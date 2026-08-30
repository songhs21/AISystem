# core/db.py
import sqlite3
from config.PATH import DB_PATH


def get_conn(timeout: int = 10) -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH, timeout=timeout)


def init_db():
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS generations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_id TEXT,
            prompt TEXT,
            seed INTEGER,
            checkpoint TEXT,
            image_path TEXT,
            file_name TEXT,
            tags TEXT,
            status TEXT DEFAULT 'generating',
            upscaled_image TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            generation_id INTEGER,
            score INTEGER,
            liked_tags TEXT,
            disliked_tags TEXT,
            pass_type TEXT,
            pass_reasons TEXT,
            false_tags TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_tag_weights (
            tag TEXT PRIMARY KEY,
            weight REAL DEFAULT 0.0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inpainting (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            generation_id INTEGER,
            file_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 컬럼 마이그레이션 (없을 때만 추가)
    existing = {row[1] for row in cursor.execute("PRAGMA table_info(feedback)")}
    if "false_tags" not in existing:
        cursor.execute("ALTER TABLE feedback ADD COLUMN false_tags TEXT")

    existing_gen = {row[1] for row in cursor.execute("PRAGMA table_info(generations)")}
    if "upscaled_image" not in existing_gen:
        cursor.execute("ALTER TABLE generations ADD COLUMN upscaled_image TEXT")

    # 좀비 레코드 정리
    cursor.execute("UPDATE generations SET status = 'failed' WHERE status = 'generating'")

    conn.commit()
    conn.close()
