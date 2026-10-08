# api/routers/system.py
import requests
from fastapi import APIRouter
from fastapi.responses import (StreamingResponse, Response, PlainTextResponse)
from pydantic import BaseModel
import mimetypes
from fastapi import HTTPException
import os
from core.system.comfy_manager import is_comfy_alive, start_comfy, kill_comfy, get_vram_info
from config.constants import NEGATIVE_BASE
from pathlib import Path 
from fastapi import UploadFile, File
import json
from core.system.ollama_manager import (
    is_ollama_alive, start_ollama, kill_ollama, get_ollama_vram_info
)
import logging
import re
import time
from collections import deque
from config.PATH import APP_LOG, ERROR_LOG, INCIDENT_DIR

_client_log = logging.getLogger("client")
_client_times = deque(maxlen=30)

router = APIRouter(prefix="/api/system", tags=["system"])

FORGE_URL  = "http://127.0.0.1:8188"
OLLAMA_URL = "http://localhost:11434"


# ── 스키마 ────────────────────────────────────────────────

class SwitchRequest(BaseModel):
    mode: str  # "sd" | "llm"
    llm_model: str = "sorc/qwen3.5-instruct-heretic:9b"


# ── SD / LLM 스위칭 ───────────────────────────────────────

def unload_sd():
    try:
        requests.post(f"{FORGE_URL}/sdapi/v1/unload-checkpoint", timeout=10)
        return True
    except Exception:
        return False


def reload_sd():
    try:
        requests.post(f"{FORGE_URL}/sdapi/v1/reload-checkpoint", timeout=10)
        return True
    except Exception:
        return False


def unload_llm(model: str):
    try:
        requests.post(f"{OLLAMA_URL}/api/generate",
                      json={"model": model, "keep_alive": 0}, timeout=10)
        return True
    except Exception:
        return False


def load_llm(model: str):
    try:
        requests.post(f"{OLLAMA_URL}/api/generate",
                      json={"model": model, "keep_alive": -1, "prompt": ""}, timeout=30)
        return True
    except Exception:
        return False


# ── 엔드포인트 ────────────────────────────────────────────

@router.post("/switch")
def switch_mode(req: SwitchRequest):
    """
    mode=sd  → LLM 언로드 + SD 로드
    mode=llm → SD 언로드 + LLM 로드
    """
    if req.mode == "sd":
        unload_llm(req.llm_model)
        reload_sd()
        return {"mode": "sd", "ok": True}
    elif req.mode == "llm":
        unload_sd()
        load_llm(req.llm_model)
        return {"mode": "llm", "ok": True}
    else:
        return {"ok": False, "error": "mode는 'sd' 또는 'llm'"}


@router.get("/status")
def system_status():
    sd_alive = False
    llm_alive = False

    try:
        requests.get(f"{FORGE_URL}/sdapi/v1/options", timeout=2)
        sd_alive = True
    except requests.RequestException:
        pass

    llm_alive = is_ollama_alive()

    return {"sd": sd_alive, "llm": llm_alive}


@router.get("/image")
def serve_image(path: str):
    normalized = os.path.normpath(path)
    if not os.path.exists(normalized):
        raise HTTPException(status_code=404, detail=f"파일 없음: {normalized}")
    
    mime, _ = mimetypes.guess_type(normalized)
    with open(normalized, "rb") as f:
        data = f.read()
    
    return Response(
        content=data,
        media_type=mime or "image/png",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=31536000, immutable",
            "Vary": "Origin",
        }
    )

@router.post("/comfy/start")
def comfy_start():
    start_comfy()
    return {"ok": True}


@router.post("/comfy/kill")
def comfy_kill():
    kill_comfy()
    return {"ok": True}


@router.get("/vram")
def vram_status():
    return get_vram_info() or {"used_gb": 0, "total_gb": 0, "percent": 0}


@router.get("/constants")
def get_constants():
    return {"negative_base": NEGATIVE_BASE}


@router.post("/comfy/unload")
def comfy_unload():
    try:
        res = requests.post(
            f"{FORGE_URL}/free",
            json={
                "unload_models": True,
                "free_memory": True
            },
            timeout=10
        )

        return {
            "ok": res.ok,
            "status": res.status_code
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e)
        }

@router.get("/tags/{filename}")
def get_tag_json(filename: str):
    import json as json_lib
    # 경로 traversal 방지
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="invalid filename")
    tag_dir = Path("D:/Python/AISystem/assets/tag/json")
    path = tag_dir / filename
    if not path.exists() or path.suffix != ".json":
        raise HTTPException(status_code=404, detail="not found")
    with open(path, encoding="utf-8") as f:
        return json_lib.load(f)

@router.get("/tags")
def list_tag_files():
    tag_dir = Path("D:/Python/AISystem/assets/tag/json")
    files = [p.name for p in tag_dir.glob("*.json")]
    return {"files": sorted(files)}

class RevealRequest(BaseModel):
    path: str
@router.post("/reveal")
def reveal_in_explorer(req: RevealRequest):
    """탐색기에서 해당 파일을 선택한 상태로 열기 (서버 PC에서 열림, Windows 전용)"""
    import subprocess
    from config.PATH import COMFY_DIR

    target = Path(os.path.normpath(req.path)).resolve()
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"파일 없음: {target}")
    if not target.is_relative_to(Path(COMFY_DIR).resolve()):
        raise HTTPException(status_code=403, detail="ComfyUI 폴더 밖의 경로는 열 수 없음")

    # explorer는 성공해도 종료 코드가 1이라 check하지 않음
    subprocess.Popen(f'explorer /select,"{target}"')
    return {"ok": True}

@router.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    """이미지를 COMFY_INPUT에 저장하고 경로 반환"""
    from config.PATH import COMFY_INPUT
    import shutil

    # 확장자 체크
    if not file.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
        raise HTTPException(status_code=400, detail="이미지 파일만 업로드 가능합니다")

    save_path = os.path.join(COMFY_INPUT, file.filename)
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    return {"path": save_path, "filename": file.filename}

# @router.get("/comfy/start-stream")
# def comfy_start_stream():
#     from core.system.comfy_manager import start_comfy, get_comfy_log_queue, is_comfy_alive
#     import queue as _queue

#     def stream():
#         start_comfy()
#         log_queue = get_comfy_log_queue()
#         yield f"event: log\ndata: {json.dumps({'text': 'ComfyUI 시작 중...'})}\n\n"

#         while True:
#             alive = is_comfy_alive()
#             try:
#                 line = log_queue.get(timeout=1)
#                 yield f"event: log\ndata: {json.dumps({'text': line})}\n\n"
#             except _queue.Empty:
#                 pass

#             if alive:
#                 yield f"event: done\ndata: {json.dumps({'text': 'ComfyUI 시작 완료'})}\n\n"
#                 break
#     return StreamingResponse(stream(), media_type="text/event-stream")
@router.get("/comfy/start-stream")
def comfy_start_stream():
    import time
    from core.system.comfy_manager import start_comfy

    def stream():
        start_comfy()
        yield f"event: log\ndata: {json.dumps({'text': 'ComfyUI 시작 중...'})}\n\n"
        while not is_comfy_alive():
            time.sleep(1)
        yield f"event: done\ndata: {json.dumps({'text': 'ComfyUI 시작 완료'})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")

@router.get("/video")
def serve_video(path: str):
    normalized = os.path.normpath(path)
    if not os.path.exists(normalized):
        raise HTTPException(status_code=404, detail=f"파일 없음: {normalized}")
    
    mime, _ = mimetypes.guess_type(normalized)
    with open(normalized, "rb") as f:
        data = f.read()
    
    return Response(
        content=data,
        media_type=mime or "video/mp4",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache",
        }
    )

@router.post("/ollama/start")
def ollama_start():
    start_ollama()
    return {"ok": True}


@router.post("/ollama/kill")
def ollama_kill():
    kill_ollama()
    return {"ok": True}


@router.get("/ollama/vram")
def ollama_vram():
    return get_ollama_vram_info() or {"used_gb": 0, "model": None}

@router.post("/ollama/unload-model")
def ollama_unload_model(model: str = "sorc/qwen3.5-instruct-heretic:9b"):
    ok = unload_llm(model)
    return {"ok": ok}

# ── 로그 ──────────────────────────────────────────────────

class ClientLog(BaseModel):
    level: str = "error"          # error | warn | info
    message: str
    stack: str | None = None
    url: str | None = None
    breadcrumbs: list[str] = []


@router.post("/client-log")
def post_client_log(req: ClientLog):
    """프론트 오류·API 실패를 서버 로그 파일에 기록"""
    now = time.time()
    if len(_client_times) == _client_times.maxlen and now - _client_times[0] < 60:
        return {"ok": True, "dropped": True}          # 폭주 방지: 60초에 30건
    _client_times.append(now)

    lvl = {"error": logging.ERROR, "warn": logging.WARNING}.get(req.level, logging.INFO)
    parts = [req.message[:2000]]
    if req.url:
        parts.append(f"url={req.url[:300]}")
    if req.breadcrumbs:
        parts.append("breadcrumbs:\n  " + "\n  ".join(b[:200] for b in req.breadcrumbs[-20:]))
    if req.stack:
        parts.append("stack:\n" + req.stack[:5000])
    _client_log.log(lvl, "\n".join(parts))
    return {"ok": True}


def _tail_lines(path: Path, n: int, max_bytes: int = 2_000_000) -> list[str]:
    if not path.exists():
        return []
    size = path.stat().st_size
    with open(path, "rb") as f:
        f.seek(max(0, size - max_bytes))
        data = f.read().decode("utf-8", errors="replace")
    return data.splitlines()[-n:]


@router.get("/logs/tail", response_class=PlainTextResponse)
def logs_tail(lines: int = 200, file: str = "app"):
    """file=app(전체) | error(WARNING 이상). 채팅에 붙여넣기용 텍스트"""
    path = Path(ERROR_LOG if file == "error" else APP_LOG)
    return "\n".join(_tail_lines(path, min(max(lines, 1), 2000)))


@router.get("/logs/incidents")
def logs_incidents(limit: int = 20):
    if not Path(INCIDENT_DIR).exists():
        return {"incidents": []}
    files = sorted(Path(INCIDENT_DIR).glob("*.log"), reverse=True)[:limit]
    return {"incidents": [f.name for f in files]}


@router.get("/logs/incidents/{name}", response_class=PlainTextResponse)
def logs_incident(name: str):
    if not re.fullmatch(r"[0-9A-Za-z_\-]+\.log", name):
        raise HTTPException(status_code=400, detail="invalid name")
    path = Path(INCIDENT_DIR) / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="not found")
    return path.read_text(encoding="utf-8", errors="replace")