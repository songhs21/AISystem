# api/routers/system.py
import requests
from fastapi import APIRouter
from pydantic import BaseModel
from fastapi.responses import FileResponse
from fastapi import HTTPException
import os
from core.system.comfy_manager import is_comfy_alive, start_comfy, kill_comfy, get_vram_info
from config.constants import NEGATIVE_BASE
from pathlib import Path

router = APIRouter(prefix="/api/system", tags=["system"])

FORGE_URL  = "http://127.0.0.1:8188"
OLLAMA_URL = "http://localhost:11434"


# ── 스키마 ────────────────────────────────────────────────

class SwitchRequest(BaseModel):
    mode: str  # "sd" | "llm"
    llm_model: str = "qwen3:14b"


# ── SD / LLM 스위칭 ───────────────────────────────────────

def unload_sd():
    try:
        requests.post(f"{FORGE_URL}/sdapi/v1/unload-checkpoint", timeout=10)
        return True
    except Exception as e:
        return False


def reload_sd():
    try:
        requests.post(f"{FORGE_URL}/sdapi/v1/reload-checkpoint", timeout=10)
        return True
    except Exception as e:
        return False


def unload_llm(model: str):
    try:
        requests.post(f"{OLLAMA_URL}/api/generate",
                      json={"model": model, "keep_alive": 0}, timeout=10)
        return True
    except Exception as e:
        return False


def load_llm(model: str):
    try:
        requests.post(f"{OLLAMA_URL}/api/generate",
                      json={"model": model, "keep_alive": -1, "prompt": ""}, timeout=30)
        return True
    except Exception as e:
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
    except:
        pass

    try:
        requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        llm_alive = True
    except:
        pass

    return {"sd": sd_alive, "llm": llm_alive}


@router.get("/image")
def serve_image(path: str):
    # 백슬래시 정규화
    normalized = os.path.normpath(path)
    if not os.path.exists(normalized):
        raise HTTPException(status_code=404, detail=f"파일 없음: {normalized}")
    return FileResponse(normalized)


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