import os
import json
import random
import threading
import time as _time
import uuid
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, File, UploadFile, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config.PATH import CHECKPOINT_DIR, WORKFLOW_PATH, COMFY_INPUT
from config.constants import MODEL_RESOLUTION
# 입력 범위 (UI 슬라이더와 동일)
DENOISE_MIN, DENOISE_MAX = 0.1, 1.0
LORA_STRENGTH_MIN, LORA_STRENGTH_MAX = 0.0, 1.0
CFG_MIN, CFG_MAX = 1.0, 10.0
I2I_DENOISE_DEFAULT = 0.7

from core.image.generate import run_comfy, run_upscale, run_i2i, run_i2i_mask
from core.image.preference import (
    save_generation_start, get_generation_by_prompt_id, update_upscaled_image,
    update_generation_meta, save_video,
)
from core.system.watcher import watch_comfy
from core.system.comfy_manager import is_comfy_alive, start_comfy, wait_for_comfy
from core.system.notify import notify
from core.system import jobs
from core.system import gen_queue
import logging
from core.system.log_setup import clip_text

log = logging.getLogger("sd")

router = APIRouter(prefix="/api/sd", tags=["sd"])

# ── 유틸 ──────────────────────────────────────────────────

def get_local_checkpoints() -> list[str]:
    if not os.path.exists(str(CHECKPOINT_DIR)):
        return []
    return sorted([f for f in os.listdir(str(CHECKPOINT_DIR)) if f.endswith(('.safetensors', '.ckpt'))])


def get_local_upscale_models() -> list[str]:
    from config.PATH import UPSCALE_MODEL_DIR
    if not os.path.exists(str(UPSCALE_MODEL_DIR)):
        return []
    return sorted([f for f in os.listdir(str(UPSCALE_MODEL_DIR)) if f.endswith(('.pth', '.pt'))])

def get_model_config(checkpoint_name: str) -> dict:
    name = checkpoint_name.lower()
    for key, config in MODEL_RESOLUTION.items():
        if key.lower() in name:
            return config
    return {"width": 832, "height": 1216}

def get_local_loras() -> list[str]:
    from config.PATH import LORA_DIR
    if not os.path.exists(str(LORA_DIR)):
        return []
    return sorted([f for f in os.listdir(str(LORA_DIR)) if f.endswith('.safetensors')])

def load_workflow() -> dict:
    with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

@lru_cache(maxsize=None)
def _load_txt(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def _dedupe_tags(text: str) -> str:
    """쉼표 구분 태그에서 중복 제거 (대소문자 무시, 순서 유지)"""
    seen, out = set(), []
    for t in (x.strip() for x in text.split(",")):
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return ", ".join(out)
    
# ── 스키마 ────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    prompt: str = ""
    negative: str = ""
    checkpoint: str
    seed: int = -1
    lora_name: str = ""
    lora_strength: float = Field(0.8, ge=LORA_STRENGTH_MIN, le=LORA_STRENGTH_MAX)

class UpscaleRequest(BaseModel):
    gen_id: int
    image_path: str
    upscale_model: str
    checkpoint: str
    prompt: str = ""
    negative: str = ""
    denoise: float = Field(I2I_DENOISE_DEFAULT, ge=DENOISE_MIN, le=DENOISE_MAX)
    seed: int = -1
    lora_name: str = ""
    lora_strength: float = Field(0.8, ge=LORA_STRENGTH_MIN, le=LORA_STRENGTH_MAX)

class I2IRequest(BaseModel):
    image_path: str
    checkpoint: str
    prompt: str = ""
    negative: str = ""
    denoise: float = Field(I2I_DENOISE_DEFAULT, ge=DENOISE_MIN, le=DENOISE_MAX)
    seed: int = -1
    lora_name: str = ""
    lora_strength: float = Field(0.8, ge=LORA_STRENGTH_MIN, le=LORA_STRENGTH_MAX)

# ── 엔드포인트 ────────────────────────────────────────────

@router.get("/checkpoints")
def list_checkpoints():
    return {"checkpoints": get_local_checkpoints()}


@router.get("/upscale-models")
def list_upscale_models():
    return {"models": get_local_upscale_models()}


@router.get("/status")
def comfy_status():
    return {"alive": is_comfy_alive()}


SAMPLER_MAP = {
    "Euler a":    "euler_ancestral",
    "Euler":      "euler",
    "DPM++ 2M":   "dpmpp_2m",
    "DDIM":       "ddim",
}
SCHEDULER_MAP = {
    "Automatic":    "normal",
    "SGM Uniform":  "sgm_uniform",
    "Karras":       "karras",
}


def _mark_failed(gen_id: int):
    from core.db import get_conn
    with get_conn() as conn:
        conn.execute("UPDATE generations SET status = 'failed' WHERE id = ?", (gen_id,))
        conn.commit()


def _t2i_events(req: GenerateRequest):
    """
    t2i 생성 이벤트 제너레이터
    yield {"type": "progress", "value": float, "text": str}
    yield {"type": "done", "gen_id": int, "image_path": str}
    """
    log.debug("t2i 요청 lora=%s strength=%s", req.lora_name, req.lora_strength)
    if not is_comfy_alive():
        yield {"type": "progress", "value": 0.0, "text": "ComfyUI 시작 중..."}
        start_comfy()
        wait_for_comfy()

    workflow = load_workflow()
    cfg      = get_model_config(req.checkpoint)

    workflow["4"]["inputs"]["ckpt_name"] = req.checkpoint
    seed = req.seed if req.seed >= 0 else random.randint(1, 999999999999999)
    workflow["3"]["inputs"]["seed"] = seed

    # 해상도 (50% 확률 가로/세로 스왑)
    w, h = cfg["width"], cfg["height"]
    if random.random() < 0.5:
        w, h = h, w
    workflow["5"]["inputs"]["width"]  = w
    workflow["5"]["inputs"]["height"] = h

    v4_prefix = cfg.get("prefix")
    if "steps" in cfg:
        workflow["3"]["inputs"]["steps"] = cfg["steps"]
        workflow["3"]["inputs"]["cfg"]   = cfg["cfg"]
    if "sampler_name" in cfg:
        workflow["3"]["inputs"]["sampler_name"] = SAMPLER_MAP.get(cfg["sampler_name"], "euler_ancestral")
    if "scheduler" in cfg:
        workflow["3"]["inputs"]["scheduler"] = SCHEDULER_MAP.get(cfg["scheduler"], "normal")

    core_prompt = req.prompt.strip()

    # 이미 모델 prefix로 시작하면 다시 붙이지 않음
    _n = lambda s: s.replace("_", " ").lower()
    if v4_prefix and not _n(core_prompt).startswith(_n(v4_prefix)):
        user_prompt = f"{v4_prefix}, {core_prompt}"
    else:
        user_prompt = core_prompt
    workflow["6"]["inputs"]["text"] = user_prompt

    if req.lora_name:
            from core.image.generate import apply_lora_patch
            workflow = apply_lora_patch(workflow, req.lora_name, req.lora_strength, positive_node_id="6")

    # 네거티브
    negative = _dedupe_tags(req.negative.strip())
    workflow["7"]["inputs"]["text"] = negative

    # gen_id 선발급
    pre_gen_id = save_generation_start("pending", user_prompt, seed, req.checkpoint)
    log.info("t2i gen_id=%s ckpt=%s seed=%s %sx%s lora=%s prompt=%s",
             pre_gen_id, req.checkpoint, seed, w, h, req.lora_name or "-", clip_text(user_prompt))
    log.debug("t2i gen_id=%s prompt_full=%r negative_full=%r", pre_gen_id, user_prompt, negative)
    workflow["9"]["inputs"]["filename_prefix"] = f"ComfyUI_{pre_gen_id:04d}_generated"

    # 생성 DNA 기록 (실제 워크플로우에 들어간 값 기준)
    ksampler = workflow["3"]["inputs"]
    update_generation_meta(
        pre_gen_id,
        negative=negative,
        lora_name=req.lora_name or None,
        lora_strength=req.lora_strength if req.lora_name else None,
        width=w, height=h,
        steps=ksampler.get("steps"), cfg=ksampler.get("cfg"),
        sampler=ksampler.get("sampler_name"), scheduler=ksampler.get("scheduler"),
    )

    prompt_id = None
    try:
        for event in run_comfy(workflow):
            if event["type"] == "prompt_id":
                prompt_id = event["prompt_id"]
                threading.Thread(
                    target=watch_comfy,
                    args=(prompt_id, event["before"], user_prompt, seed, req.checkpoint, pre_gen_id),
                    daemon=True
                ).start()

            elif event["type"] == "progress":
                yield {"type": "progress", "value": event["value"], "text": event["text"]}

            elif event["type"] == "done":
                gen_record = None
                for _ in range(20):
                    gen_record = get_generation_by_prompt_id(prompt_id)
                    if gen_record:
                        break
                    _time.sleep(0.5)
                gen_id = gen_record["id"] if gen_record else pre_gen_id
                yield {"type": "done", "gen_id": gen_id, "image_path": event["image_path"]}
    except Exception:
        _mark_failed(pre_gen_id)
        raise


@router.post("/generate")
def generate(req: GenerateRequest):
    """
    이미지 생성 — SSE 스트림 (큐를 거치지 않는 직접 호출용)
    event: progress  → {"value": float, "text": str}
    event: done      → {"gen_id": int, "image_path": str}
    event: error     → {"message": str}
    """
    def stream():
        try:
            for ev in _t2i_events(req):
                if ev["type"] == "progress":
                    yield f"event: progress\ndata: {json.dumps({'value': ev['value'], 'text': ev['text']})}\n\n"
                elif ev["type"] == "done":
                    yield f"event: done\ndata: {json.dumps({'gen_id': ev['gen_id'], 'image_path': ev['image_path']})}\n\n"
        except Exception as e:
            log.exception("t2i 스트림 실패")
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/upscale")
def upscale(req: UpscaleRequest):
    """
    업스케일 — SSE 스트림으로 progress 이벤트 반환
    event: progress  → {"value": float, "text": str}
    event: done      → {"image_path": str, "filename": str}
    event: error     → {"message": str}
    """
    def stream():
        try:
            for event in run_upscale(
                req.image_path,
                req.upscale_model,
                checkpoint=req.checkpoint,
                prompt=req.prompt,
                negative=req.negative
            ):
                if event["type"] == "progress":
                    yield f"event: progress\ndata: {json.dumps({'value': event['value'], 'text': event['text']})}\n\n"
                elif event["type"] == "done":
                    filename = os.path.basename(event["image_path"])
                    update_upscaled_image(req.gen_id, filename)
                    yield f"event: done\ndata: {json.dumps({'image_path': event['image_path'], 'filename': filename})}\n\n"
        except Exception as e:
            log.exception("upscale 실패 gen_id=%s", req.gen_id)
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")

@router.post("/i2i")
def i2i(req: I2IRequest):
    """
    i2i — SSE 스트림
    event: progress → {"value": float, "text": str}
    event: done     → {"image_path": str, "filename": str}
    event: error    → {"message": str}
    """
    def stream():
        try:
            # i2i 엔드포인트는 run_i2i 내부에서 workflow 로드하므로
            # run_i2i 파라미터로 lora 정보 전달 필요
            for event in run_i2i(
                req.image_path, req.checkpoint,
                req.prompt, req.negative,
                req.denoise, req.seed,
                req.lora_name, req.lora_strength
            ):
                if event["type"] == "progress":
                    yield f"event: progress\ndata: {json.dumps({'value': event['value'], 'text': event['text']})}\n\n"
                elif event["type"] == "done":
                    filename = os.path.basename(event["image_path"])
                    yield f"event: done\ndata: {json.dumps({'image_path': event['image_path'], 'filename': filename})}\n\n"
        except Exception as e:
            log.exception("i2i 실패 image=%s", req.image_path)
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")

@router.post("/i2i-mask")
async def i2i_mask(
    image_path:  Annotated[str,   Form()],
    mask_path:   Annotated[str,   Form()] = "",
    checkpoint:  Annotated[str,   Form()] = "",
    prompt:      Annotated[str,   Form()] = "",
    negative:    Annotated[str,   Form()] = "",
    denoise:     Annotated[float, Form(ge=DENOISE_MIN, le=DENOISE_MAX)] = I2I_DENOISE_DEFAULT,
    seed:        Annotated[int,   Form()] = -1,
    lora_name:     Annotated[str,   Form()] = "",
    lora_strength: Annotated[float, Form(ge=LORA_STRENGTH_MIN, le=LORA_STRENGTH_MAX)] = 0.8,
    mask_file:   UploadFile = File(None),
):
    # 마스크 blob을 임시 파일로 저장
    tmp_mask_path = None
    if mask_file:
        mask_bytes = await mask_file.read()
        tmp_mask_path = os.path.join(COMFY_INPUT, f"i2i_mask_tmp_{uuid.uuid4().hex}.png")
        with open(tmp_mask_path, "wb") as f:
            f.write(mask_bytes)

    def stream():
        try:
            for event in run_i2i_mask(
                image_path, tmp_mask_path or mask_path,
                checkpoint, prompt, negative, denoise, seed,
                lora_name, lora_strength
            ):
                if event["type"] == "progress":
                    yield f"event: progress\ndata: {json.dumps({'value': event['value'], 'text': event['text']})}\n\n"
                elif event["type"] == "done":
                    filename = os.path.basename(event["image_path"])
                    yield f"event: done\ndata: {json.dumps({'image_path': event['image_path'], 'filename': filename})}\n\n"
        except Exception as e:
            log.exception("i2i-mask 실패 image=%s", image_path)
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
        finally:
            if tmp_mask_path and os.path.exists(tmp_mask_path):
                try:
                    os.remove(tmp_mask_path)
                except OSError:
                    pass

    return StreamingResponse(stream(), media_type="text/event-stream")

@router.get("/loras")
def list_loras():
    return {"loras": get_local_loras()}

# ── I2V ───────────────────────────────────────────────────

class I2VRequest(BaseModel):
    image_path: str
    prompt:     str   = ""
    negative:   str   = ""
    seed:       int   = -1
    width:      int   = 832
    height:     int   = 480
    length:     int   = 81
    high_steps: int   = 2
    low_steps:  int   = 3
    cfg:        float = Field(1.0, ge=CFG_MIN, le=CFG_MAX)
    frame_rate: int   = 10


@router.post("/i2v")
def i2v(req: I2VRequest):
    """
    I2V — 백그라운드 작업 시작
    즉시 {"job_id": str} 반환. 진행 상황은 GET /jobs/{job_id}/stream 으로 수신.
    """
    from core.video.i2v_generate import run_i2v

    job_id = jobs.create_job("i2v")

    def worker():
        t0 = _time.time()
        try:
            for event in run_i2v(
                req.image_path,
                prompt=req.prompt,
                negative=req.negative,
                seed=req.seed,
                width=req.width,
                height=req.height,
                length=req.length,
                high_steps=req.high_steps,
                low_steps=req.low_steps,
                cfg=req.cfg,
                frame_rate=req.frame_rate,
            ):
                if event["type"] == "progress":
                    jobs.update_progress(job_id, event["value"], event["text"])
                elif event["type"] == "done":
                    video_path = event["video_path"]
                    try:
                        save_video(
                            video_path=video_path,
                            source_image=req.image_path,
                            prompt=req.prompt,
                            negative=req.negative,
                            seed=event.get("seed", req.seed),
                            width=req.width,
                            height=req.height,
                            cfg=req.cfg,
                            params={
                                "length": req.length,
                                "frame_rate": req.frame_rate,
                                "high_steps": req.high_steps,
                                "low_steps": req.low_steps,
                            },
                        )
                    except Exception:
                        log.exception("I2V DB 등록 실패")
                    jobs.finish_job(job_id, {"video_path": video_path})
                    notify("I2V 완료", os.path.basename(video_path), _time.time() - t0)
        except Exception as e:
            jobs.fail_job(job_id, str(e))
            notify("I2V 실패", str(e), _time.time() - t0, ok=False)

    threading.Thread(target=worker, daemon=True).start()
    return {"job_id": job_id}

# !!active가 stream보다 위에 존재해야함.
@router.get("/jobs/active")
def active_jobs(kind: str = "i2v"):
    """진행 중이거나 최근 끝난 작업 목록 (최신순)"""
    return {"jobs": jobs.list_jobs(kind=kind)}


@router.get("/jobs/{job_id}/stream")
def job_stream(job_id: str):
    """
    작업 상태 SSE 스트림 — 재연결 가능
    event: progress → {"value": float, "text": str}
    event: done     → {"video_path": str}
    event: error    → {"message": str}
    """
    import time as _t

    def stream():
        last = None
        while True:
            job = jobs.get_job(job_id)
            if job is None:
                yield f"event: error\ndata: {json.dumps({'message': '작업을 찾을 수 없음'})}\n\n"
                return

            snapshot = (job["progress"], job["text"], job["status"])
            if snapshot != last:
                last = snapshot
                if job["status"] == "running":
                    yield f"event: progress\ndata: {json.dumps({'value': job['progress'], 'text': job['text']})}\n\n"

            if job["status"] == "done":
                yield f"event: done\ndata: {json.dumps(job['result'])}\n\n"
                return
            if job["status"] == "error":
                yield f"event: error\ndata: {json.dumps({'message': job['error']})}\n\n"
                return

            _t.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream")

# ── 생성 큐 ───────────────────────────────────────────────

def _lora_label(name: str, strength: float):
    return f"{name} ({strength})" if name else None


def _run_t2i(p: dict):
    yield from _t2i_events(GenerateRequest(**p))


def _run_i2i(p: dict):
    if p.get("mask_path"):
        gen = run_i2i_mask(
            p["image_path"], p["mask_path"], p["checkpoint"], p["prompt"], p["negative"],
            p["denoise"], p["seed"], p["lora_name"], p["lora_strength"],
        )
    else:
        gen = run_i2i(
            p["image_path"], p["checkpoint"], p["prompt"], p["negative"],
            p["denoise"], p["seed"], p["lora_name"], p["lora_strength"],
        )
    for ev in gen:
        if ev["type"] == "progress":
            yield ev
        elif ev["type"] == "done":
            yield {"type": "done", "image_path": ev["image_path"],
                   "filename": os.path.basename(ev["image_path"])}


def _run_i2v(p: dict):
    from core.video.i2v_generate import run_i2v
    t0 = _time.time()
    try:
        for event in run_i2v(
            p["image_path"], prompt=p["prompt"], negative=p["negative"], seed=p["seed"],
            width=p["width"], height=p["height"], length=p["length"],
            high_steps=p["high_steps"], low_steps=p["low_steps"],
            cfg=p["cfg"], frame_rate=p["frame_rate"],
        ):
            if event["type"] == "progress":
                yield event
            elif event["type"] == "done":
                video_path = event["video_path"]
                try:
                    save_video(
                        video_path=video_path,
                        source_image=p["image_path"],
                        prompt=p["prompt"], negative=p["negative"],
                        seed=event.get("seed", p["seed"]),
                        width=p["width"], height=p["height"], cfg=p["cfg"],
                        params={
                            "length": p["length"], "frame_rate": p["frame_rate"],
                            "high_steps": p["high_steps"], "low_steps": p["low_steps"],
                        },
                    )
                except Exception as e:
                    print(f"[I2V] DB 등록 실패: {e}")
                notify("I2V 완료", os.path.basename(video_path), _time.time() - t0)
                yield {"type": "done", "video_path": video_path}
    except gen_queue.GenerationCancelled:
        raise
    except Exception as e:
        notify("I2V 실패", str(e), _time.time() - t0, ok=False)
        raise


gen_queue.register_runner("t2i", _run_t2i)
gen_queue.register_runner("i2i", _run_i2i)
gen_queue.register_runner("i2v", _run_i2v)


@router.post("/queue/t2i")
def queue_t2i(req: GenerateRequest):
    summary = {
        "mode": "t2i", "checkpoint": req.checkpoint,
        "prompt": req.prompt, "negative": req.negative,
        "lora": _lora_label(req.lora_name, req.lora_strength),
    }
    return {"id": gen_queue.enqueue("t2i", req.dict(), summary)}


@router.post("/queue/i2i")
async def queue_i2i(
    image_path:    Annotated[str,   Form()],
    checkpoint:    Annotated[str,   Form()] = "",
    prompt:        Annotated[str,   Form()] = "",
    negative:      Annotated[str,   Form()] = "",
    denoise:       Annotated[float, Form(ge=DENOISE_MIN, le=DENOISE_MAX)] = I2I_DENOISE_DEFAULT,
    seed:          Annotated[int,   Form()] = -1,
    lora_name:     Annotated[str,   Form()] = "",
    lora_strength: Annotated[float, Form(ge=LORA_STRENGTH_MIN, le=LORA_STRENGTH_MAX)] = 0.8,
    mask_file:     UploadFile = File(None),
):
    mask_path = None
    if mask_file:
        mask_bytes = await mask_file.read()
        mask_path = os.path.join(COMFY_INPUT, f"i2i_mask_tmp_{uuid.uuid4().hex}.png")
        with open(mask_path, "wb") as f:
            f.write(mask_bytes)

    payload = {
        "image_path": image_path, "mask_path": mask_path, "checkpoint": checkpoint,
        "prompt": prompt, "negative": negative, "denoise": denoise, "seed": seed,
        "lora_name": lora_name, "lora_strength": lora_strength,
    }
    summary = {
        "mode": "i2i", "checkpoint": checkpoint, "prompt": prompt, "negative": negative,
        "lora": _lora_label(lora_name, lora_strength),
        "base_image": image_path, "denoise": denoise, "seed": seed,
        "has_mask": bool(mask_path),
    }
    item_id = gen_queue.enqueue("i2i", payload, summary, cleanup=[mask_path] if mask_path else [])
    return {"id": item_id}


@router.post("/queue/i2v")
def queue_i2v(req: I2VRequest):
    summary = {
        "mode": "i2v", "prompt": req.prompt, "negative": req.negative,
        "base_image": req.image_path, "seed": req.seed,
        "width": req.width, "height": req.height, "length": req.length,
        "high_steps": req.high_steps, "low_steps": req.low_steps, "cfg": req.cfg,
    }
    return {"id": gen_queue.enqueue("i2v", req.dict(), summary)}


@router.get("/queue")
def get_queue():
    return {"items": gen_queue.snapshot(), "shutdown": gen_queue.shutdown_state()}


class ReorderRequest(BaseModel):
    ids: list[str]
@router.post("/queue/reorder")
def reorder_queue(req: ReorderRequest):
    gen_queue.reorder(req.ids)
    return {"items": gen_queue.snapshot()}

class ShutdownRequest(BaseModel):
    enabled: bool
@router.post("/queue/shutdown")
def set_queue_shutdown(req: ShutdownRequest):
    gen_queue.set_shutdown(req.enabled)
    return gen_queue.shutdown_state()


@router.post("/queue/shutdown/abort")
def abort_queue_shutdown():
    return {"aborted": gen_queue.abort_shutdown()}


@router.delete("/queue/{item_id}")
def delete_queue_item(item_id: str):
    return {"result": gen_queue.remove(item_id)}


@router.delete("/queue")
def clear_queue():
    return {"cancelled": gen_queue.clear_pending()}