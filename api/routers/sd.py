# api/routers/sd.py
import os
import json
import random
import threading
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from config.PATH import CHECKPOINT_DIR, WORKFLOW_PATH
from config.constants import NEGATIVE_BASE, MODEL_RESOLUTION
from core.image.generate import run_comfy, run_upscale, load_upscale_workflow, is_comfy_alive
from core.image.preference import save_generation_start, get_generation_by_prompt_id, update_upscaled_image
from core.system.watcher import watch_comfy
from core.system.comfy_manager import is_comfy_alive, start_comfy, wait_for_comfy
from config.PATH import (
    POSES_PATH, MOUTH_STYLE,
    HAIR_LENGTH, HAIR_STYLE, BANGS, HAIR_DETAILS, HAIR_ACCESSORIES,
    COSTUME_BASE, TOP_STYLE, BOTTOM_STYLE, OUTERWEAR, FASHION_THEME, SEASON_COSTUME,
    DESIGN_DETAILS, MATERIAL_DETAILS, ACCESSORIES, LEGWEAR, FOOTWEAR,
)
import random
from functools import lru_cache
import logging

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
    seed: int = -1  # -1이면 랜덤


class UpscaleRequest(BaseModel):
    gen_id: int
    image_path: str
    upscale_model: str
    checkpoint: str
    prompt: str = ""
    negative: str = ""


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
    def stream():
        
        try:
                
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
            
            # 프롬프트 조립 (모드 A: 사용자 입력 / 모드 B: txt 파일 랜덤 조합)
            print(f"[SD] 받은 prompt: '{req.prompt}'")
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
