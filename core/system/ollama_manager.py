# core/system/ollama_manager.py
import subprocess
import time
import requests
import psutil
from config.PATH import OLLAMA_APP_PATH

OLLAMA_URL = "http://localhost:11434"


def is_ollama_alive() -> bool:
    try:
        requests.get(f"{OLLAMA_URL}/api/tags", timeout=1)
        return True
    except requests.RequestException:
        return False


def start_ollama():
    if is_ollama_alive():
        return
    subprocess.Popen(
        [str(OLLAMA_APP_PATH)],
        creationflags=subprocess.CREATE_NO_WINDOW
    )


def kill_ollama():
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            name = (proc.info['name'] or '').lower()
            if name in ('ollama.exe', 'ollama app.exe'):
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def wait_for_ollama(timeout: int = 30):
    start = time.time()
    while not is_ollama_alive():
        if time.time() - start > timeout:
            raise TimeoutError("Ollama 시작 시간 초과")
        time.sleep(1)


def get_ollama_vram_info() -> dict | None:
    """Ollama /api/ps로 로드된 모델의 VRAM 점유량 조회"""
    try:
        res = requests.get(f"{OLLAMA_URL}/api/ps", timeout=2)
        data = res.json()
        models = data.get("models", [])
        if not models:
            return {"used_gb": 0, "total_gb": 0, "percent": 0, "model": None}
        # 여러 모델 로드 가능하지만 보통 1개 — 합산
        used = sum(m.get("size_vram", 0) for m in models)
        return {
            "used_gb": round(used / 1024 ** 3, 1),
            "model": models[0].get("name"),
        }
    except:
        return None