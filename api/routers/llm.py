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
from core.llm.llm_memory import extract_session, list_memories, delete_memory, update_memory
from core.llm import memory_worker

log = logging.getLogger("llm")
router = APIRouter(prefix="/api/llm", tags=["llm"])

OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "sorc/qwen3.5-instruct-heretic:9b"

class QuoteItem(BaseModel):
    role: str | None = None          # 'user' | 'assistant' | None(이미지 전용)
    content: str = ""
    image_path: str | None = None

class ChatRequest(BaseModel):
    message: str
    session_id: int = 1
    model: str = DEFAULT_MODEL
    image_path: str | None = None
    quotes: list[QuoteItem] = []

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
        "SELECT role, content, elapsed_ms, image_path, quotes FROM chat_messages WHERE session_id = ? ORDER BY id",
        (session_id,),
    )
    rows = cur.fetchall()
    conn.close()
    out = []
    for r, c, e, i, q in rows:
        try:
            quotes = json.loads(q) if q else []
        except Exception:
            quotes = []
        out.append({"role": r, "content": c, "elapsed_ms": e, "image_path": i, "quotes": quotes})
    return out


def _save_message(session_id: int, role: str, content: str, model: str,
                  elapsed_ms: int = 0, image_path: str | None = None,
                  quotes: list[dict] | None = None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO chat_messages (session_id, role, content, model, elapsed_ms, image_path, quotes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (session_id, role, content, model, elapsed_ms, image_path,
         json.dumps(quotes, ensure_ascii=False) if quotes else None),
    )
    conn.commit()
    conn.close()


_ROLE_LABEL = {"user": "나", "assistant": "AI"}


def _build_ollama_messages(req: ChatRequest) -> list[dict]:
    """
    인용 없음 → 전체 텍스트 대화 + 새 메시지 (과거 이미지는 보내지 않음)
    인용 있음 → 인용 텍스트/이미지만 새 메시지에 붙여서 전송 (이전 대화는 보내지 않음)
    이미지 순서: 인용 이미지 → 직접 첨부 이미지
    """
    images: list[str] = []
    quote_img_count = 0
    attach_count = 0
    parts: list[str] = []

    if req.quotes:
        messages = []
        for q in req.quotes:
            if q.content:
                parts.append(f"{_ROLE_LABEL.get(q.role, '인용')}: {q.content}")
            if q.image_path:
                enc = _encode_image(q.image_path)
                if enc is None:
                    raise HTTPException(status_code=400, detail=f"인용 이미지 파일 없음: {q.image_path}")
                images.append(enc)
                quote_img_count += 1
    else:
        messages = [{"role": h["role"], "content": h["content"]} for h in _get_history(req.session_id)]

    if req.image_path:
        enc = _encode_image(req.image_path)
        if enc is None:
            raise HTTPException(status_code=400, detail=f"이미지 파일 없음: {req.image_path}")
        images.append(enc)
        attach_count = 1

    if req.quotes:
        lines = ["[인용]", "※ 아래 인용은 참고 자료이며, 답변 대상은 [메시지]입니다."]
        lines += parts
        if quote_img_count and attach_count:
            lines.append(
                f"※ 첨부된 이미지 중 앞 {quote_img_count}장은 인용 이미지, "
                f"마지막 {attach_count}장은 [메시지]에 직접 첨부한 이미지입니다."
            )
        elif quote_img_count:
            lines.append(f"※ 첨부된 이미지 {quote_img_count}장은 모두 인용 이미지입니다.")
        content = "\n".join(lines) + "\n\n[메시지]\n" + req.message
    else:
        content = req.message

    user_msg = {"role": "user", "content": content}
    if images:
        user_msg["images"] = images
    messages.append(user_msg)
    return messages


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
    ollama_messages = _build_ollama_messages(req)

    start = time.time()
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": req.model,
                "messages": ollama_messages,
                "stream": False,
                "options": {"num_ctx": 8192, "num_predict": -1},
            },
            timeout=300,
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        log.warning("Ollama 호출 실패 session=%s: %s", req.session_id, e)
        raise HTTPException(status_code=502, detail=f"Ollama 호출 실패: {e}")

    elapsed_ms = int((time.time() - start) * 1000)
    reply = resp.json()["message"]["content"]

    _save_message(req.session_id, "user", req.message, req.model,
                  image_path=req.image_path, quotes=[q.dict() for q in req.quotes])
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
    ollama_messages = _build_ollama_messages(req)
    log.info("chat 요청 session=%s model=%s msg_len=%d quotes=%d image=%s",
             req.session_id, req.model, len(req.message), len(req.quotes), bool(req.image_path))
    
    quotes_data = [q.dict() for q in req.quotes]

    def stream():
        start = time.time()
        collected = []
        memory_worker.chat_begin()
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
                        log.info("chat 완료 session=%s model=%s done_reason=%s prompt_tokens=%s eval_tokens=%s",
                                 req.session_id, req.model, chunk.get("done_reason"),
                                 chunk.get("prompt_eval_count"), chunk.get("eval_count"))
                        break

            elapsed_ms = int((time.time() - start) * 1000)
            yield f"event: done\ndata: {json.dumps({'elapsed_ms': elapsed_ms, 'model': req.model})}\n\n"

        except requests.exceptions.RequestException as e:
            log.exception("Ollama 호출 실패 session=%s", req.session_id)
            yield f"event: error\ndata: {json.dumps({'message': f'Ollama 호출 실패: {e}'})}\n\n"
        finally:
            memory_worker.chat_end()
            # 정상 종료, 오류, 클라이언트 연결 끊김 모두 여기서 저장
            reply = "".join(collected)
            if reply:
                elapsed_ms = int((time.time() - start) * 1000)
                _save_message(req.session_id, "user", req.message, req.model,
                              image_path=req.image_path, quotes=quotes_data)
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

@router.get("/memory-status")
def memory_status():
    return memory_worker.status()

class MemoryUpdate(BaseModel):
    category: str | None = None
    type: str | None = None
    content: str | None = None
    keywords: list[str] | None = None
    reviewed: bool | None = None


@router.patch("/memories/{memory_id}")
def patch_memory(memory_id: int, req: MemoryUpdate):
    fields = req.dict(exclude_none=True)
    try:
        row = update_memory(memory_id, fields)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if row is None:
        raise HTTPException(status_code=404, detail="메모리를 찾을 수 없음")
    return row