# core/system/comfy_manager.py
import os
import subprocess
import time
import requests
import psutil
from config.PATH import COMFY_DIR, PYTHON_EMBEDED, COMFY_URL
import queue
_comfy_log_queue = queue.Queue()

_comfy_process = None

def is_comfy_alive() -> bool:
    try:
        requests.get(f"{COMFY_URL}/system_stats", timeout=1)
        return True
    except:
        return False


def start_comfy():
    global _comfy_process
    if is_comfy_alive():
        return

    main_py = os.path.join(COMFY_DIR, "main.py")

    _comfy_process = subprocess.Popen(
        [PYTHON_EMBEDED, main_py],
        cwd=COMFY_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW
    )

    # stdout을 별도 스레드에서 읽어 큐에 적재
    def _read_stdout():
        for line in _comfy_process.stdout:
            try:
                _comfy_log_queue.put(line.decode('utf-8', errors='replace').rstrip())
            except Exception:
                break

    import threading
    threading.Thread(target=_read_stdout, daemon=True).start()

def get_comfy_log_queue():
    return _comfy_log_queue

def kill_comfy():
    global _comfy_process
    # 직접 띄운 프로세스 종료
    if _comfy_process:
        _comfy_process.kill()
        _comfy_process = None

    # 포트 8188 점유 프로세스 강제 종료 (외부 실행된 경우 대비)
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'connections']):
            try:
                for conn in proc.connections():
                    if conn.laddr.port == 8188:
                        proc.kill()
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception as e:
        pass

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