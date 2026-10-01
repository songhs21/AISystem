# api/routers/sd.py
import os
import json
import random
import threading
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from config.PATH import CHECKPOINT_DIR, WORKFLOW_PATH, COMFY_INPUT
from config.constants import NEGATIVE_BASE, MODEL_RESOLUTION
from core.image.generate import run_comfy, run_upscale, load_upscale_workflow, is_comfy_alive, run_i2i, run_i2i_mask
from core.image.preference import save_generation_start, get_generation_by_prompt_id, update_upscaled_image
from core.system.watcher import watch_comfy
from core.system.comfy_manager import is_comfy_alive, start_comfy, wait_for_comfy
import random
from functools import lru_cache
import uuid
from typing import Annotated
from fastapi import File, UploadFile, Form
import time as _time
from core.system.notify import notify
router = APIRouter(prefix="/api/sd", tags=["sd"])
from core.system.notify import notify
from core.system import jobs

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

# ── 스키마 ────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    prompt: str = ""
    negative: str = ""
    checkpoint: str
    seed: int = -1
    lora_name: str = ""
    lora_strength: float = 0.8

class UpscaleRequest(BaseModel):
    gen_id: int
    image_path: str
    upscale_model: str
    checkpoint: str
    prompt: str = ""
    negative: str = ""

class I2IRequest(BaseModel):
    image_path: str
    checkpoint: str
    prompt: str = ""
    negative: str = ""
    denoise: float = 0.7
    seed: int = -1
    lora_name: str = ""
    lora_strength: float = 0.8

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


@router.post("/generate")
def generate(req: GenerateRequest):
    """
    이미지 생성 — SSE 스트림으로 progress 이벤트 반환
    event: progress  → {"value": float, "text": str}
    event: done      → {"gen_id": int, "image_path": str}
    event: error     → {"message": str}
    """

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

    def stream():
        
        try:
            print(f"[SD] lora_name={req.lora_name}, lora_strength={req.lora_strength}")
            # ComfyUI 자동 기동
            if not is_comfy_alive():
                yield f"event: progress\ndata: {json.dumps({'value': 0.0, 'text': 'ComfyUI 시작 중...'})}\n\n"
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

            # v4 prefix
            v4_prefix = cfg.get("prefix")
            if "steps" in cfg:
                workflow["3"]["inputs"]["steps"] = cfg["steps"]
                workflow["3"]["inputs"]["cfg"]   = cfg["cfg"]
            if "sampler_name" in cfg:
                comfy_sampler = SAMPLER_MAP.get(cfg["sampler_name"], "euler_ancestral")
                workflow["3"]["inputs"]["sampler_name"] = comfy_sampler
            if "scheduler" in cfg:
                comfy_scheduler = SCHEDULER_MAP.get(cfg["scheduler"], "normal")
                workflow["3"]["inputs"]["scheduler"] = comfy_scheduler
            if req.lora_name:
                from core.image.generate import apply_lora_patch
                workflow = apply_lora_patch(workflow, req.lora_name, req.lora_strength, positive_node_id="6")
            
            # 프롬프트 조립 (모드 A: 사용자 입력 / 모드 B: txt 파일 랜덤 조합)
            print(f"[SD] 받은 prompt: '{req.prompt}', '{req.lora_name}'")
            if req.prompt.strip():
                core_prompt = req.prompt.strip()
                print(f"[SD] 모드 A")
            else:
                core_prompt = ""
                print(f"[SD] 빈 프롬프트")

            # 프롬프트 조립
            user_prompt = f"{v4_prefix}, {core_prompt}" if v4_prefix else core_prompt
            workflow["6"]["inputs"]["text"] = user_prompt

            # 네거티브
            negative = ", ".join(p for p in [req.negative.strip(), NEGATIVE_BASE] if p)
            workflow["7"]["inputs"]["text"] = negative

            # gen_id 선발급
            pre_gen_id = save_generation_start("pending", user_prompt, seed, req.checkpoint)
            workflow["9"]["inputs"]["filename_prefix"] = f"ComfyUI_{pre_gen_id:04d}_generated"

            prompt_id  = None
            before     = None

            for event in run_comfy(workflow):
                if event["type"] == "prompt_id":
                    prompt_id = event["prompt_id"]
                    before    = event["before"]
                    threading.Thread(
                        target=watch_comfy,
                        args=(prompt_id, before, user_prompt, seed, req.checkpoint, pre_gen_id),
                        daemon=True
                    ).start()

                elif event["type"] == "progress":
                    yield f"event: progress\ndata: {json.dumps({'value': event['value'], 'text': event['text']})}\n\n"

                elif event["type"] == "done":
                    import time
                    gen_record = None
                    for _ in range(20):
                        gen_record = get_generation_by_prompt_id(prompt_id)
                        if gen_record:
                            break
                        time.sleep(0.5)

                    gen_id = gen_record["id"] if gen_record else pre_gen_id
                    yield f"event: done\ndata: {json.dumps({'gen_id': gen_id, 'image_path': event['image_path']})}\n\n"

        except Exception as e:
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
                negative=req.negative or NEGATIVE_BASE
            ):
                if event["type"] == "progress":
                    yield f"event: progress\ndata: {json.dumps({'value': event['value'], 'text': event['text']})}\n\n"
                elif event["type"] == "done":
                    filename = os.path.basename(event["image_path"])
                    update_upscaled_image(req.gen_id, filename)
                    yield f"event: done\ndata: {json.dumps({'image_path': event['image_path'], 'filename': filename})}\n\n"
        except Exception as e:
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
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")

@router.post("/i2i-mask")
async def i2i_mask(
    image_path:  Annotated[str,   Form()],
    mask_path:   Annotated[str,   Form()] = "",
    checkpoint:  Annotated[str,   Form()] = "",
    prompt:      Annotated[str,   Form()] = "",
    negative:    Annotated[str,   Form()] = "",
    denoise:     Annotated[float, Form()] = 0.5,
    seed:        Annotated[int,   Form()] = -1,
    lora_name:     Annotated[str,   Form()] = "",
    lora_strength: Annotated[float, Form()] = 0.8,
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
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
        finally:
            if tmp_mask_path and os.path.exists(tmp_mask_path):
                try:
                    os.remove(tmp_mask_path)
                except:
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
    cfg:        float = 1.0
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
                    jobs.finish_job(job_id, {"video_path": event["video_path"]})
                    notify("I2V 완료", os.path.basename(event["video_path"]), _time.time() - t0)
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