# main.py
import sys
import logging
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (config 패키지 import 해결)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import database
from tagger import analyze
from ui_generate import render_generate_tab
from ui_history import render_history_tab, load_filter_config
from config.PATH import COMFY_OUTPUT
from tag_util import tag_meta, TAG_META_PATH


st.set_page_config(layout="wide")
st.title("짤 생성 및 취향 DB 구축")


# 세션 상태 초기값 설정
if "auto_generate" not in st.session_state:
    st.session_state.auto_generate = False
if "show_filter_panel" not in st.session_state:
    st.session_state.show_filter_panel = False
if "gen_id" not in st.session_state:
    st.session_state.gen_id = None


# 앱 최초 실행 시 1회 초기화 (DB, 필터 설정, 이미지/태그 동기화)
if "system_initialized" not in st.session_state:
    database.init_db()

    # config.json에서 히스토리 필터 설정 로드
    _cfg = load_filter_config()
    st.session_state.current_excluded_tags = _cfg["excluded_tags"]
    st.session_state.current_included_tags = _cfg["included_tags"]
    st.session_state.include_mode          = _cfg["include_mode"]
    st.session_state.score_filter_mode     = _cfg["score_filter_mode"]
    st.session_state.score_filter_value    = _cfg["score_filter_value"]

    # 디스크 미등록 이미지 복구 동기화
    try:
        database.sync_unregistered_images(str(COMFY_OUTPUT), analyze_fn=analyze)
    except Exception as e:
        logging.error(f"이미지 동기화 실패: {e}")

    # liked_tags 기준 미등록 태그 → tag_meta.json 자동 추가
    try:
        added = database.sync_unregistered_tags(TAG_META_PATH, tag_meta)
        if added:
            logging.info(f"미등록 태그 {added}개 추가됨")
    except Exception as e:
        logging.error(f"태그 동기화 실패: {e}")

    st.session_state.system_initialized = True


# history_dirty 플래그 기반 히스토리 캐시 갱신
if "history_cache" not in st.session_state or st.session_state.get("history_dirty", False):
    st.session_state.history_cache = database.get_all_generations()
    st.session_state.history_dirty = False


# 탭 렌더링
tab_generate, tab_history = st.tabs(["🖼️ 생성", "📋 히스토리"])
with tab_generate:
    render_generate_tab()
with tab_history:
    render_history_tab()