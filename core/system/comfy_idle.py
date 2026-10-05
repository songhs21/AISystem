# core/system/comfy_idle.py
import threading
import time
import requests
from config.PATH import COMFY_URL
from core.system.comfy_manager import is_comfy_alive

IDLE_UNLOAD_SEC = 300   # ComfyUI에 작업이 없는 채로 이 시간이 지나면 모델 언로드
POLL_SEC = 30

unloaded_event = threading.Event()   # 언로드 완료 시 set → memory_worker가 깨어남

_lock = threading.Lock()
_loaded = False
_last_busy = time.time()
_started = False


def mark_busy():
    """ComfyUI에 작업을 제출하기 직전에 호출. 모델이 올라갈 것이므로 로드 상태로 본다."""
    global _loaded, _last_busy
    with _lock:
        _loaded = True
        _last_busy = time.time()


def models_unloaded() -> bool:
    if not is_comfy_alive():
        return True          # 프로세스가 없으면 VRAM에 모델이 없음
    with _lock:
        return not _loaded


def _queue_busy():
    """True / False, 확인 불가면 None"""
    try:
        d = requests.get(f"{COMFY_URL}/queue", timeout=2).json()
        return bool(d.get("queue_running")) or bool(d.get("queue_pending"))
    except Exception:
        return None


def unload_now() -> bool:
    global _loaded
    if not is_comfy_alive():
        with _lock:
            _loaded = False
        unloaded_event.set()
        return True
    if _queue_busy() is not False:
        return False
    try:
        r = requests.post(
            f"{COMFY_URL}/free",
            json={"unload_models": True, "free_memory": True},
            timeout=10,
        )
        if not r.ok:
            return False
    except Exception as e:
        print(f"[COMFY] 언로드 실패: {e}")
        return False
    with _lock:
        _loaded = False
    print("[COMFY] 모델 언로드 완료")
    unloaded_event.set()
    return True


def _loop():
    global _loaded, _last_busy
    while True:
        time.sleep(POLL_SEC)
        try:
            if not is_comfy_alive():
                with _lock:
                    _loaded = False
                continue
            busy = _queue_busy()
            now = time.time()
            if busy:
                with _lock:
                    _loaded = True
                    _last_busy = now
                continue
            with _lock:
                due = _loaded and busy is False and now - _last_busy >= IDLE_UNLOAD_SEC
            if due:
                unload_now()
        except Exception as e:
            print(f"[COMFY] 유휴 감시 오류: {e}")


def start():
    global _loaded, _last_busy, _started
    if _started:
        return
    _started = True
    with _lock:
        _loaded = is_comfy_alive()     # 서버 시작 시 이미 켜져 있으면 로드된 것으로 간주
        _last_busy = time.time()
    threading.Thread(target=_loop, daemon=True).start()