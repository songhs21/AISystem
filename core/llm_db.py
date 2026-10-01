# core/llm_db.py
import sqlite3
from config.PATH import LLM_DB_PATH


def get_conn(timeout: int = 10) -> sqlite3.Connection:
    return sqlite3.connect(LLM_DB_PATH, timeout=timeout)


def init_llm_db():
    conn = get_conn()
    cursor = conn.cursor()

    # 대화 세션 (탭/페이지 단위로 구분하고 싶을 때 대비 — 지금은 세션 1개로도 무방)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            model TEXT,
            extracted_until INTEGER DEFAULT 0,  -- 여기까지의 chat_messages.id는 메모리 추출 완료
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 메시지
    # 장기 메모리 (대화에서 추출한 구조화 정보)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,          -- 'coding' | 'image' | 'general'
            type TEXT,              -- 'preference' | 'decision' | 'fact' | 'roadmap'
            content TEXT,
            keywords TEXT,          -- JSON 배열 문자열
            session_id INTEGER,
            source_message_id INTEGER,   -- 추출 근거가 된 마지막 메시지 id
            reviewed INTEGER DEFAULT 0,  -- 0: 미확인, 1: 사용자 확인 완료
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()