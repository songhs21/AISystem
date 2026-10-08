# core/llm/memory_worker.py
import threading
import time
import requests

from core.llm_db import get_conn
from core.llm.llm_memory import extract_session
from core.system import comfy_idle
from core.system.ollama_manager import is_ollama_alive, start_ollama, wait_for_ollama
import logging
log = logging.getLogger("mem")

EXTRACT_MODEL = "sorc/qwen3.5-instruct-heretic:9b"
OLLAMA_BASE = "http://localhost:11434"
CHAT_IDLE_SEC = 300     # 마지막 대화 이후 이 시간이 지나야 추출 시작
POLL_SEC = 30
BACKOFF_SEC = 600       # 추출 실패 시 재시도 대기

_cv = threading.Condition()
_run_lock = threading.Lock()
_interrupt = threading.Event()
_extracting = False
_active_chats = 0
_last_chat_touch = time.time()
_backoff_until = 0.0
_started = False


# ── 채팅 활동 추적 (llm.py의 chat_stream에서 호출) ─────────

def chat_begin():
    global _active_chats, _last_chat_touch
    with _cv:
        _active_chats += 1
        _last_chat_touch = time.time()


def chat_end():
    global _active_chats, _last_chat_touch
    with _cv:
        _active_chats = max(0, _active_chats - 1)
        _last_chat_touch = time.time()


def chat_idle_seconds() -> float:
    """전체 세션 기준 마지막 대화 이후 경과 시간"""
    with _cv:
        if _active_chats > 0:
            return 0.0
        mem_idle = time.time() - _last_chat_touch
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT strftime('%s','now') - strftime('%s', MAX(created_at)) FROM chat_messages")
    row = cur.fetchone()
    conn.close()
    db_idle = float(row[0]) if row and row[0] is not None else float("inf")
    return min(mem_idle, db_idle)


def pending_session_ids() -> list[int]:
    """extracted_until 이후 메시지가 남아 있는 세션"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.id FROM chat_sessions s
        WHERE EXISTS (
            SELECT 1 FROM chat_messages m
            WHERE m.session_id = s.id AND m.id > COALESCE(s.extracted_until, 0)
        )
        ORDER BY s.id
    """)
    ids = [r[0] for r in cur.fetchall()]
    conn.close()
    return ids


# ── Ollama ────────────────────────────────────────────────

def _ensure_ollama():
    if not is_ollama_alive():
        start_ollama()
        wait_for_ollama()


def _unload_ollama():
    try:
        requests.post(f"{OLLAMA_BASE}/api/generate",
                      json={"model": EXTRACT_MODEL, "keep_alive": 0}, timeout=10)
    except Exception:
        pass


# ── 추출 실행 ─────────────────────────────────────────────

def run_extraction(max_batches: int | None = None, ignore_idle: bool = False,
                   should_abort=None, on_batch=None) -> int:
    """
    미추출 대화를 묶음 단위로 처리하고 처리한 묶음 수를 반환.
    매 묶음 전에 조건(ComfyUI 언로드 상태, 채팅 유휴, 중단 요청)을 다시 확인한다.
    """
    global _extracting, _backoff_until
    if not _run_lock.acquire(blocking=False):
        return 0
    batches = 0
    ollama_ready = False
    try:
        _interrupt.clear()
        while True:
            if max_batches is not None and batches >= max_batches:
                break
            if _interrupt.is_set() or (should_abort and should_abort()):
                break
            if not comfy_idle.models_unloaded():
                break
            if _active_chats > 0:
                break
            if not ignore_idle and chat_idle_seconds() < CHAT_IDLE_SEC:
                break
            ids = pending_session_ids()
            if not ids:
                break
            try:
                if not ollama_ready:
                    _ensure_ollama()
                    ollama_ready = True
                with _cv:
                    _extracting = True
                res = extract_session(ids[0], EXTRACT_MODEL)
                batches += 1
                log.info("세션 %s 묶음 처리: saved=%s remaining=%s", ids[0], res['saved'], res['remaining'])
                if on_batch:
                    on_batch(batches)
            except Exception as e:
                log.exception("추출 실패 session=%s", ids[0])
                _backoff_until = time.time() + BACKOFF_SEC
                break
            finally:
                with _cv:
                    _extracting = False
                    _cv.notify_all()
    finally:
        if batches:
            _unload_ollama()
        _run_lock.release()
    return batches


# ── 생성 시작 전 게이트 (gen_queue에서 호출) ──────────────

def wait_until_idle(on_wait=None, should_abort=None, timeout: float = 1800):
    """
    추출 묶음이 진행 중이면 그 묶음이 끝날 때까지 대기. 이후 묶음은 시작되지 않는다.
    반환 후 ComfyUI를 '로드 상태'로 표시해 추출이 다시 시작되지 않게 한다.
    """
    _interrupt.set()
    waited = False
    start = time.time()
    while True:
        with _cv:
            busy = _extracting
        if not busy:
            break
        if not waited:
            waited = True
            if on_wait:
                on_wait()
        if should_abort and should_abort():
            break
        if time.time() - start > timeout:
            break
        with _cv:
            _cv.wait(timeout=1)
    if waited:
        _unload_ollama()          # 생성 모델이 올라가기 전에 Ollama VRAM 해제
    comfy_idle.mark_busy()


# ── 워커 ──────────────────────────────────────────────────

def _loop():
    while True:
        comfy_idle.unloaded_event.wait(timeout=POLL_SEC)
        comfy_idle.unloaded_event.clear()
        try:
            if time.time() < _backoff_until:
                continue
            run_extraction()
        except Exception as e:
            log.exception("워커 오류")


def start():
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, daemon=True).start()


def status() -> dict:
    return {
        "extracting": _extracting,
        "pending_sessions": len(pending_session_ids()),
        "chat_idle_sec": int(chat_idle_seconds()),
        "comfy_unloaded": comfy_idle.models_unloaded(),
        "backoff_sec": max(0, int(_backoff_until - time.time())),
    }