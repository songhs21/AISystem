# core/system/gen_queue.py
import os
import threading
import time
import uuid
import requests
from config.PATH import COMFY_URL
import subprocess

MAX_FINISHED = 10  # 메모리에 유지할 완료/실패 항목 수
SHUTDOWN_DELAY_SEC = 60  # 큐 완료 후 PC 종료까지 유예 시간

class GenerationCancelled(Exception):
    """사용자가 생성을 취소함"""


_items: list[dict] = []
_cv = threading.Condition()
_runners: dict = {}
_worker_started = False


def register_runner(kind: str, fn):
    """fn(payload) -> 제너레이터. yield {"type": "progress", value, text} / {"type": "done", ...}"""
    _runners[kind] = fn


def enqueue(kind: str, payload: dict, summary: dict, cleanup: list | None = None) -> str:
    item = {
        "id": uuid.uuid4().hex[:12],
        "kind": kind,
        "status": "waiting",   # waiting | running | done | error
        "progress": 0.0,
        "text": "대기 중",
        "payload": payload,
        "summary": summary,
        "result": None,
        "error": None,
        "cancel": False,
        "cleanup": cleanup or [],
        "created_at": time.time(),
    }
    with _cv:
        _items.append(item)
        _start_worker_once()
        _cv.notify()
    return item["id"]


def snapshot() -> list[dict]:
    with _cv:
        out = []
        for i in _items:
            status = i["status"]
            if status == "running" and i["cancel"]:
                status = "cancelling"
            out.append({
                "id": i["id"], "kind": i["kind"], "status": status,
                "progress": i["progress"], "text": i["text"],
                "summary": i["summary"], "result": i["result"],
                "error": i["error"], "created_at": i["created_at"],
            })
        return out


def remove(item_id: str) -> str:
    """대기: 제거 / 실행 중: 중단 요청 / 완료·실패: 목록에서 제거"""
    global _shutdown_armed
    with _cv:
        item = next((i for i in _items if i["id"] == item_id), None)
        if item is None:
            return "not_found"
        if item["status"] == "running":
            item["cancel"] = True
            _shutdown_armed = False   # 실행 중 작업을 직접 취소하면 PC 종료 예약 해제
            running = True
        else:
            _items.remove(item)
            running = False
    if running:
        _interrupt()
        return "cancelling"
    _cleanup(item)
    return "removed"


def clear_pending() -> int:
    """대기 항목 전부 제거 + 실행 중 항목 중단 (PC 종료 예약도 해제)"""
    global _shutdown_armed
    removed, running = [], False
    with _cv:
        _shutdown_armed = False
        for i in list(_items):
            if i["status"] == "waiting":
                _items.remove(i)
                removed.append(i)
            elif i["status"] == "running":
                i["cancel"] = True
                running = True
    for i in removed:
        _cleanup(i)
    if running:
        _interrupt()
    return len(removed) + (1 if running else 0)

def set_shutdown(enabled: bool):
    global _shutdown_armed
    with _cv:
        _shutdown_armed = bool(enabled)

# 시스템 종료 로직
def shutdown_state() -> dict:
    with _cv:
        remaining = 0
        if _shutdown_at is not None:
            remaining = max(0, int(SHUTDOWN_DELAY_SEC - (time.time() - _shutdown_at)))
        return {"armed": _shutdown_armed, "remaining": remaining}


def abort_shutdown() -> bool:
    """예약 해제 + 이미 걸린 종료 취소"""
    global _shutdown_armed, _shutdown_at
    with _cv:
        _shutdown_armed = False
        was_scheduled = _shutdown_at is not None
        _shutdown_at = None
    if was_scheduled:
        try:
            subprocess.run(["shutdown", "/a"], check=False)
        except Exception as e:
            print(f"[QUEUE] 종료 취소 실패: {e}")
    return was_scheduled


def _maybe_shutdown():
    global _shutdown_armed, _shutdown_at
    with _cv:
        if not _shutdown_armed:
            return
        if any(i["status"] in ("waiting", "running") for i in _items):
            return
        _shutdown_armed = False
        _shutdown_at = time.time()
    try:
        subprocess.run(["shutdown", "/s", "/t", str(SHUTDOWN_DELAY_SEC)], check=True)
    except Exception as e:
        print(f"[QUEUE] PC 종료 예약 실패: {e}")
        with _cv:
            _shutdown_at = None
# ── 내부 ──────────────────────────────────────────────────

def _start_worker_once():
    global _worker_started
    if not _worker_started:
        _worker_started = True
        threading.Thread(target=_worker, daemon=True).start()


def _interrupt():
    try:
        requests.post(f"{COMFY_URL}/interrupt", timeout=5)
    except Exception as e:
        print(f"[QUEUE] interrupt 실패: {e}")


def _cleanup(item: dict):
    for path in item.get("cleanup", []):
        try:
            os.remove(path)
        except Exception:
            pass

_shutdown_armed = False
_shutdown_at = None
def _worker():
    while True:
        with _cv:
            while not any(i["status"] == "waiting" for i in _items):
                _cv.wait()
            item = next(i for i in _items if i["status"] == "waiting")
            item["status"] = "running"
            item["text"] = "시작 중..."
        _run_item(item)
        _maybe_shutdown()


def _run_item(item: dict):
    gen = None
    try:
        runner = _runners.get(item["kind"])
        if runner is None:
            raise RuntimeError(f"알 수 없는 작업 종류: {item['kind']}")
        gen = runner(item["payload"])
        result = None
        for ev in gen:
            if item["cancel"]:
                _interrupt()
                raise GenerationCancelled()
            if ev["type"] == "progress":
                with _cv:
                    item["progress"] = ev["value"]
                    item["text"] = ev["text"]
            elif ev["type"] == "done":
                result = {k: v for k, v in ev.items() if k != "type"}
        if result is None:
            raise RuntimeError("결과를 받지 못함")
        _finish(item, "done", result=result)
    except GenerationCancelled:
        _finish(item, "cancelled")
    except Exception as e:
        if item["cancel"]:
            _finish(item, "cancelled")
        else:
            _finish(item, "error", error=str(e))
    finally:
        if gen is not None:
            try:
                gen.close()
            except Exception:
                pass


def _finish(item: dict, status: str, result=None, error=None):
    _cleanup(item)
    with _cv:
        if status == "cancelled":
            if item in _items:
                _items.remove(item)
            return
        item["status"] = status
        item["result"] = result
        item["error"] = error
        item["text"] = "완료!" if status == "done" else "실패"
        if status == "done":
            item["progress"] = 1.0
        finished = [i for i in _items if i["status"] in ("done", "error")]
        for old in finished[:-MAX_FINISHED]:
            _items.remove(old)