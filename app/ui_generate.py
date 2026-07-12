# ui_generate.py
import streamlit as st
import database
import random
import threading
import json
import os
import time
from PIL import Image as PILImage
from worker import watch_comfy
from comfyApi import run_comfy
from tagger import analyze
from tag_util import load_txt, _sort_key, _cat_label, tag_ko, tag_to_cat, tag_meta
from config.PATH import (
    POSES_PATH, MOUTH_STYLE, BG_PATH,
    HAIR_LENGTH, HAIR_STYLE, BANGS, HAIR_DETAILS, HAIR_ACCESSORIES,
    COSTUME_BASE, TOP_STYLE, BOTTOM_STYLE, OUTERWEAR, FASHION_THEME, SEASON_COSTUME,
    DESIGN_DETAILS, MATERIAL_DETAILS, ACCESSORIES, LEGWEAR, FOOTWEAR,
    CHECKPOINT_DIR, WORKFLOW_PATH
)
from config.constants import TAG_CATEGORY_ORDER, EXTRA_CATEGORIES, CAT_KO, NEGATIVE_BASE, MODEL_RESOLUTION


# 로컬 체크포인트 파일 목록 조회
def get_local_checkpoints():
    if not os.path.exists(str(CHECKPOINT_DIR)):
        return []
    return sorted([f for f in os.listdir(str(CHECKPOINT_DIR)) if f.endswith(('.safetensors', '.ckpt'))])


# 워크플로우 JSON 로드
def load_workflow():
    with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# 모델명 기준 MODEL_RESOLUTION 프로필 반환 (미매칭 시 SDXL 기본값)
def get_model_config(checkpoint_name):
    name = checkpoint_name.lower()
    for key, config in MODEL_RESOLUTION.items():
        if key.lower() in name:
            return config
    return {"width": 832, "height": 1216}


# 좋아요/싫어요 태그 토글 (상호 배타적)
def toggle_like(tag):
    st.session_state.selected_dislike.discard(tag)
    if tag in st.session_state.selected_like:
        st.session_state.selected_like.remove(tag)
    else:
        st.session_state.selected_like.add(tag)

def toggle_dislike(tag):
    st.session_state.selected_like.discard(tag)
    if tag in st.session_state.selected_dislike:
        st.session_state.selected_dislike.remove(tag)
    else:
        st.session_state.selected_dislike.add(tag)


# 생성 탭 렌더링
def render_generate_tab():

    # 세션 상태 초기화
    defaults = {
        "image_ready":          False,
        "selected_like":        set(),
        "selected_dislike":     set(),
        "image":                None,
        "tags":                 [],
        "score":                5,
        "show_images":          True,
        "is_generating":        False,
        "prompt_input_value":   "",
        "negative_input_value": NEGATIVE_BASE,
        "gen_id":               None,
        "auto_generate":        False,
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default

    # 가중치 TOP 태그 팝오버용 카테고리 그룹 정의
    CATEGORY_GROUPS = {
        "💇 헤어": ["hair_style", "hair_accessory", "hair_color", "hair_color_pattern", "front_hair_style"],
        "👁️ 눈": ["eyes_color"],
        "👗 의상": ["top_style", "bra_style", "bra_color", "bottom_style", "socks_style",
                "outfit_general", "outfit_swimwear", "outfit_costume", "outfit_color",
                "cloth_color_pattern", "footwear_style", "footwear_color", "design_details",
                "underwear_style"],
        "🧍 포즈/신체": ["pose", "body_features"],
        "😊 표정/연출": ["emotion", "framing"],
        "🎭 소품": ["props_accessories", "props_food", "props_objects", "props_furniture"],
        "🌄 배경": ["background"],
    }

    # 체크포인트 셀렉트박스 (form 없이 직접 구성 — 태그 버튼 rerun 충돌 방지)
    model_list = get_local_checkpoints()
    if model_list:
        selected_model = st.selectbox("사용할 체크포인트 선택", model_list, index=1, key="checkpoint_selector")
    else:
        st.warning("체크포인트 폴더를 찾을 수 없거나 파일이 없습니다.")
        selected_model = None

    # 프롬프트에 태그 추가 (중복 방지)
    def add_tag_to_prompt(tag_text):
        current = st.session_state.prompt_input_value
        existing_tags = [tag.strip() for tag in current.split(",") if tag.strip()]
        if tag_text not in existing_tags:
            st.session_state.prompt_input_value = (current.strip() + ", " + tag_text) if current.strip() else tag_text

    # 긍정/부정 프롬프트 입력창
    pos_col, neg_col = st.columns(2)
    with pos_col:
        st.text_area("✅ 긍정 프롬프트", value=st.session_state.prompt_input_value, key="prompt_input_value", height=120)
    with neg_col:
        st.text_area("❌ 부정 프롬프트", key="negative_input_value", height=120)

    submitted = st.button("이미지 생성", type="primary", use_container_width=True)

    # 팝오버 와이드 CSS / text_area 레이아웃 고정 CSS
    st.markdown("""
        <style>
        html body div[data-testid="stPopoverBody"] {
            min-width: 75vw !important;
            max-width: 90vw !important;
            box-shadow: 0px 10px 30px rgba(0, 0, 0, 0.25) !important;
        }
        div[data-testid="stTextArea"] {
            display: flex !important;
            visibility: visible !important;
            opacity: 1 !important;
            height: auto !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # 가중치 TOP 태그 팝오버 (데이터 있는 그룹만 ROW_SIZE=7 단위로 배치)
    st.markdown("**🏷️ 가중치 TOP 태그**")
    valid_groups = [
        (group_name, categories)
        for group_name, categories in CATEGORY_GROUPS.items()
        if any(database.get_top_tags_by_category(tag_meta, cat, limit=12) for cat in categories)
    ]

    ROW_SIZE = 7
    for row_idx in range(0, len(valid_groups), ROW_SIZE):
        chunk = valid_groups[row_idx:row_idx + ROW_SIZE]
        cols = st.columns(ROW_SIZE)
        for i, (group_name, categories) in enumerate(chunk):
            with cols[i]:
                with st.popover(group_name, use_container_width=True):
                    for cat in categories:
                        top_tags = database.get_top_tags_by_category(tag_meta, cat, limit=12)
                        if not top_tags:
                            continue
                        st.caption(f"📌 {cat}")
                        inner_cols = st.columns(6)
                        for j, t in enumerate(top_tags):
                            with inner_cols[j % 6]:
                                st.button(
                                    f"{t['ko']} ({t['weight']})",
                                    key=f"top_{cat}_{row_idx}_{i}_{j}",
                                    on_click=add_tag_to_prompt,
                                    args=(t["tag"],),
                                    use_container_width=True
                                )


    if submitted and selected_model:
        st.session_state.is_generating = True
        workflow = load_workflow()
        cfg_profile = get_model_config(selected_model)

        # 체크포인트 / 시드 주입
        workflow["4"]["inputs"]["ckpt_name"] = selected_model
        random_seed = random.randint(1, 999999999999999)
        workflow["3"]["inputs"]["seed"] = random_seed

        # 해상도 주입 (50% 확률로 가로/세로 스왑)
        target_width, target_height = cfg_profile["width"], cfg_profile["height"]
        if random.random() < 0.5:
            target_width, target_height = target_height, target_width
        workflow["5"]["inputs"]["width"]  = target_width
        workflow["5"]["inputs"]["height"] = target_height

        # 모델 전용 steps/cfg/prefix 주입 (프로필에 선언된 경우에만)
        if "prefix" in cfg_profile:
            workflow["3"]["inputs"]["steps"] = cfg_profile["steps"]
            workflow["3"]["inputs"]["cfg"]   = cfg_profile["cfg"]
            v4_prefix = cfg_profile["prefix"]
        else:
            v4_prefix = None

        # 프롬프트 조립 (모드 A: 사용자 입력 / 모드 B: txt 파일 랜덤 조합)
        prompt_input = st.session_state.prompt_input_value
        if prompt_input.strip():
            core_prompt = prompt_input.strip()
        else:
            base_prompt = workflow["6"]["inputs"]["text"]

            # 헤어
            hair_parts = [
                random.choice(load_txt(HAIR_LENGTH)),
                random.choice(load_txt(HAIR_STYLE)),
                *random.sample(load_txt(BANGS), random.randint(0, 1)),
                *random.sample(load_txt(HAIR_DETAILS), random.randint(0, 2)),
                *random.sample(load_txt(HAIR_ACCESSORIES), random.randint(0, 1)),
            ]

            # 의상
            outfit_parts = [
                random.choice(load_txt(COSTUME_BASE)),
                *random.sample(load_txt(OUTERWEAR), random.randint(0, 1)),
                *random.sample(load_txt(TOP_STYLE), random.randint(0, 1)),
                *random.sample(load_txt(BOTTOM_STYLE), random.randint(0, 1)),
                *random.sample(load_txt(FASHION_THEME), random.randint(0, 1)),
                *random.sample(load_txt(SEASON_COSTUME), random.randint(0, 1)),
                *random.sample(load_txt(DESIGN_DETAILS), random.randint(0, 3)),
                *random.sample(load_txt(MATERIAL_DETAILS), random.randint(0, 2)),
            ]

            # 악세사리
            acc_parts = [
                *random.sample(load_txt(ACCESSORIES), random.randint(0, 2)),
                *random.sample(load_txt(FOOTWEAR), random.randint(0, 1)),
                *random.sample(load_txt(LEGWEAR), random.randint(0, 1)),
            ]

            prompt_parts = [
                base_prompt,
                random.choice(load_txt(MOUTH_STYLE)),
                random.choice(load_txt(POSES_PATH)),
                *hair_parts,
                *outfit_parts,
                *acc_parts,
            ]
            core_prompt = ", ".join(prompt_parts)

        # 퀄리티 prefix 조립 (Animagine V4 전용)
        gen_tags = [{"tag": t.strip()} for t in core_prompt.split(",") if t.strip()]
        user_prompt = f"{v4_prefix}, {core_prompt}" if v4_prefix else core_prompt
        workflow["6"]["inputs"]["text"] = user_prompt

        # gen_id 선발급 + 파일명 frefix 주입
        pre_gen_id = database.save_generation_start(
            prompt_id="pending",
            prompt_text=user_prompt,
            seed=random_seed,
            checkpoint=selected_model
        )
        workflow["9"]["inputs"]["filename_prefix"] = f"ComfyUI_{pre_gen_id:04d}_generated"
        
        # 네거티브 프롬프트 조립 (사용자 입력 + 베이스 + 모델별 추가)
        MODEL_NEGATIVE = {
            "animagineXL40": "",
            "novaAnimeXL":   "",
            "counterfeit":   "bad proportions, poorly drawn face",
        }
        model_negative = next((v for k, v in MODEL_NEGATIVE.items() if k in selected_model.lower()), "")
        final_negative = ", ".join(p for p in [st.session_state.negative_input_value.strip(), NEGATIVE_BASE, model_negative] if p)
        workflow["7"]["inputs"]["text"] = final_negative

        # 생성 실행 / WebSocket 이벤트 처리
        progress_bar = st.progress(0.0)
        status_text  = st.empty()

        for event in run_comfy(workflow):
            if event["type"] == "prompt_id":
                prompt_id  = event["prompt_id"]
                before_time = event["before"]
                # 워커 스레드 시작 (DB 저장 담당)
                threading.Thread(
                    target=watch_comfy,
                    args=(prompt_id, before_time, user_prompt, random_seed, selected_model, pre_gen_id),
                    daemon=True
                ).start()

            elif event["type"] == "progress":
                progress_bar.progress(event["value"])
                status_text.text(event["text"])

            elif event["type"] == "done":
                image_path = str(event.get("image_path", ""))

                # 워커 DB 저장 완료 대기 (최대 10초 폴링)
                gen_record = None
                for _ in range(20):
                    gen_record = database.get_generation_by_prompt_id(prompt_id)
                    if gen_record:
                        st.session_state.gen_id = gen_record["id"]
                        break
                    time.sleep(0.5)

                # 안전망: 워커 미완료 시 직접 태깅 (다음 앱 시작 시 sync_unregistered_images로 복구)
                if gen_record:
                    tags = json.loads(gen_record["tags"]) if isinstance(gen_record["tags"], str) else gen_record["tags"]
                else:
                    tags = [{"tag": t["tag"], "score": t["score"]} for t in analyze(image_path)]

                # 세션 상태 갱신
                st.session_state.history_dirty    = True
                st.session_state.image            = image_path
                st.session_state.tags             = tags
                st.session_state.prompt_tags      = [t["tag"] for t in gen_tags]
                st.session_state.image_ready      = True
                st.session_state.selected_like    = set()
                st.session_state.selected_dislike = set()
                st.session_state.is_generating    = False

                progress_bar.progress(1.0)
                status_text.text("생성 완료!")
                st.success("생성 완료!")
                st.rerun()


    # 생성 완료 이미지 / 태그 표시
    if st.session_state.image_ready:

        # 태그 좋아요/싫어요 버튼 + 스코어 슬라이더 + 저장 버튼
        def render_tags():
            tags       = st.session_state.get("tags", [])
            gen_id     = st.session_state.get("gen_id", 0)
            sorted_tags = sorted(tags, key=_sort_key)

            # 태그 가중치 bulk 조회 / 카테고리별 그룹핑
            weight_map = database.get_tag_weights_bulk([t.get("tag", "") for t in sorted_tags])
            grouped = {}
            for t in sorted_tags:
                grouped.setdefault(_cat_label(t), []).append(t)

            # 태그 버튼 소형화 CSS
            with st.container(height=700, border=True):
                st.html("""
                    <style>
                        div[data-testid="stButton"] button {
                            font-size: 12px !important;
                            padding-top: 4px !important;
                            padding-bottom: 4px !important;
                            line-height: 1.3 !important;
                            white-space: pre-line !important;
                            min-height: auto !important;
                        }
                    </style>
                """)

                # 카테고리 순서대로 태그 버튼 렌더링 (좌=좋아요, 우=싫어요)
                for cat in TAG_CATEGORY_ORDER + ["기타"]:
                    t_list = grouped.get(cat, [])
                    if not t_list:
                        continue
                    cat_label = CAT_KO.get(cat, cat)
                    st.markdown(f"<div style='font-size: 20px; font-weight: bold; text-align: center;'>────{cat_label}────</div>", unsafe_allow_html=True)
                    five_cols = st.columns([1, 1, 0.1, 1, 1])

                    for i, t in enumerate(t_list):
                        tag_value = t.get("tag", "unknown")
                        display   = tag_ko.get(tag_value, tag_value)
                        w         = weight_map.get(tag_value)
                        w_str     = f" W{w:.2f}" if w is not None else " W0.00"
                        liked     = tag_value in st.session_state.selected_like
                        disliked  = tag_value in st.session_state.selected_dislike

                        like_label = f"{'✅' if liked else '👍'} {display}\n{w_str}"
                        dis_label  = f"{'❌' if disliked else '👎'} {display}\n{w_str}"

                        with five_cols[i % 2]:
                            st.button(like_label, key=f"like_{cat}_{tag_value}", on_click=toggle_like, args=(tag_value,), width='stretch')
                        with five_cols[3 + (i % 2)]:
                            st.button(dis_label, key=f"dis_{cat}_{tag_value}", on_click=toggle_dislike, args=(tag_value,), width='stretch')

            st.divider()

            # 스코어 슬라이더 / 저장 버튼
            st.slider("Score (전체 이미지 평가)", 0, 10, 5, key=f"score_slider_{gen_id}")

            if st.button("저장"):
                actual_gen_id = st.session_state.get("gen_id")
                if not actual_gen_id:
                    st.error("현재 이미지의 식별 ID를 찾을 수 없습니다.")
                else:
                    pass_type_ui = st.session_state.get("pass_type_ui", "문제 없음")
                    pass_type = None if pass_type_ui == "문제 없음" else "style" if pass_type_ui == "그림체" else "quality"
                    final_reasons = st.session_state.get("edit_pass_reasons", []) if pass_type == "quality" else []
                    current_score = st.session_state.get(f"score_slider_{gen_id}", 5)

                    database.save_feedback(actual_gen_id, current_score,
                        list(st.session_state.selected_like), list(st.session_state.selected_dislike),
                        pass_type, final_reasons)
                    database.update_tag_weights(
                        list(st.session_state.selected_like), list(st.session_state.selected_dislike), current_score)

                    st.success("저장 완료")
                    st.session_state.selected_like    = set()
                    st.session_state.selected_dislike = set()
                    st.session_state.image_ready = False
                    st.rerun()

        # 이미지 해상도 기반 세로/가로 레이아웃 분기
        img = PILImage.open(st.session_state.image)
        is_portrait = img.height > img.width
        col_ratio = [1, 1.5] if is_portrait else [1, 1]

        img_col, tag_col = st.columns(col_ratio)
        with img_col:
            st.image(st.session_state.image, width='stretch')

        with tag_col:
            # 사용된 프롬프트 표시
            prompt_tags = st.session_state.get("prompt_tags", [])
            st.markdown("**📝 사용된 프롬프트:**")
            st.caption(", ".join(prompt_tags) if prompt_tags else "*(기본값)*")

            # 패스 유형 라디오 / 문제 부위 멀티셀렉트 (인체 디테일 선택 시에만 노출)
            pass_type_ui = st.radio("패스 유형", ["문제 없음", "그림체", "인체 디테일"], horizontal=True, key="generate_pass_type")
            edit_pass_reasons = st.multiselect(
                "문제 부위", ["eye", "hand", "face", "body", "body_penetration", "extra_limb"],
                key="pass_reasons"
            ) if pass_type_ui == "인체 디테일" else []

            st.session_state.pass_type_ui     = pass_type_ui
            st.session_state.edit_pass_reasons = edit_pass_reasons

            st.subheader("Tags")
            render_tags()