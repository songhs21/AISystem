# database.py
import sqlite3
import json
from datetime import datetime
import glob
import os
import time
from config.PATH import DB_PATH

#underwrear visible, outlines visible, sheer tight clothes
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 테이블 생성 feedback
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            generation_id INTEGER,
            score INTEGER,
            liked_tags TEXT,
            disliked_tags TEXT,
            pass_type TEXT,
            pass_reasons TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # user weights
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_tag_weights (
            tag TEXT PRIMARY KEY,
            weight REAL DEFAULT 0.0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # inpainting
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inpainting (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            generation_id INTEGER,
            file_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # generations 테이블 컬럼 추가 (upscaled_image — 없을 때만)
    cursor.execute("""
        ALTER TABLE generations ADD COLUMN upscaled_image TEXT
    """) if not any(
        row[1] == "upscaled_image"
        for row in cursor.execute("PRAGMA table_info(generations)")
    ) else None

    # 앱 비정상 종료 시 generating 상태로 남은 좀비 레코드 정리
    cursor.execute("""
        UPDATE generations SET status = 'failed' WHERE status = 'generating'
    """)

    conn.commit()
    conn.close()



def save_feedback(generation_id, score, liked_tags, disliked_tags, pass_type=None, pass_reasons=None):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()

    # 기존 피드백 존재 여부 확인 (있으면 UPDATE, 없으면 INSERT)
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
    )

    if row:
        cursor.execute("""
            UPDATE feedback
            SET score=?, liked_tags=?, disliked_tags=?, pass_type=?, pass_reasons=?
            WHERE id=?
        """, (*params, row[0]))
    else:
        cursor.execute("""
            INSERT INTO feedback (generation_id, score, liked_tags, disliked_tags, pass_type, pass_reasons, created_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
        """, (generation_id, *params))

    conn.commit()
    conn.close()


def save_inpainting(generation_id: int, file_name: str) -> int:
    # 인페인팅 결과 파일명 저장
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO inpainting (generation_id, file_name) VALUES (?, ?)
        """, (generation_id, file_name))
        conn.commit()
        return cursor.lastrowid


def get_inpaintings_by_generation(generation_id: int) -> list[dict]:
    # generation_id 기준 인페인팅 결과 목록 조회 (최신순)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, generation_id, file_name, created_at
        FROM inpainting WHERE generation_id = ? ORDER BY created_at DESC
    """, (generation_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "generation_id": r[1], "file_name": r[2], "created_at": r[3]} for r in rows]


def get_all_generations():
    # status=done인 전체 생성 이력 조회 (최신순)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, prompt, seed, image_path, tags, created_at, checkpoint, upscaled_image
        FROM generations WHERE status = 'done' OR status IS NULL
        ORDER BY created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [{
        "id": row[0], "prompt": row[1], "seed": row[2],
        "image_path": row[3], "tags": json.loads(row[4]) if row[4] else [],
        "created_at": row[5], "checkpoint": row[6] or "Unknown",
        "upscaled_image": row[7] or None
    } for row in rows]


def get_feedbacks_by_ids(gen_ids: list[int]) -> dict[int, dict]:
    # gen_id 목록 기준 최신 피드백 bulk 조회 → {gen_id: feedback_dict}
    if not gen_ids:
        return {}
    placeholders = ",".join("?" * len(gen_ids))
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT f.generation_id, f.score, f.liked_tags, f.disliked_tags, f.pass_type, f.pass_reasons
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
    } for row in rows}


def get_top_weighted_tags(limit=10, min_weight=0.5):
    # 가중치 상위 태그 목록 조회
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT tag FROM user_tag_weights WHERE weight >= ? ORDER BY weight DESC LIMIT ?
    """, (min_weight, limit))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]


def save_generation_start(prompt_id, prompt_text, seed, checkpoint):
    # 생성 시작 시점 레코드 삽입 (status=generating)
    korea_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO generations (prompt_id, prompt, seed, checkpoint, status, created_at)
        VALUES (?, ?, ?, ?, 'generating', ?)
    """, (prompt_id, prompt_text, seed, checkpoint, korea_now))
    gen_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return gen_id


def update_generation_done(gen_id, image_path, tags):
    # 생성 완료 시 image_path/tags/status 업데이트 (중복 완료 방지)
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM generations WHERE id = ?", (gen_id,))
        row = cursor.fetchone()
        if row and row[0] == 'done':
            return
        cursor.execute("""
            UPDATE generations SET image_path = ?, tags = ?, status = 'done' WHERE id = ?
        """, (image_path, tags, gen_id))
        conn.commit()


def get_generating_count():
    # 현재 generating 상태 레코드 수 조회
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM generations WHERE status = 'generating'")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_generation_by_id(gen_id):
    # gen_id 기준 단일 generation 레코드 조회
    conn = sqlite3.connect(DB_PATH, timeout=10)
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
        "status": row[5], "checkpoint": row[6], "created_at": row[7],
    }


def save_generation_complete(prompt_id, prompt_text, seed, checkpoint, image_path, tags):
    # 생성 완료 데이터 단일 INSERT (worker.py에서 호출)
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO generations
                (prompt_id, prompt, seed, checkpoint, image_path, file_name, tags, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'done', datetime('now', 'localtime'))
        """, (prompt_id, prompt_text, seed, checkpoint, image_path, os.path.basename(image_path), json.dumps(tags)))
        conn.commit()
        return cursor.lastrowid


def update_tag_weights(liked_tags, disliked_tags, score):
    # 이동평균 방식으로 태그 가중치 갱신 (좋아요=양수, 싫어요=음수 방향)
    # new_weight = (기존_weight * count + magnitude) / (count + 1)
    conn = sqlite3.connect(DB_PATH, timeout=10)
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


def sync_unregistered_images(image_dir_path, analyze_fn):
    # 디스크에만 있고 DB 미등록된 이미지를 WD14 태깅 후 복구 등록
    disk_images = glob.glob(os.path.join(image_dir_path, "*.png")) + \
                  glob.glob(os.path.join(image_dir_path, "*.jpg"))
    if not disk_images:
        return

    with sqlite3.connect(DB_PATH, timeout=30) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_name FROM generations WHERE file_name IS NOT NULL")
        registered_filenames = {row[0].lower() for row in cursor.fetchall() if row[0]}

        has_changes = False
        for img_path in disk_images:
            normalized_path = os.path.normpath(img_path).replace("\\", "/")
            filename = os.path.basename(normalized_path).lower()

            # 인페인팅 결과물 스킵
            if "_inpainting_" in filename:
                continue

            if filename not in registered_filenames:
                try:
                    tags_raw = analyze_fn(normalized_path)
                    cursor.execute("""
                        INSERT INTO generations
                            (prompt_id, prompt, seed, checkpoint, image_path, file_name, tags, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'done', ?)
                    """, (
                        f"recovered_{int(time.time())}", "*(복구본)*", 0, "Unknown",
                        normalized_path, os.path.basename(normalized_path),
                        json.dumps(tags_raw), datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    ))
                    has_changes = True
                except Exception as e:
                    print(f"복구 실패: {e}")

        # 변경분 있을 때만 커밋 (불필요한 저널 생성 방지)
        if has_changes:
            conn.commit()


def get_generation_by_prompt_id(prompt_id):
    # prompt_id 기준 generation 레코드 조회
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM generations WHERE prompt_id = ? LIMIT 1", (prompt_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_top_tags_by_category(tag_meta, category, limit=10):
    # 카테고리 기준 가중치 상위 태그 조회 (tag_meta 필터링)
    conn = sqlite3.connect(DB_PATH, timeout=10)
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


def get_tag_weight(tag):
    # 단일 태그 가중치 조회
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT weight FROM user_tag_weights WHERE tag = ?", (tag,))
    row = cursor.fetchone()
    conn.close()
    return round(row[0], 2) if row else None


def update_upscaled_image(gen_id, filename):
    # 업스케일 완료 파일명 저장
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE generations SET upscaled_image = ? WHERE id = ?", (filename, gen_id))
        conn.commit()


def get_upscaled_image(gen_id):
    # 업스케일 파일명 조회
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT upscaled_image FROM generations WHERE id = ?", (gen_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def get_tag_weights_bulk(tags: list[str]) -> dict[str, float]:
    # 태그 목록 bulk 가중치 조회 → {tag: weight}
    if not tags:
        return {}
    placeholders = ",".join("?" * len(tags))
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute(f"SELECT tag, weight FROM user_tag_weights WHERE tag IN ({placeholders})", tags)
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: round(row[1], 2) for row in rows}


def sync_unregistered_tags(tag_meta_path: str, tag_meta: dict) -> int:
    # liked_tags 기준 미등록 태그를 tag_meta.json unregistered 카테고리에 자동 추가
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT liked_tags FROM feedback WHERE liked_tags IS NOT NULL")
    rows = cursor.fetchall()
    conn.close()

    # DB liked_tags에서 태그 추출
    db_tags = set()
    for row in rows:
        try:
            tag_list = json.loads(row[0])
            if not isinstance(tag_list, list):
                tag_list = [tag_list]
        except (json.JSONDecodeError, TypeError):
            tag_list = row[0].split(",")
        for tag in tag_list:
            tag = str(tag).strip().lower()
            if tag:
                db_tags.add(tag)

    # tag_meta 등록 태그와 비교 → 미등록 추출
    registered = {tag for cat_dict in tag_meta.values() for tag in cat_dict.keys()}
    unregistered = db_tags - registered
    if not unregistered:
        return 0

    # unregistered 카테고리에 추가 후 저장
    tag_meta.setdefault("unregistered", {})
    added = sum(1 for tag in sorted(unregistered) if not tag_meta["unregistered"].setdefault(tag, {"ko": tag}) or tag not in tag_meta["unregistered"])

    added = 0
    for tag in sorted(unregistered):
        if tag not in tag_meta["unregistered"]:
            tag_meta["unregistered"][tag] = {"ko": tag}
            added += 1

    if added > 0:
        with open(tag_meta_path, "w", encoding="utf-8") as f:
            json.dump(tag_meta, f, ensure_ascii=False, indent=2)

    return added
