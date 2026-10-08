# core/video/i2v_generate.py

import json
import copy
import glob
import os
import shutil
import time
import uuid
import websocket
from pathlib import Path
from PIL import Image as PILImage

from config.PATH import (
    COMFY_URL, COMFY_WS, COMFY_OUTPUT, COMFY_INPUT, FFMPEG_PATH
)
from core.image.generate import _post_workflow, _ws_progress, apply_lora_patch
import logging
from core.system.log_setup import clip_text

log = logging.getLogger("sd")

I2V_WORKFLOW_PATH = Path(__file__).resolve().parent.parent.parent / "assets" / "workflow" / "i2v_workflow.json"

# ── 기본값 ────────────────────────────────────────────────

I2V_DEFAULTS = {
    "model_high": "wan22EnhancedNSFWSVICamera_nsfwFASTMOVEV2Q8H.gguf",
    "model_low":  "wan22EnhancedNSFWSVICamera_nsfwFASTMOVEV2Q8L.gguf",
    "vae":        "wan_2.1_vae.safetensors",
    "clip":       "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
    "width":      832,
    "height":     480,
    "length":     81,
    "high_steps": 2,
    "low_steps": 3,
    "high_end_step": 2,   # High가 담당하는 마지막 스텝 (여기까지 High, 이후 Low)
    "cfg":        1,
    "sampler":    "euler",
    "scheduler":  "simple",
    "frame_rate": 10,
    "crf":        19,
}


def load_i2v_workflow() -> dict:
    with open(I2V_WORKFLOW_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def get_image_size(image_path: Path) -> tuple[int, int]:
    with PILImage.open(image_path) as img:
        w, h = img.size
    # 32배수 맞춤
    w = (w // 32) * 32
    h = (h // 32) * 32
    return w, h

def pad_to_wan_resolution(src_path: Path, dst_path: Path, target_w: int, target_h: int):
    with PILImage.open(src_path) as img:
        img = img.convert("RGB")
        iw, ih = img.size
        scale = min(target_w / iw, target_h / ih)
        new_w = (int(iw * scale) // 32) * 32
        new_h = (int(ih * scale) // 32) * 32
        resized = img.resize((new_w, new_h), PILImage.LANCZOS)
        canvas = PILImage.new("RGB", (target_w, target_h), (255, 255, 255))
        offset_x = (target_w - new_w) // 2
        offset_y = (target_h - new_h) // 2
        canvas.paste(resized, (offset_x, offset_y))
        canvas.save(dst_path)

def run_i2v(
    image_path: str,
    prompt: str      = "",
    negative: str    = "",
    seed: int        = -1,
    width: int       = None,
    height: int      = None,
    length: int      = None,
    high_steps: int = None,
    low_steps:  int = None,
    high_end_step: int = None,
    cfg: float       = None,
    frame_rate: int  = None,
):
    """
    I2V 생성 파이프라인 (High/Low 듀얼 KSampler) — SSE generator
    yield: {"type": "progress", "value": float, "text": str}
    yield: {"type": "done", "video_path": str}
    """
    import random

    client_id = str(uuid.uuid4())

    _w = width if width is not None else I2V_DEFAULTS["width"]
    _h = height if height is not None else I2V_DEFAULTS["height"]
    
    log.info("i2v 시작 client=%s image=%s %sx%s length=%s seed=%s prompt=%s",
             client_id[:8], os.path.basename(str(image_path)), _w, _h,
             length or I2V_DEFAULTS["length"], seed, clip_text(prompt))
    
    filename = f"i2v_input_{client_id[:8]}.png"
    dst = COMFY_INPUT / filename
    pad_to_wan_resolution(Path(image_path), dst, _w, _h)

    workflow = load_i2v_workflow()
    workflow["4"]["inputs"]["image"] = filename

    _seed  = seed  if seed >= 0 else random.randint(1, 999999999999999)
    _high_steps = high_steps or I2V_DEFAULTS["high_steps"]
    _low_steps  = low_steps  or I2V_DEFAULTS["low_steps"]
    _total_steps = _high_steps + _low_steps
    _high_end = high_end_step or _high_steps   # High 담당 마지막 스텝 (별도 지정 시 우선)
    _cfg   = cfg or I2V_DEFAULTS["cfg"]

    # High KSamplerAdvanced
    high_in = workflow["12_high"]["inputs"]
    high_in["noise_seed"]  = _seed
    high_in["steps"]       = _total_steps
    high_in["cfg"]         = _cfg
    high_in["end_at_step"] = _high_end

    # Low KSamplerAdvanced
    low_in = workflow["12_low"]["inputs"]
    low_in["noise_seed"]    = _seed
    low_in["steps"]         = _total_steps
    low_in["cfg"]           = _cfg
    low_in["start_at_step"] = _high_end

    # 모델 (필요 시 교체 가능하도록 파라미터화는 나중 드롭다운 작업에서)
    workflow["6_high"]["inputs"]["model_name"] = I2V_DEFAULTS["model_high"]
    workflow["6_low"]["inputs"]["model_name"]  = I2V_DEFAULTS["model_low"]

    workflow["7"]["inputs"]["width"]  = _w
    workflow["7"]["inputs"]["height"] = _h
    workflow["7"]["inputs"]["length"] = length or I2V_DEFAULTS["length"]

    workflow["8"]["inputs"]["text"] = prompt
    workflow["9"]["inputs"]["text"] = negative

    output_prefix = f"i2v_{client_id[:8]}"
    workflow["14"]["inputs"]["filename_prefix"] = f"Wan2.1/{output_prefix}"
    workflow["14"]["inputs"]["frame_rate"] = frame_rate or I2V_DEFAULTS["frame_rate"]

    yield {"type": "progress", "value": 0.01, "text": "워크플로우 전송 중..."}

    before = time.time()

    ws = websocket.WebSocket()
    ws.connect(f"{COMFY_WS}?clientId={client_id}")
    prompt_id = _post_workflow(workflow, client_id)

    for event in _ws_progress(ws, start_ratio=0.05, end_ratio=0.97, prompt_id=prompt_id):
        yield event

    yield {"type": "progress", "value": 0.98, "text": "결과 수집 중..."}

    pattern = str(COMFY_OUTPUT / "Wan2.1" / f"{output_prefix}*.mp4")
    files = [f for f in glob.glob(pattern) if os.path.getctime(f) > before]

    if not files:
        raise RuntimeError("I2V 결과 파일을 찾을 수 없음")

    video_path = max(files, key=os.path.getctime)
    yield {"type": "done", "video_path": video_path, "seed": _seed}