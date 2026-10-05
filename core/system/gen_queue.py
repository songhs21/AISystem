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
SHUTDOWN_MAX_BATCHES = 10  # 종료 예약 시 PC 종료 전에 처리할 메모리 추출 묶음 상한

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
    """대기 항목 전부 제거 + 실행 중 항목 중단 (PC 종료 예약·종료 전 추출도 해제)"""
    global _shutdown_armed, _shutdown_prep_cancel
    removed, running = [], False
    with _cv:
        _shutdown_armed = False
        if _shutdown_prep:
            _shutdown_prep_cancel = True
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


def reorder(ids: list[str]) -> bool:
    """대기 중인 항목만 ids 순서대로 재배치. ids에 없는 대기 항목은 뒤에 유지."""
    with _cv:
        waiting = [i for i in _items if i["status"] == "waiting"]
        by_id = {i["id"]: i for i in waiting}
        ordered, seen = [], set()
        for x in ids:
            if x in by_id and x not in seen:
                ordered.append(by_id[x])
                seen.add(x)
        ordered += [i for i in waiting if i["id"] not in seen]
        it = iter(ordered)
        for idx, item in enumerate(_items):
            if item["status"] == "waiting":
                _items[idx] = next(it)
        return True
    
def set_shutdown(enabled: bool):
    global _shutdown_armed, _shutdown_prep_cancel
    with _cv:
        _shutdown_armed = bool(enabled)
        if not enabled and _shutdown_prep:
            _shutdown_prep_cancel = True


def shutdown_state() -> dict:
    with _cv:
        remaining = 0
        if _shutdown_at is not None:
            remaining = max(0, int(SHUTDOWN_DELAY_SEC - (time.time() - _shutdown_at)))
        return {
            "armed": _shutdown_armed,
            "remaining": remaining,
            "extracting": _shutdown_prep,
            "batches": _prep_batches,
            "max_batches": SHUTDOWN_MAX_BATCHES,
        }


def abort_shutdown() -> bool:
    """예약 해제 + 종료 전 추출 중단 + 이미 걸린 종료 취소"""
    global _shutdown_armed, _shutdown_at, _shutdown_prep_cancel
    with _cv:
        _shutdown_armed = False
        was_scheduled = _shutdown_at is not None
        was_prep = _shutdown_prep
        if was_prep:
            _shutdown_prep_cancel = True
        _shutdown_at = None
    if was_scheduled:
        try:
            subprocess.run(["shutdown", "/a"], check=False)
        except Exception as e:
            print(f"[QUEUE] 종료 취소 실패: {e}")
    return was_scheduled or was_prep


def _maybe_shutdown():
    global _shutdown_armed, _shutdown_prep, _shutdown_prep_cancel, _prep_batches
    with _cv:
        if not _shutdown_armed or _shutdown_prep:
            return
        if any(i["status"] in ("waiting", "running") for i in _items):
            return
        _shutdown_armed = False
        _shutdown_prep = True
        _shutdown_prep_cancel = False
        _prep_batches = 0
    threading.Thread(target=_shutdown_sequence, daemon=True).start()

def _shutdown_sequence():
    """큐 완료 → 모델 즉시 언로드 → 메모리 추출(상한) → PC 종료 예약"""
    global _shutdown_prep, _shutdown_at, _shutdown_armed, _prep_batches
    try:
        from core.system import comfy_idle
        from core.llm import memory_worker

        def should_abort():
            with _cv:
                return _shutdown_prep_cancel or any(
                    i["status"] in ("waiting", "running") for i in _items
                )

        def on_batch(n):
            global _prep_batches
            with _cv:
                _prep_batches = n

        comfy_idle.unload_now()
        memory_worker.run_extraction(
            max_batches=SHUTDOWN_MAX_BATCHES, ignore_idle=True,
            should_abort=should_abort, on_batch=on_batch,
        )
    except Exception as e:
        print(f"[QUEUE] 종료 전 메모리 추출 실패: {e}")

    with _cv:
        _shutdown_prep = False
        _prep_batches = 0
        if _shutdown_prep_cancel:
            return
        if any(i["status"] in ("waiting", "running") for i in _items):
            _shutdown_armed = True     # 새 작업이 들어왔으니 그 작업이 끝난 뒤 다시 시도
            return
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


def _before_run(item: dict):
    """LLM 메모리 추출이 진행 중이면 현재 묶음이 끝날 때까지 시작을 지연."""
    try:
        from core.llm import memory_worker

        def on_wait():
            with _cv:
                item["text"] = "LLM 메모리 추출 중 — 묶음 완료 후 시작"

        memory_worker.wait_until_idle(on_wait=on_wait, should_abort=lambda: item["cancel"])
    except Exception as e:
        print(f"[QUEUE] 메모리 추출 대기 실패: {e}")

_shutdown_armed = False
_shutdown_at = None
_shutdown_prep = False          # 종료 전 메모리 추출 진행 중
_shutdown_prep_cancel = False
_prep_batches = 0
def _worker():
    while True:
        with _cv:
            while not any(i["status"] == "waiting" for i in _items):
                _cv.wait()
            item = next(i for i in _items if i["status"] == "waiting")
            item["status"] = "running"
            item["text"] = "시작 중..."
        _before_run(item)
        if item["cancel"]:
            _finish(item, "cancelled")
        else:
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