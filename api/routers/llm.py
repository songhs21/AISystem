# api/routers/llm.py
import time
import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from core.llm_db import get_conn, init_llm_db
import base64
import os
import json
from fastapi.responses import StreamingResponse
import logging
from pathlib import Path
from core.llm.llm_memory import extract_session, list_memories, delete_memory
router = APIRouter(prefix="/api/llm", tags=["llm"])

OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "sorc/qwen3.5-instruct-heretic:9b"
_log_path = Path(__file__).resolve().parent.parent.parent / "data" / "logs" / "llm_debug.log"
_log_path.parent.mkdir(parents=True, exist_ok=True)
_llm_logger = logging.getLogger("llm_debug")
_llm_logger.setLevel(logging.INFO)
if not _llm_logger.handlers:
    _fh = logging.FileHandler(_log_path, encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _llm_logger.addHandler(_fh)

class ChatRequest(BaseModel):
    message: str
    session_id: int = 1
    model: str = DEFAULT_MODEL
    image_path: str | None = None
    use_history_images: bool = False
    max_history_images: int = 2

class ChatResponse(BaseModel):
    reply: str
    elapsed_ms: int
    model: str

class SessionOut(BaseModel):
    id: int
    title: str
    model: str
    created_at: str

class SessionUpdate(BaseModel):
    title: str


def _ensure_session(session_id: int, model: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM chat_sessions WHERE id = ?", (session_id,))
    exists = cur.fetchone()
    conn.close()
    if not exists:
        raise HTTPException(status_code=404, detail=f"세션 {session_id}을(를) 찾을 수 없음")


def _get_history(session_id: int) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT role, content, elapsed_ms, image_path FROM chat_messages WHERE session_id = ? ORDER BY id",
        (session_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {"role": r, "content": c, "elapsed_ms": e, "image_path": i}
        for r, c, e, i in rows
    ]

def _save_message(session_id: int, role: str, content: str, model: str,
                  elapsed_ms: int = 0, image_path: str | None = None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO chat_messages (session_id, role, content, model, elapsed_ms, image_path)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (session_id, role, content, model, elapsed_ms, image_path),
    )
    conn.commit()
    conn.close()


@router.get("/history/{session_id}")
def get_history(session_id: int):
    return {"messages": _get_history(session_id)}


@router.post("/sessions", response_model=SessionOut)
def create_session(model: str = DEFAULT_MODEL):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO chat_sessions (title, model) VALUES (?, ?)",
        ("New Chat", model),
    )
    session_id = cur.lastrowid
    conn.commit()
    cur.execute("SELECT id, title, model, created_at FROM chat_sessions WHERE id = ?", (session_id,))
    row = cur.fetchone()
    conn.close()
    return SessionOut(id=row[0], title=row[1], model=row[2], created_at=row[3])


@router.get("/sessions")
def list_sessions():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, title, model, created_at FROM chat_sessions ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "model": r[2], "created_at": r[3]} for r in rows]


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    init_llm_db()
    _ensure_session(req.session_id, req.model)

    history = _get_history(req.session_id)

    # 과거 이미지 중 최신 N개만 문맥에 포함 (use_history_images가 켜진 경우)
    allowed_idx = set()
    if req.use_history_images and req.max_history_images > 0:
        img_idx = [i for i, h in enumerate(history) if h["image_path"]]
        allowed_idx = set(img_idx[-req.max_history_images:])

    ollama_messages = []
    for i, h in enumerate(history):
        msg = {"role": h["role"], "content": h["content"]}
        if i in allowed_idx:
            enc = _encode_image(h["image_path"])
            if enc:
                msg["images"] = [enc]
        ollama_messages.append(msg)

    user_msg = {"role": "user", "content": req.message}
    if req.image_path:
        enc = _encode_image(req.image_path)
        if enc is None:
            raise HTTPException(status_code=400, detail=f"이미지 파일 없음: {req.image_path}")
        user_msg["images"] = [enc]
    ollama_messages.append(user_msg)

    start = time.time()
    try:
        resp = requests.post(
            OLLAMA_URL,
                json={
                    "model": req.model,
                    "messages": ollama_messages,
                    "stream": True,
                    "options": {"num_ctx": 8192, "num_predict": -1},
                },
            timeout=300,
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Ollama 호출 실패: {e}")

    elapsed_ms = int((time.time() - start) * 1000)
    reply = resp.json()["message"]["content"]

    _save_message(req.session_id, "user", req.message, req.model, image_path=req.image_path)
    _save_message(req.session_id, "assistant", reply, req.model, elapsed_ms)

    return ChatResponse(reply=reply, elapsed_ms=elapsed_ms, model=req.model)

@router.post("/chat-stream")
def chat_stream(req: ChatRequest):
    """
    스트리밍 채팅 — SSE
    event: token → {"text": str}
    event: done  → {"elapsed_ms": int, "model": str}
    event: error → {"message": str}
    """
    init_llm_db()
    _ensure_session(req.session_id, req.model)

    history = _get_history(req.session_id)

    allowed_idx = set()
    if req.use_history_images and req.max_history_images > 0:
        img_idx = [i for i, h in enumerate(history) if h["image_path"]]
        allowed_idx = set(img_idx[-req.max_history_images:])

    ollama_messages = []
    for i, h in enumerate(history):
        msg = {"role": h["role"], "content": h["content"]}
        if i in allowed_idx:
            enc = _encode_image(h["image_path"])
            if enc:
                msg["images"] = [enc]
        ollama_messages.append(msg)

    user_msg = {"role": "user", "content": req.message}
    if req.image_path:
        enc = _encode_image(req.image_path)
        if enc is None:
            raise HTTPException(status_code=400, detail=f"이미지 파일 없음: {req.image_path}")
        user_msg["images"] = [enc]
    ollama_messages.append(user_msg)

    def stream():
        start = time.time()
        collected = []
        try:
            with requests.post(
                OLLAMA_URL,
                json={
                    "model": req.model,
                    "messages": ollama_messages,
                    "stream": True,
                    "options": {"num_ctx": 8192},
                },
                stream=True,
                timeout=300,
            ) as resp:
                if not resp.ok:
                    error_body = resp.text
                    _llm_logger.error(
                        f"Ollama HTTP {resp.status_code}: {error_body}"
                    )
                    raise requests.exceptions.HTTPError(
                        f"Ollama HTTP {resp.status_code}: {error_body}"
                    )
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        collected.append(token)
                        yield f"event: token\ndata: {json.dumps({'text': token})}\n\n"
                    if chunk.get("done"):
                        _llm_logger.info(
                            f"done_reason={chunk.get('done_reason')}, "
                            f"prompt_eval_count={chunk.get('prompt_eval_count')}, "
                            f"eval_count={chunk.get('eval_count')}"
                        )
                        break

            elapsed_ms = int((time.time() - start) * 1000)
            yield f"event: done\ndata: {json.dumps({'elapsed_ms': elapsed_ms, 'model': req.model})}\n\n"

        except requests.exceptions.RequestException as e:
            yield f"event: error\ndata: {json.dumps({'message': f'Ollama 호출 실패: {e}'})}\n\n"
        finally:
            # 정상 종료, 오류, 클라이언트 연결 끊김 모두 여기서 저장
            reply = "".join(collected)
            if reply:
                elapsed_ms = int((time.time() - start) * 1000)
                _save_message(req.session_id, "user", req.message, req.model, image_path=req.image_path)
                _save_message(req.session_id, "assistant", reply, req.model, elapsed_ms)

    return StreamingResponse(stream(), media_type="text/event-stream")

@router.delete("/sessions/{session_id}")
def delete_session(session_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
    cur.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.patch("/sessions/{session_id}", response_model=SessionOut)
def rename_session(session_id: int, req: SessionUpdate):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE chat_sessions SET title = ? WHERE id = ?", (req.title, session_id))
    conn.commit()
    cur.execute("SELECT id, title, model, created_at FROM chat_sessions WHERE id = ?", (session_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없음")
    return SessionOut(id=row[0], title=row[1], model=row[2], created_at=row[3])

def _encode_image(path: str) -> str | None:
    normalized = os.path.normpath(path)
    if not os.path.exists(normalized):
        return None
    with open(normalized, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

# 대화 세션 추출
@router.post("/sessions/{session_id}/extract")
def extract_memories(session_id: int, model: str = DEFAULT_MODEL):
    """세션의 미추출 대화를 한 묶음 추출. remaining > 0이면 다시 호출해 이어서 처리."""
    try:
        return extract_session(session_id, model)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Ollama 호출 실패: {e}")


@router.get("/memories")
def get_memories(category: str | None = None, only_unreviewed: bool = False):
    return {"memories": list_memories(category, only_unreviewed)}


@router.delete("/memories/{memory_id}")
def remove_memory(memory_id: int):
    delete_memory(memory_id)
    return {"ok": True}