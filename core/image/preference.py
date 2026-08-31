# core/image/preference.py
import sqlite3
import json
import os
from datetime import datetime
from core.db import get_conn
from core.image.tag import tag_to_cat

# ── 헬퍼 ──────────────────────────────────────────────────

def _attach_category(tags: list[dict]) -> list[dict]:
    """tags 리스트의 각 항목에 category 필드 추가"""
    for t in tags:
        t["category"] = tag_to_cat.get(t["tag"], "기타")
    return tags


# get_all_generations 수정 — tags 파싱 부분만
def get_all_generations() -> list[dict]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, prompt, seed, image_path, tags, created_at, checkpoint, upscaled_image
        FROM generations WHERE status = 'done' OR status IS NULL
        ORDER BY created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [{
        "id": r[0], "prompt": r[1], "seed": r[2],
        "image_path": r[3],
        "tags": _attach_category(json.loads(r[4])) if r[4] else [],
        "created_at": r[5], "checkpoint": r[6] or "Unknown",
        "upscaled_image": r[7] or None
    } for r in rows]


# get_generation_by_id 수정 — tags 파싱 부분만
def get_generation_by_id(gen_id) -> dict | None:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, prompt, seed, image_path, tags, status, checkpoint, created_at
        FROM generations WHERE id = ?
    """, (gen_id,))
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return None
    return {
        "id": row[0], "prompt": row[1], "seed": row[2],
        "image_path": row[3],
        "tags": _attach_category(json.loads(row[4])) if row[4] else [],
        "status": row[5], "checkpoint": row[6], "created_at": row[7],
    }

# ── Generation ────────────────────────────────────────────

def save_generation_start(prompt_id, prompt_text, seed, checkpoint) -> int:
    korea_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO generations (prompt_id, prompt, seed, checkpoint, status, created_at)
        VALUES (?, ?, ?, ?, 'generating', ?)
    """, (prompt_id, prompt_text, seed, checkpoint, korea_now))
    gen_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return gen_id


def save_generation_complete(gen_id, prompt_id, prompt_text, seed, checkpoint, image_path, tags) -> int:
    with get_conn() as conn:
        conn.execute("""
            UPDATE generations
            SET prompt_id=?, prompt=?, seed=?, checkpoint=?, image_path=?, file_name=?, tags=?, status='done'
            WHERE id=?
        """, (prompt_id, prompt_text, seed, checkpoint, image_path,
              os.path.basename(image_path), json.dumps(tags), gen_id))
        conn.commit()
    return gen_id


def update_generation_done(gen_id, image_path, tags):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM generations WHERE id = ?", (gen_id,))
        row = cursor.fetchone()
        if row and row[0] == 'done':
            return
        cursor.execute("""
            UPDATE generations SET image_path = ?, tags = ?, status = 'done' WHERE id = ?
        """, (image_path, json.dumps(tags), gen_id))
        conn.commit()


def update_upscaled_image(gen_id, filename):
    with get_conn() as conn:
        conn.execute("UPDATE generations SET upscaled_image = ? WHERE id = ?", (filename, gen_id))
        conn.commit()


def get_all_generations() -> list[dict]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, prompt, seed, image_path, tags, created_at, checkpoint, upscaled_image
        FROM generations WHERE status = 'done' OR status IS NULL
        ORDER BY created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [{
        "id": r[0], "prompt": r[1], "seed": r[2],
        "image_path": r[3], "tags": json.loads(r[4]) if r[4] else [],
        "created_at": r[5], "checkpoint": r[6] or "Unknown",
        "upscaled_image": r[7] or None
    } for r in rows]


def get_generation_by_id(gen_id) -> dict | None:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, prompt, seed, image_path, tags, status, checkpoint, created_at
        FROM generations WHERE id = ?
    """, (gen_id,))
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return None
    return {
        "id": row[0], "prompt": row[1], "seed": row[2],
        "image_path": row[3], "tags": json.loads(row[4]) if row[4] else [],
        "tags": _attach_category(json.loads(row[4])) if row[4] else [],
        "status": row[5], "checkpoint": row[6], "created_at": row[7],
    }


def get_generation_by_prompt_id(prompt_id) -> dict | None:
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM generations WHERE prompt_id = ? LIMIT 1", (prompt_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_generating_count() -> int:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM generations WHERE status = 'generating'")
    count = cursor.fetchone()[0]
    conn.close()
    return count


# ── Feedback ──────────────────────────────────────────────

def save_feedback(generation_id, score, liked_tags, disliked_tags,
                  pass_type=None, pass_reasons=None, false_tags=None):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM feedback WHERE generation_id = ? ORDER BY id DESC LIMIT 1
    """, (generation_id,))
    row = cursor.fetchone()

    params = (
        score,
        json.dumps(liked_tags, ensure_ascii=False),
        json.dumps(disliked_tags, ensure_ascii=False),
        pass_type,
        json.dumps(pass_reasons or [], ensure_ascii=False),
        json.dumps(false_tags or [], ensure_ascii=False),
    )

    if row:
        cursor.execute("""
            UPDATE feedback
            SET score=?, liked_tags=?, disliked_tags=?, pass_type=?, pass_reasons=?, false_tags=?
            WHERE id=?
        """, (*params, row[0]))
    else:
        cursor.execute("""
            INSERT INTO feedback (generation_id, score, liked_tags, disliked_tags, pass_type, pass_reasons, false_tags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (generation_id, *params))

    conn.commit()
    conn.close()


def get_feedbacks_by_ids(gen_ids: list[int]) -> dict[int, dict]:
    if not gen_ids:
        return {}
    placeholders = ",".join("?" * len(gen_ids))
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT f.generation_id, f.score, f.liked_tags, f.disliked_tags, f.pass_type, f.pass_reasons, f.false_tags
        FROM feedback f
        INNER JOIN (
            SELECT generation_id, MAX(id) as max_id
            FROM feedback WHERE generation_id IN ({placeholders})
            GROUP BY generation_id
        ) latest ON f.id = latest.max_id
    """, gen_ids)
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: {
        "score": row[1],
        "liked_tags": json.loads(row[2]) if row[2] else [],
        "disliked_tags": json.loads(row[3]) if row[3] else [],
        "pass_type": row[4],
        "pass_reasons": json.loads(row[5]) if row[5] else [],
        "false_tags": json.loads(row[6]) if row[6] else [],
    } for row in rows}


# ── Inpainting ────────────────────────────────────────────

def save_inpainting(generation_id: int, file_name: str) -> int:
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO inpainting (generation_id, file_name) VALUES (?, ?)
        """, (generation_id, file_name))
        conn.commit()
        return cursor.lastrowid


def get_inpaintings_by_generation(generation_id: int) -> list[dict]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, generation_id, file_name, created_at
        FROM inpainting WHERE generation_id = ? ORDER BY created_at DESC
    """, (generation_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "generation_id": r[1], "file_name": r[2], "created_at": r[3]} for r in rows]


# ── Tag Weights ───────────────────────────────────────────

def update_tag_weights(liked_tags, disliked_tags, score):
    conn = get_conn()
    cursor = conn.cursor()

    scale = abs(score - 5) / 5
    magnitude = 0.5 + scale * 0.5

    def _get_count_and_weight(tag: str) -> tuple[int, float]:
        cursor.execute("SELECT weight FROM user_tag_weights WHERE tag = ?", (tag,))
        row = cursor.fetchone()
        current_weight = row[0] if row else 0.0
        cursor.execute("""
            SELECT COUNT(*) FROM feedback WHERE liked_tags LIKE ? OR disliked_tags LIKE ?
        """, (f'%"{tag}"%', f'%"{tag}"%'))
        return cursor.fetchone()[0], current_weight

    def _upsert(tag: str, new_w: float):
        cursor.execute("""
            INSERT INTO user_tag_weights (tag, weight) VALUES (?, ?)
            ON CONFLICT(tag) DO UPDATE SET weight = ?, updated_at = CURRENT_TIMESTAMP
        """, (tag, new_w, new_w))

    for tag in liked_tags:
        count, current_w = _get_count_and_weight(tag)
        _upsert(tag, round((current_w * count + magnitude) / (count + 1), 4))

    for tag in disliked_tags:
        count, current_w = _get_count_and_weight(tag)
        _upsert(tag, round((current_w * count + (-magnitude)) / (count + 1), 4))

    conn.commit()
    conn.close()


def get_tag_weights_bulk(tags: list[str]) -> dict[str, float]:
    if not tags:
        return {}
    placeholders = ",".join("?" * len(tags))
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(f"SELECT tag, weight FROM user_tag_weights WHERE tag IN ({placeholders})", tags)
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: round(row[1], 2) for row in rows}


def get_tag_weight(tag) -> float | None:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT weight FROM user_tag_weights WHERE tag = ?", (tag,))
    row = cursor.fetchone()
    conn.close()
    return round(row[0], 2) if row else None


def get_top_weighted_tags(limit=10, min_weight=0.5) -> list[str]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT tag FROM user_tag_weights WHERE weight >= ? ORDER BY weight DESC LIMIT ?
    """, (min_weight, limit))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]


def get_top_tags_by_category(tag_meta, category, limit=10) -> list[dict]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT tag, weight FROM user_tag_weights WHERE weight > 0 ORDER BY weight DESC")
    rows = cursor.fetchall()
    conn.close()

    category_tags = tag_meta.get(category, {})
    result = []
    for tag, weight in rows:
        if tag in category_tags:
            result.append({"tag": tag, "ko": category_tags[tag].get("ko", tag), "weight": round(weight, 2)})
        if len(result) >= limit:
            break
    return result


def get_upscaled_image(gen_id) -> str | None:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT upscaled_image FROM generations WHERE id = ?", (gen_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def get_all_tag_weights() -> dict[str, float]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT tag, weight FROM user_tag_weights")
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: round(row[1], 2) for row in rows}