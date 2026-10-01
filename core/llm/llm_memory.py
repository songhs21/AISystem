# core/llm_memory.py
import json
import logging
import re
import requests
from core.llm_db import get_conn

OLLAMA_URL = "http://localhost:11434/api/chat"

# 추출 입력 상한 (글자 수 기준 근사치, 토큰이 아님)
MAX_INPUT_CHARS = 6000
# 코드블록 하나에서 남길 최대 글자 수
MAX_CODE_CHARS = 300

_logger = logging.getLogger("llm_memory")

EXTRACT_SYSTEM_PROMPT = """너는 대화에서 장기적으로 기억할 가치가 있는 정보만 뽑아 JSON으로 정리하는 도구다.

규칙:
- 반드시 아래 JSON 형식으로만 답한다. 다른 설명은 쓰지 않는다.
- 뽑을 것이 없으면 {"memories": []} 를 돌려준다. 억지로 만들지 않는다.
- 사용자가 직접 말하거나 명확히 결정한 내용만 뽑는다. 추측하지 않는다.
- 일회성 질문, 인사, 단순 코드 결과물은 뽑지 않는다.
- content는 한 문장으로, 나중에 대화 없이 읽어도 이해되게 쓴다.
- category: "coding"(코드/개발), "image"(이미지 생성/프롬프트/태그), "general"(그 외) 중 하나.
- type: "preference"(취향/선호), "decision"(내린 결정), "fact"(사용자 환경/사실), "roadmap"(앞으로 할 계획) 중 하나.
- keywords: 검색에 쓸 핵심 단어 2~5개.

형식:
{"memories": [{"category": "...", "type": "...", "content": "...", "keywords": ["...", "..."]}]}"""


def _strip_code(text: str) -> str:
    """코드블록은 앞부분만 남겨 입력 길이를 줄인다."""
    def repl(m):
        body = m.group(2)
        if len(body) > MAX_CODE_CHARS:
            body = body[:MAX_CODE_CHARS] + "\n...(생략)"
        return f"```{m.group(1)}\n{body}\n```"
    return re.sub(r"```(\w*)\n(.*?)```", repl, text, flags=re.DOTALL)


def _fetch_pending(session_id: int) -> tuple[list[dict], int]:
    """아직 추출하지 않은 메시지와 세션의 현재 extracted_until을 반환."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT extracted_until FROM chat_sessions WHERE id = ?", (session_id,))
    row = cur.fetchone()
    if row is None:
        conn.close()
        raise ValueError(f"세션 {session_id} 없음")
    until = row[0] or 0
    cur.execute(
        "SELECT id, role, content FROM chat_messages WHERE session_id = ? AND id > ? ORDER BY id",
        (session_id, until),
    )
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "role": r[1], "content": r[2]} for r in rows], until


def _build_transcript(messages: list[dict]) -> tuple[str, int]:
    """입력 상한까지 앞에서부터 채운다. (텍스트, 실제로 포함된 마지막 메시지 id) 반환."""
    parts = []
    total = 0
    last_id = 0
    for m in messages:
        label = "사용자" if m["role"] == "user" else "AI"
        text = _strip_code(m["content"] or "")
        line = f"[{label}] {text}"
        if total + len(line) > MAX_INPUT_CHARS and parts:
            break
        parts.append(line)
        total += len(line)
        last_id = m["id"]
    return "\n\n".join(parts), last_id


def _call_extractor(model: str, transcript: str) -> list[dict]:
    resp = requests.post(
        OLLAMA_URL,
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
                {"role": "user", "content": transcript},
            ],
            "stream": False,
            "format": "json",
            "options": {"num_ctx": 8192, "temperature": 0.2},
            "keep_alive": "2m",
        },
        timeout=300,
    )
    resp.raise_for_status()
    raw = resp.json()["message"]["content"]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        _logger.warning(f"추출 JSON 파싱 실패: {raw[:300]}")
        raise ValueError("모델이 올바른 JSON을 반환하지 않음")
    items = data.get("memories", [])
    return items if isinstance(items, list) else []


_VALID_CATEGORY = {"coding", "image", "general"}
_VALID_TYPE = {"preference", "decision", "fact", "roadmap"}


def _normalize(item: dict) -> dict | None:
    content = (item.get("content") or "").strip()
    if not content:
        return None
    category = item.get("category")
    mtype = item.get("type")
    keywords = item.get("keywords") or []
    if not isinstance(keywords, list):
        keywords = []
    return {
        "category": category if category in _VALID_CATEGORY else "general",
        "type": mtype if mtype in _VALID_TYPE else "fact",
        "content": content,
        "keywords": [str(k).strip() for k in keywords if str(k).strip()][:5],
    }


def extract_session(session_id: int, model: str) -> dict:
    """세션의 미추출 대화 한 묶음을 추출해 저장. 한 번에 상한만큼만 처리한다."""
    messages, _ = _fetch_pending(session_id)
    if not messages:
        return {"processed": 0, "saved": 0, "remaining": 0, "memories": []}

    transcript, last_id = _build_transcript(messages)
    raw_items = _call_extractor(model, transcript)
    items = [n for n in (_normalize(i) for i in raw_items) if n]

    conn = get_conn()
    cur = conn.cursor()
    for it in items:
        cur.execute(
            """INSERT INTO memories (category, type, content, keywords, session_id, source_message_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (it["category"], it["type"], it["content"],
             json.dumps(it["keywords"], ensure_ascii=False), session_id, last_id),
        )
    cur.execute("UPDATE chat_sessions SET extracted_until = ? WHERE id = ?", (last_id, session_id))
    conn.commit()
    conn.close()

    remaining = sum(1 for m in messages if m["id"] > last_id)
    return {
        "processed": sum(1 for m in messages if m["id"] <= last_id),
        "saved": len(items),
        "remaining": remaining,
        "memories": items,
    }


def list_memories(category: str | None = None, only_unreviewed: bool = False) -> list[dict]:
    conn = get_conn()
    cur = conn.cursor()
    sql = "SELECT id, category, type, content, keywords, session_id, reviewed, created_at FROM memories"
    conds, args = [], []
    if category:
        conds.append("category = ?")
        args.append(category)
    if only_unreviewed:
        conds.append("reviewed = 0")
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY id DESC"
    cur.execute(sql, args)
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "id": r[0], "category": r[1], "type": r[2], "content": r[3],
            "keywords": json.loads(r[4] or "[]"), "session_id": r[5],
            "reviewed": bool(r[6]), "created_at": r[7],
        }
        for r in rows
    ]


def delete_memory(memory_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
    conn.commit()
    conn.close()