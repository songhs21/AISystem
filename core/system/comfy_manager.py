# core/system/comfy_manager.py
import os
import subprocess
import time
import requests
import psutil
from config.PATH import COMFY_DIR, PYTHON_EMBEDED, COMFY_URL

_comfy_process = None

def is_comfy_alive() -> bool:
    try:
        requests.get(f"{COMFY_URL}/system_stats", timeout=1)
        return True
    except:
        return False


def start_comfy():
    global _comfy_process

    # 이미 실행 중이면 다시 실행하지 않음
    if is_comfy_alive():
        return

    main_py = os.path.join(COMFY_DIR, "main.py")

    _comfy_process = subprocess.Popen(
        [PYTHON_EMBEDED, main_py],
        cwd=COMFY_DIR,
        creationflags=subprocess.CREATE_NO_WINDOW
    )

def kill_comfy():
    global _comfy_process
    if _comfy_process:
        _comfy_process.kill()
        _comfy_process = None

def wait_for_comfy(timeout: int = 60):
    start = time.time()
    while not is_comfy_alive():
        if time.time() - start > timeout:
            raise TimeoutError("ComfyUI 시작 시간 초과")
        time.sleep(2)

def ensure_comfy_running():
    """ComfyUI 미실행 시 자동 기동 + 대기. 제너레이터용 progress 없음."""
    if not is_comfy_alive():
        start_comfy()
        wait_for_comfy()

def get_vram_info() -> dict:
    """ComfyUI system_stats에서 VRAM 수치 조회"""
    try:
        res = requests.get(f"{COMFY_URL}/system_stats", timeout=1)
        data = res.json()
        devices = data.get("devices", [])
        if not devices:
            return {"used": 0, "total": 0, "percent": 0}
        gpu = devices[0]
        total = gpu.get("vram_total", 0)
        free  = gpu.get("vram_free", 0)
        used  = total - free
        percent = round(used / total * 100) if total > 0 else 0
        return {
            "used_gb":  round(used  / 1024 ** 3, 1),
            "total_gb": round(total / 1024 ** 3, 1),
            "percent":  percent,
        }
    except:
        return None