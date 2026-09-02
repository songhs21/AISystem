# core/image/generate.py
import requests
import websocket
import json
import glob
import os
import shutil
import time
import uuid
import random
from config.PATH import (
    COMFY_URL, COMFY_WS, COMFY_DIR, COMFY_INPUT, COMFY_OUTPUT,
    UPSCALE_WORKFLOW_DIR, INPAINTING_DIR, DETAIL_INPAINTING_DIR,
    PYTHON_EMBEDED, I2IBASE, I2I_MASK
)
from core.system.comfy_manager import is_comfy_alive, start_comfy, wait_for_comfy
from core.db import get_conn
import subprocess
import time

# ── 워크플로우 로드 ───────────────────────────────────────

def load_upscale_workflow() -> dict:
    with open(UPSCALE_WORKFLOW_DIR, "r", encoding="utf-8") as f:
        return json.load(f)


def load_inpaint_workflow(mode: str = "replace") -> dict:
    path = INPAINTING_DIR if mode == "replace" else DETAIL_INPAINTING_DIR
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── 파일 I/O 대기 ─────────────────────────────────────────

def wait_for_file_ready(filepath: str, timeout: int = 3) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            return True
        time.sleep(0.1)
    return False


# ── WebSocket 이벤트 공통 수신 ────────────────────────────

def _ws_progress(ws, start_ratio: float = 0.15, end_ratio: float = 0.95):
    """
    WebSocket에서 progress 이벤트를 수신하며 yield.
    yield {"type": "progress", "value": float, "text": str}
    완료(executing node=None) 시 루프 종료.
    """
    try:
        while True:
            raw = ws.recv()
            if isinstance(raw, bytes):
                continue
            msg  = json.loads(raw)
            mtype = msg.get("type")
            data  = msg.get("data", {})

            if mtype == "status":
                remaining = data.get("status", {}).get("exec_info", {}).get("queue_remaining")
                if remaining:
                    yield {"type": "progress", "value": 0.05, "text": f"큐 대기 중... (앞 {remaining}개)"}

            elif mtype == "execution_start":
                yield {"type": "progress", "value": start_ratio, "text": "시작..."}

            elif mtype == "execution_cached":
                yield {"type": "progress", "value": start_ratio + 0.05, "text": "캐시 로드 중..."}

            elif mtype == "progress":
                value = data.get("value", 0)
                max_v = data.get("max", 1)
                mapped = start_ratio + (value / max_v if max_v > 0 else 0) * (end_ratio - start_ratio)
                yield {"type": "progress", "value": mapped, "text": f"스텝 {value}/{max_v}"}

            elif mtype == "executing" and data.get("node") is None:
                yield {"type": "progress", "value": 0.97, "text": "후처리 중..."}
                break
    finally:
        ws.close()


def _post_workflow(workflow: dict, client_id: str) -> str:
    """워크플로우 전송 → prompt_id 반환. 검증 실패 시 ValueError."""
    response = requests.post(
        f"{COMFY_URL}/prompt",
        json={"prompt": workflow, "client_id": client_id},
        timeout=5
    )
    response.raise_for_status()
    resp = response.json()
    if "prompt_id" not in resp:
        raise ValueError(
            f"ComfyUI 노드 검증 실패\n"
            f"▶ 노드 에러: {resp.get('node_errors', {})}\n"
            f"▶ 에러: {resp.get('error', {})}"
        )
    return resp["prompt_id"]

# ── 이미지 생성 ───────────────────────────────────────────

def run_comfy(workflow: dict, client_id: str = None):
    if not is_comfy_alive():
        yield {"type": "progress", "value": 0.0, "text": "ComfyUI 시작 중..."}
        start_comfy()
        wait_for_comfy()
    """
    yield {"type": "progress", "value": float, "text": str}
    yield {"type": "prompt_id", "prompt_id": str, "before": float}
    yield {"type": "done", "image_path": str, "prompt_id": str}
    """
    if client_id is None:
        client_id = str(uuid.uuid4())

    before = time.time()
    prompt_id = _post_workflow(workflow, client_id)
    yield {"type": "prompt_id", "prompt_id": prompt_id, "before": before}
    yield {"type": "progress", "value": 0.02, "text": "큐 등록됨..."}

    ws = websocket.WebSocket()
    ws.connect(f"{COMFY_WS}?clientId={client_id}")
    yield from _ws_progress(ws, start_ratio=0.10, end_ratio=0.95)

    files = glob.glob(os.path.join(COMFY_OUTPUT, "*.png"))
    new_files = [f for f in files if os.path.getctime(f) > before]
    if not new_files:
        raise RuntimeError("생성된 이미지를 찾을 수 없음")

    image_path = max(new_files, key=os.path.getctime)
    yield {"type": "done", "image_path": image_path, "prompt_id": prompt_id}


# ── 업스케일 ──────────────────────────────────────────────

def run_upscale(image_path: str, select_upscaler: str, checkpoint: str,
                prompt: str, negative: str = "", client_id: str = None):
    if not is_comfy_alive():
        yield {"type": "progress", "value": 0.0, "text": "ComfyUI 시작 중..."}
        start_comfy()
        wait_for_comfy()
    """
    yield {"type": "progress", "value": float, "text": str}
    yield {"type": "done", "image_path": str}
    """
    if client_id is None:
        client_id = str(uuid.uuid4())

    filename = os.path.basename(image_path)
    shutil.copy2(image_path, os.path.join(COMFY_INPUT, filename))

    workflow = load_upscale_workflow()
    workflow["4"]["inputs"]["image"]   = filename
    workflow["10"]["inputs"]["ckpt_name"] = checkpoint
    workflow["16"]["inputs"]["text"]   = prompt
    workflow["17"]["inputs"]["text"]   = negative
    if select_upscaler:
        workflow["14"]["inputs"]["model_name"] = select_upscaler

    origin_stem = os.path.splitext(filename)[0].strip()
    model_stem  = os.path.splitext(workflow["14"]["inputs"]["model_name"])[0].strip()
    workflow["3"]["inputs"]["filename_prefix"] = f"{origin_stem}_{model_stem}"

    before    = time.time()
    prompt_id = _post_workflow(workflow, client_id)
    yield {"type": "progress", "value": 0.05, "text": "업스케일 큐 등록됨..."}

    ws = websocket.WebSocket()
    ws.connect(f"{COMFY_WS}?clientId={client_id}")
    yield from _ws_progress(ws, start_ratio=0.10, end_ratio=0.95)

    files = glob.glob(os.path.join(COMFY_OUTPUT, f"{origin_stem}*{model_stem}*.png"))
    new_files = [f for f in files if os.path.getctime(f) > before]
    if not new_files:
        raise RuntimeError(f"업스케일된 이미지를 찾을 수 없음 (패턴: {origin_stem}*{model_stem}*.png)")

    yield {"type": "done", "image_path": max(new_files, key=os.path.getctime)}


# ── 인페인팅 ──────────────────────────────────────────────

def run_inpaint(image_path: str, mask_path: str, checkpoint: str,
                prompt: str, negative: str = "", denoise: float = 0.75,
                steps: int = 20, mode: str = "replace", gen_id: int = 0,
                client_id: str = None):
    if not is_comfy_alive():
        yield {"type": "progress", "value": 0.0, "text": "ComfyUI 시작 중..."}
        start_comfy()
        wait_for_comfy()
    """
    yield {"type": "progress", "value": float, "text": str}
    yield {"type": "done", "image_path": str}
    """
    if client_id is None:
        client_id = str(uuid.uuid4())

    filename    = os.path.basename(image_path)
    origin_stem = os.path.splitext(filename)[0].strip()

    from PIL import Image as PILImage, ImageFilter
    
    # 마스크 복사
    assert os.path.exists(mask_path), f"마스크 파일 없음: {repr(mask_path)}"
    mask_filename   = os.path.basename(mask_path)
    mask_input_path = os.path.join(COMFY_INPUT, mask_filename)
    if os.path.normpath(mask_path) != os.path.normpath(mask_input_path):
        shutil.copy2(mask_path, mask_input_path)
    if not wait_for_file_ready(mask_input_path):
        raise TimeoutError("마스크 파일 I/O 대기 시간 초과")


    # 마스크 페더링 (경계 자연스럽게)
    mask_img = PILImage.open(mask_input_path).convert("L")
    mask_img = mask_img.filter(ImageFilter.GaussianBlur(radius=12))
    mask_img.save(mask_input_path)

    # 워크플로우 로드 및 노드 주입
    workflow = load_inpaint_workflow(mode)
    seed = random.randint(1, 1125899906842624)

    if mode == "detail":
        workflow["1"]["inputs"]["image"]  = filename
        workflow["3"]["inputs"]["ckpt_name"] = checkpoint
        if "22" in workflow:
            workflow["22"]["inputs"]["image"]   = mask_filename
            workflow["22"]["inputs"]["channel"] = "red"
        if "18" in workflow: workflow["18"]["inputs"]["text"] = prompt
        if "19" in workflow: workflow["19"]["inputs"]["text"] = negative
        workflow["8"]["inputs"]["seed"]    = seed
        workflow["8"]["inputs"]["steps"]   = steps
        workflow["8"]["inputs"]["denoise"] = denoise
    else:
        workflow["1"]["inputs"]["image"]   = filename
        workflow["2"]["inputs"]["image"]   = mask_filename
        workflow["2"]["inputs"]["channel"] = "red"
        workflow["4"]["inputs"]["text"]    = prompt
        workflow["5"]["inputs"]["text"]    = negative
        workflow["8"]["inputs"]["seed"]    = seed
        workflow["8"]["inputs"]["steps"]   = steps
        workflow["8"]["inputs"]["denoise"] = denoise

    # 출력 prefix (인페인팅 누적 횟수 기반)
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM inpainting WHERE file_name LIKE ?", (f"{origin_stem}_inpainting%",))
    count = cursor.fetchone()[0] + 1
    conn.close()

    output_prefix = f"{origin_stem}_inpainting_{count:04d}"
    workflow["10"]["inputs"]["filename_prefix"] = output_prefix

    before    = time.time()
    prompt_id = _post_workflow(workflow, client_id)
    yield {"type": "progress", "value": 0.05, "text": "인페인팅 큐 등록됨..."}

    ws = websocket.WebSocket()
    ws.connect(f"{COMFY_WS}?clientId={client_id}")
    yield from _ws_progress(ws, start_ratio=0.10, end_ratio=0.95)

    files = glob.glob(os.path.join(COMFY_OUTPUT, f"{output_prefix}*.png"))
    new_files = [f for f in files if os.path.getctime(f) > before]
    if not new_files:
        raise RuntimeError(f"인페인팅 이미지를 찾을 수 없음 (패턴: {output_prefix}*.png)")

    yield {"type": "done", "image_path": max(new_files, key=os.path.getctime)}

# ── i2i ──────────────────────────────────────────────────

def run_i2i(image_path: str, checkpoint: str,
            prompt: str, negative: str = "",
            denoise: float = 0.7, seed: int = -1,
            client_id: str = None):
    if not is_comfy_alive():
        yield {"type": "progress", "value": 0.0, "text": "ComfyUI 시작 중..."}
        start_comfy()
        wait_for_comfy()

    if client_id is None:
        client_id = str(uuid.uuid4())

    filename = os.path.basename(image_path)
    dest = os.path.join(str(COMFY_INPUT), filename)
    if os.path.abspath(image_path) != os.path.abspath(dest):
        shutil.copy2(image_path, dest)

    with open(I2IBASE, "r", encoding="utf-8") as f:
        workflow = json.load(f)

    if seed < 0:
        seed = random.randint(1, 999999999999999)

    workflow["1"]["inputs"]["image"]    = filename
    workflow["6"]["inputs"]["text"]     = prompt
    workflow["7"]["inputs"]["text"]     = negative
    workflow["9"]["inputs"]["ckpt_name"] = checkpoint
    workflow["11"]["inputs"]["seed"]    = seed
    workflow["11"]["inputs"]["denoise"] = denoise

    origin_stem = os.path.splitext(filename)[0].strip()
    output_prefix = f"{origin_stem}_i2i"
    workflow["14"]["inputs"]["filename_prefix"] = output_prefix

    before    = time.time()
    prompt_id = _post_workflow(workflow, client_id)
    yield {"type": "progress", "value": 0.05, "text": "i2i 큐 등록됨..."}

    ws = websocket.WebSocket()
    ws.connect(f"{COMFY_WS}?clientId={client_id}")
    yield from _ws_progress(ws, start_ratio=0.10, end_ratio=0.95)

    files = glob.glob(os.path.join(COMFY_OUTPUT, f"{output_prefix}*.png"))
    new_files = [f for f in files if os.path.getctime(f) > before]
    if not new_files:
        raise RuntimeError(f"i2i 이미지를 찾을 수 없음 (패턴: {output_prefix}*.png)")

    yield {"type": "done", "image_path": max(new_files, key=os.path.getctime)}

    # ── i2i 마스크 ────────────────────────────────────────────

def run_i2i_mask(image_path: str, mask_path: str, checkpoint: str,
                 prompt: str, negative: str = "",
                 denoise: float = 0.5, seed: int = -1,
                 client_id: str = None):
    if not is_comfy_alive():
        yield {"type": "progress", "value": 0.0, "text": "ComfyUI 시작 중..."}
        start_comfy()
        wait_for_comfy()

    if client_id is None:
        client_id = str(uuid.uuid4())

    filename = os.path.basename(image_path)
    dest = os.path.join(str(COMFY_INPUT), filename)
    if os.path.normpath(image_path) != os.path.normpath(dest):
        shutil.copy2(image_path, dest)

    from PIL import Image as PILImage, ImageFilter

    mask_filename = os.path.basename(mask_path)
    mask_input_path = os.path.join(COMFY_INPUT, mask_filename)
    if os.path.normpath(mask_path) != os.path.normpath(mask_input_path):
        shutil.copy2(mask_path, mask_input_path)
    if not wait_for_file_ready(mask_input_path):
        raise TimeoutError("마스크 파일 I/O 대기 시간 초과")

    # 마스크 페더링 (경계 자연스럽게)
    mask_img = PILImage.open(mask_input_path).convert("L")
    mask_img = mask_img.filter(ImageFilter.GaussianBlur(radius=12))
    mask_img.save(mask_input_path)

    with open(I2I_MASK, "r", encoding="utf-8") as f:
        workflow = json.load(f)

    if seed < 0:
        seed = random.randint(1, 999999999999999)

    workflow["1"]["inputs"]["image"]    = filename
    workflow["3"]["inputs"]["ckpt_name"] = checkpoint
    workflow["18"]["inputs"]["text"]    = prompt
    workflow["19"]["inputs"]["text"]    = negative
    workflow["22"]["inputs"]["image"]   = mask_filename
    workflow["8"]["inputs"]["seed"]     = seed
    workflow["8"]["inputs"]["denoise"]  = denoise

    origin_stem = os.path.splitext(filename)[0].strip()
    output_prefix = f"{origin_stem}_i2i_mask"
    workflow["10"]["inputs"]["filename_prefix"] = output_prefix

    before    = time.time()
    prompt_id = _post_workflow(workflow, client_id)
    yield {"type": "progress", "value": 0.05, "text": "i2i 마스크 큐 등록됨..."}

    ws = websocket.WebSocket()
    ws.connect(f"{COMFY_WS}?clientId={client_id}")
    yield from _ws_progress(ws, start_ratio=0.10, end_ratio=0.95)

    files = glob.glob(os.path.join(COMFY_OUTPUT, f"{output_prefix}*.png"))
    new_files = [f for f in files if os.path.getctime(f) > before]
    if not new_files:
        raise RuntimeError(f"i2i 마스크 이미지를 찾을 수 없음 (패턴: {output_prefix}*.png)")

    yield {"type": "done", "image_path": max(new_files, key=os.path.getctime)}