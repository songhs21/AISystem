# core/image/tag.py
import json
import csv
import numpy as np
import onnxruntime as ort
from PIL import Image
from config.PATH import MODEL_PATH, MODEL_TAG_PATH, TAG_META_PATH
from config.constants import TAG_CATEGORY_ORDER, EXTRA_CATEGORIES, CAT_KO, BLACKLIST
from core.db import get_conn


# ── 태그 메타 로드 ────────────────────────────────────────

with open(TAG_META_PATH, encoding="utf-8") as f:
    tag_meta = json.load(f)

tag_ko: dict[str, str] = {}
tag_to_cat: dict[str, str] = {}

for _cat, _tag_dict in tag_meta.items():
    for _tv, meta in _tag_dict.items():
        tag_to_cat[_tv] = _cat
        if isinstance(meta, dict) and "ko" in meta:
            tag_ko[_tv] = meta["ko"]


# ── WD14 모델 로드 (모듈 임포트 시 1회) ──────────────────

def _load_tags():
    with open(MODEL_TAG_PATH, encoding="utf-8") as f:
        return [row["name"] for row in csv.DictReader(f)]

_session    = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
_input_name = _session.get_inputs()[0].name
_tags       = _load_tags()


# ── 이미지 태깅 ───────────────────────────────────────────

def _preprocess(image_path: str) -> np.ndarray:
    image = Image.open(image_path).convert("RGB")
    image = np.array(image.resize((448, 448)), dtype=np.float32)
    image = image[:, :, ::-1]
    return np.expand_dims(image, axis=0)


def analyze(image_path: str, threshold: float = 0.25, top_k: int = 50) -> list[dict]:
    outputs = _session.run(None, {_input_name: _preprocess(image_path)})[0][0]
    results = [
        {"tag": _tags[i], "score": float(score)}
        for i, score in enumerate(outputs)
        if _tags[i].lower() not in BLACKLIST and score >= threshold
    ]
    return sorted(results, key=lambda x: x["score"], reverse=True)[:top_k]


# ── 태그 분류 유틸 ────────────────────────────────────────

def cat_label(t: dict) -> str:
    cat = tag_to_cat.get(t.get("tag", ""), "")
    return "기타" if (cat in EXTRA_CATEGORIES or cat == "") else cat


def sort_key(t: dict) -> tuple:
    cat = tag_to_cat.get(t.get("tag", ""), "")
    if cat in TAG_CATEGORY_ORDER:
        return (0, TAG_CATEGORY_ORDER.index(cat))
    return (1, 0)


# ── 미등록 태그 동기화 ────────────────────────────────────

def sync_unregistered_tags(tag_meta_path: str, tag_meta: dict) -> int:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT liked_tags FROM feedback WHERE liked_tags IS NOT NULL")
    rows = cursor.fetchall()
    conn.close()

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

    registered = {tag for cat_dict in tag_meta.values() for tag in cat_dict.keys()}
    unregistered = db_tags - registered
    if not unregistered:
        return 0

    tag_meta.setdefault("unregistered", {})
    added = 0
    for tag in sorted(unregistered):
        if tag not in tag_meta["unregistered"]:
            tag_meta["unregistered"][tag] = {"ko": tag}
            added += 1

    if added > 0:
        with open(tag_meta_path, "w", encoding="utf-8") as f:
            json.dump(tag_meta, f, ensure_ascii=False, indent=2)

    return added
