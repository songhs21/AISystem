# tag_util.py
import json
import streamlit as st
from config.PATH import TAG_META_PATH
from config.constants import TAG_CATEGORY_ORDER, EXTRA_CATEGORIES, CAT_KO


# tag_meta.json 로드 → tag_ko(태그:한국어), tag_to_cat(태그:카테고리) 딕셔너리 구축
with open(TAG_META_PATH, encoding="utf-8") as f:
    tag_meta = json.load(f)

tag_ko: dict[str, str] = {}
tag_to_cat: dict[str, str] = {}

for _cat, _tag_dict in tag_meta.items():
    for _tv, meta in _tag_dict.items():
        tag_to_cat[_tv] = _cat
        if isinstance(meta, dict) and "ko" in meta:
            tag_ko[_tv] = meta["ko"]


# txt 파일에서 태그 목록 로드 (Streamlit 캐시 적용)
@st.cache_data
def load_txt(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


# 태그 카테고리 라벨 반환 (EXTRA_CATEGORIES 또는 미등록 → "기타")
def _cat_label(t: dict) -> str:
    cat = tag_to_cat.get(t.get("tag", ""), "")
    return "기타" if (cat in EXTRA_CATEGORIES or cat == "") else cat


# TAG_CATEGORY_ORDER 기준 정렬 키 반환 (미등록 카테고리는 후순위)
def _sort_key(t: dict) -> tuple:
    cat = tag_to_cat.get(t.get("tag", ""), "")
    if cat in TAG_CATEGORY_ORDER:
        return (0, TAG_CATEGORY_ORDER.index(cat))
    return (1, 0)