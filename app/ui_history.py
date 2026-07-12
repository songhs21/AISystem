import os
import json
import streamlit as st
import database
import json
import os
import streamlit as st
from comfyApi import run_upscale
from config.constants import NEGATIVE_BASE
from config.PATH import GRADIO_INPAINT, CONFIG_PATH, COMFY_OUTPUT, UPSCALE_MODEL_DIR, INPAINT_REQUEST, GRADIO_LOG, LOCAL_PYTHON, PYTHON_EMBEDED
from config.constants import TAG_CATEGORY_ORDER, CAT_KO
from tag_util import _sort_key, _cat_label, tag_ko
import logging

# gradio 로그 파일 변수
_gradio_log_file = None

# 좋아요/싫어요 상호 배타적 토글 버튼
def _toggle_edit_like(tag: str, like_key: str, dis_key: str):
    st.session_state[dis_key].discard(tag)
    if tag in st.session_state[like_key]:
        st.session_state[like_key].remove(tag)
    else:
        st.session_state[like_key].add(tag)

def _toggle_edit_dislike(tag: str, like_key: str, dis_key: str):
    st.session_state[like_key].discard(tag)
    if tag in st.session_state[dis_key]:
        st.session_state[dis_key].remove(tag)
    else:
        st.session_state[dis_key].add(tag)

# Gradio 인페인팅 실행
def _launch_gradio_inpaint(gen_id, image_path):
    global _gradio_log_file
    import json, subprocess, time, webbrowser
    
    # 1 gen_id, image_path를 inpaint_request.json에 저장 (gradio_inpaint.py에서 로드)
    tmp_path = INPAINT_REQUEST
    with open(tmp_path, "w") as f:
        json.dump({"gen_id": gen_id, "image_path": image_path}, f)
    
    # 2 이전 서브프로세스 로그 파일 핸들 정리
    if _gradio_log_file:
        _gradio_log_file.close()
    
    # 3 Gradio 서브프로세스 실행 (stdout/stderr를 gradio_log.txt로 리다이렉트)
    _gradio_log_file = open(
        GRADIO_LOG,
        "w",
        buffering=1,
        encoding="utf-8"
    )
    proc = subprocess.Popen(
        [LOCAL_PYTHON,
        GRADIO_INPAINT],
        stdout=_gradio_log_file,
        stderr=_gradio_log_file,
        text=True,
        bufsize=1
    )
    print(f"[DEBUG] Gradio PID: {proc.pid}")
    time.sleep(4)
    webbrowser.open("http://127.0.0.1:7860")

# config.json에서 히스토리 필터 설정 로드 (파일 없으면 기본값 반환)
def load_filter_config():
    default_history = {
        "excluded_tags": [],
        "included_tags": [],
        "include_mode": "AND",
        "score_filter_mode": "문제 없음",
        "score_filter_value": 5,
    }

    if not os.path.exists(CONFIG_PATH):
        return default_history

    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    return config.get("history", {}).get("filter", default_history)

# config.json에 히스토리 필터 설정 저장
def save_filter_config(config: dict):
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        existing = json.load(f)
    existing["history"]["filter"] = config
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

# 로컬 Upscale 모델 리스트업
def get_local_upscalemodels():
    if not os.path.exists(UPSCALE_MODEL_DIR):
        return []
    files = [f for f in os.listdir(str(UPSCALE_MODEL_DIR)) if f.endswith(('.pth', '.pt'))]
    return sorted(files)



# ===========================
# TAB 2 — 히스토리
# ===========================

def render_history_tab():
    st.subheader("생성 히스토리")



    # 히스토리 탭 세션 상태 초기화
    defaults = {
        "show_images":           False,
        "history_edit_id":       None,
        "history_page":          1,
        "show_filter_panel":     False,
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default

    # score_filter_mode는 main.py에서 보장되므로 prev 동기화만 수행
    if "prev_score_filter_mode" not in st.session_state:
        st.session_state.prev_score_filter_mode = st.session_state.score_filter_mode



    # 좌/우 방향키로 페이지 이동 (입력 포커스 중엔 비활성 됨)
    st.iframe("""
    <script>
    window.parent.document.addEventListener('keydown', function(e) {
        if (document.activeElement.tagName === 'INPUT' ||
            document.activeElement.tagName === 'TEXTAREA') {
            return;
        }
        if (e.key === 'ArrowLeft') {
            const btns = window.parent.document.querySelectorAll('button');
            for (const btn of btns) {
                if (btn.innerText.trim() === '◀ 이전') {
                    btn.click();
                    break;
                }
            }
        }
        if (e.key === 'ArrowRight') {
            const btns = window.parent.document.querySelectorAll('button');
            for (const btn of btns) {
                if (btn.innerText.trim() === '다음 ▶') {
                    btn.click();
                    break;
                }
            }
        }
    });
    </script>
    """, height=1)



    # 새로고침 버튼 / 생성 세션 상태 표기
    col_refresh, col_status, _ = st.columns([1, 2, 3])
    with col_refresh:
        if st.button("🔄 새로고침", width='stretch'):
            st.rerun()
    with col_status:
        if st.session_state.get("is_generating", False):
            st.warning("⏳ 생성 중")
        else:
            st.success("✅ 대기 중")




    # 페이지당 표시 이미지 수 / 히스토리 캐시 로드
    PAGE_SIZE = 10
    generations = st.session_state.history_cache

    # 로컬의 생성 된 이미지 존재 여부에 따른 리스트 출력
    if not generations:
        st.info("저장된 이미지가 없습니다.")
    else:
        # 필터 멀티셀렉트용 전체 태그 목록 추출
        all_unique_tags = set()
        for gen in generations:
            for t in gen.get("tags", []):
                if "tag" in t:
                    all_unique_tags.add(t["tag"])
        sorted_tags = sorted(list(all_unique_tags))



        # 필터 패널 토글 버튼
        btn_label = "닫기 ✖️" if st.session_state.show_filter_panel else "🔍 필터 설정"
        if st.button(btn_label, key="filter_toggle_btn", type="secondary", width='stretch'):
            st.session_state.show_filter_panel = not st.session_state.show_filter_panel
            st.rerun()



        # 필터 패널 (show_filter_panel 활성 시에만 렌더링)
        if st.session_state.show_filter_panel:
            with st.container(border=True):
                filter_col1, filter_col2 = st.columns([1, 2])

                with filter_col1:
                    # 이미지 표시 여부 토글
                    st.session_state.show_images = st.checkbox(
                        "생성한 이미지 히스토리 보기",
                        value=st.session_state.show_images
                    )


                    # 점수 필터 라디오 / 기준점수 슬라이더 (적용 안함 제외 시 노출)
                    SCORE_OPTIONS = ["적용 안함", "피드백 없음", "이상", "이하", "동일"]
                    score_mode = st.radio(
                        "점수 필터",
                        options=SCORE_OPTIONS,  # ✅ 누락된 options 추가
                        index=SCORE_OPTIONS.index(st.session_state.score_filter_mode) 
                        if st.session_state.score_filter_mode in SCORE_OPTIONS 
                        else 0,
                        key="score_filter_mode_radio",
                        horizontal=True,
                    )
                    # 점수 필터 변경 감지 시 세션 갱신 + config 저장 + rerun
                    if score_mode != "적용 안함":
                        st.slider("기준 점수", 0, 10, key="score_filter_value")
                    if score_mode != st.session_state.score_filter_mode:
                        st.session_state.score_filter_mode      = score_mode
                        st.session_state.prev_score_filter_mode = score_mode
                        st.session_state.history_page = 1
                        save_filter_config({
                            "excluded_tags":      st.session_state.current_excluded_tags,
                            "included_tags":      st.session_state.current_included_tags,
                            "include_mode":       st.session_state.include_mode,
                            "score_filter_mode":  score_mode,
                            "score_filter_value": st.session_state.get("score_filter_value", 5),
                        })
                        st.rerun()



                with filter_col2:
                    # 포함 태그 AND/OR 조건 선택 / 포함·제외 태그 멀티셀렉트
                    include_mode = st.radio(
                        "포함 태그 조건",
                        ["AND","OR"],
                        horizontal=True,
                        index=["AND","OR"].index(
                            st.session_state.include_mode
                        ),
                        key="include_mode_radio"
                    )
                    new_included = st.multiselect(
                        "✅ 포함할 태그 (이 태그가 있는 이미지만 표시)",
                        options=sorted_tags,
                        default=st.session_state.get("current_included_tags", []),
                        placeholder="포함할 태그를 선택하세요",
                        key="included_tags_multiselect"
                    )
                    new_excluded = st.multiselect(
                        "🚫 제외할 태그 (이 태그가 있는 이미지는 숨김)",
                        options=sorted_tags,
                        default=st.session_state.get("current_excluded_tags", []),
                        placeholder="제외할 태그를 선택하세요",
                        key="excluded_tags_multiselect"
                    )

                    # 태그 필터 변경 감지 시 세션 갱신 + config 저장
                    if (new_included != st.session_state.current_included_tags or
                            new_excluded != st.session_state.current_excluded_tags or
                            include_mode != st.session_state.include_mode):
                        st.session_state.current_included_tags = new_included
                        st.session_state.current_excluded_tags = new_excluded
                        st.session_state.include_mode          = include_mode
                        st.session_state.history_page = 1
                        save_filter_config({
                            "excluded_tags":      new_excluded,
                            "included_tags":      new_included,
                            "include_mode":       include_mode,
                            "score_filter_mode":  st.session_state.score_filter_mode,
                            "score_filter_value": st.session_state.score_filter_value,
                        })
        # 렌더링에 사용할 최종 제외 태그 리스트 확보
        excluded_tags = st.session_state.get("current_excluded_tags", [])
        


        # 이미지 출력 필터 동작
        # 1패스: 태그 필터링 (제외/포함 태그 기준)
        filtered_generations = []
        for gen in generations:
            current_image_tags = {t.get("tag") for t in gen.get("tags", []) if "tag" in t}

            # 제외 태그 매칭 시 스킵
            if any(tag in current_image_tags for tag in st.session_state.get("current_excluded_tags", [])):
                continue

            # 포함 태그 AND/OR 조건 검사
            included = st.session_state.get("current_included_tags", [])
            if included:
                if st.session_state.get("include_mode", "AND") == "AND":
                    if not all(tag in current_image_tags for tag in included):
                        continue
                else:
                    if not any(tag in current_image_tags for tag in included):
                        continue

            filtered_generations.append(gen)

        # 점수 필터용 feedback bulk 조회
        gen_ids = [g["id"] for g in filtered_generations]
        feedback_map = database.get_feedbacks_by_ids(gen_ids)

        # 2패스: 점수 필터링
        score_mode = st.session_state.score_filter_mode
        score_val = st.session_state.score_filter_value

        if score_mode != "적용 안함":
            def _score_filter(gen):
                feedback = feedback_map.get(gen["id"])
                gen_score = feedback["score"] if feedback else None
                if score_mode == "피드백 없음": return gen_score is None
                elif score_mode == "이상": return gen_score is not None and gen_score >= score_val
                elif score_mode == "이하": return gen_score is not None and gen_score <= score_val
                elif score_mode == "동일": return gen_score is not None and gen_score == score_val
                return True
            filtered_generations = [g for g in filtered_generations if _score_filter(g)]



        # 총 페이지 수 계산 / 현재 페이지 범위 보정 (1 ~ total_pages)
        total = len(filtered_generations)
        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

        st.session_state.history_page = max(1, min(st.session_state.history_page, total_pages))

        # 현재 페이지 슬라이싱
        start = (st.session_state.history_page - 1) * PAGE_SIZE
        end   = start + PAGE_SIZE
        page_gens = filtered_generations[start:end]

        # 페이지 네비게이션 (이전/다음 버튼 + 직접 입력 + 전체 페이지 수 표시)
        col_prev, col_cur, col_slash, col_total, col_next = st.columns([1, 1, 0.3, 1, 1])
        with col_prev:
            if st.button(
                "◀ 이전",
                key="nav_prev_top",
                disabled=st.session_state.history_page <= 1,
                width='stretch'
            ):
                st.session_state.history_page -= 1
                st.rerun()

        with col_cur:
            new_page = st.number_input(
                label="페이지",
                min_value=1,
                max_value=total_pages,
                value=min(st.session_state.history_page, total_pages),
                step=1,
                label_visibility="collapsed"
            )
            if new_page != st.session_state.history_page:
                st.session_state.history_page = new_page
                st.session_state.history_edit_id = None
                st.rerun()
        with col_slash:
            st.markdown(
                "<div style='text-align:center; line-height:38px;'>/ </div>",
                unsafe_allow_html=True
            )
        with col_total:
            st.markdown(
                f"<div style='text-align:center; line-height:38px;'>{total_pages} ({total})</div>",
                unsafe_allow_html=True
            )


        with col_next:
            if st.button(
                "다음 ▶",
                key="nav_next_top",
                disabled=st.session_state.history_page >= total_pages,
                width='stretch'
            ):
                st.session_state.history_page += 1
                st.session_state.history_edit_id = None
                st.rerun()



        # 이미지 히스토리 렌더링 (show_images 활성 시에만)
        if st.session_state.show_images and total > 0:
            page_gen_ids = [gen["id"] for gen in page_gens]
            feedback_map = database.get_feedbacks_by_ids(page_gen_ids)

            from PIL import Image
            for idx, gen in enumerate(page_gens):
                # 이미지 해상도 기반 컬럼 비율 동적 할당 (가로/세로 판단)
                col_ratio = [1, 1.5]
                if gen.get("image_path") and os.path.exists(gen["image_path"]):
                    try:
                        with Image.open(gen["image_path"]) as img:
                            width, height = img.size
                        col_ratio = [1, 1] if width >= height else [0.7, 1.8]
                    except Exception:
                        pass


                main_img_col, main_info_col = st.columns(col_ratio, vertical_alignment="center")                
                with main_img_col:
                    if gen.get("image_path") and os.path.exists(gen["image_path"]):
                        st.image(gen["image_path"], width='stretch')
                    else:
                        st.warning("이미지 파일 없음")

        

                with main_info_col:
                    # 생성 메타데이터 표시 (일시, 시드, 모델, 프롬프트)
                    st.markdown(f"### 📅 생성 일시: {gen['created_at']}")
                    st.markdown(f"**Seed:** `{gen['seed']}`")
                    raw_checkpoint = gen.get('checkpoint', 'Unknown')
                    checkpoint_display = raw_checkpoint.split('/')[-1].split('\\')[-1]
                    st.markdown(f"**🤖 사용된 모델:** `{checkpoint_display}`")
                    st.markdown(f"**📝 생성 프롬프트:** `{gen.get('prompt', '없음')}`")

                    # 업스케일 모델 선택 / 업스케일 상태 표시
                    upscale_model_list = get_local_upscalemodels()
                    if upscale_model_list:
                        selected_upscaler = st.selectbox(
                            "사용할 업스케일 모델 선택",
                            upscale_model_list,
                            index=0,
                            key=f"upscaler_selector_{gen['id']}"
                        )
                    else:
                        st.warning("업스케일 모델 없음")
                        selected_upscaler = None

                    upscaled = gen.get("upscaled_image")
                    upscaled_path = os.path.join(str(COMFY_OUTPUT), upscaled) if upscaled else None
                    st.markdown(f"**🔍 업스케일:** ✅ `{upscaled}`" if upscaled else "**🔍 업스케일:** ❌")

                    # 피드백 데이터 표시 (점수, 좋아요/싫어요 태그, 패스 여부)
                    feedback = feedback_map.get(gen["id"])
                    if feedback:
                        st.markdown(f"**⭐ 점수:** {feedback.get('score', '-')} / 10")
                        if feedback.get("liked_tags"):
                            st.markdown(f"**👍 좋아요:** {', '.join(feedback['liked_tags'])}")
                        if feedback.get("disliked_tags"):
                            st.markdown(f"**👎 싫어요:** {', '.join(feedback['disliked_tags'])}")
                        if feedback.get("pass_type"):
                            st.warning(f"패스 처리됨 : {feedback['pass_type']}")
                    else:
                        st.info("등록된 피드백 데이터가 없습니다.")


                    # 팝오버 최대 높이 CSS
                    st.markdown("""
                    <style>
                    /* 팝오버 전체 컨테이너의 최대 높이를 강제로 지정 */
                    [data-testid="stPopover"] {
                        max-height: 80%; /* 화면 높이의 80%까지 허용 */
                    }
                    </style>
                    """, unsafe_allow_html=True)
                    
                    # 업스케일 버튼 / 진행 상태 표시 (완료 시 history_dirty 세팅 후 rerun)
                    upscale_key = f"upscaling_{gen['id']}"
                    if st.session_state.get(upscale_key):
                        st.info("⏳ 업스케일 진행 중...")
                    elif not gen.get("upscaled_image"):
                        if st.button("🔼 업스케일", key=f"upscale_btn_{gen['id']}", width='stretch'):
                            progress_ph = st.empty()
                            for event in run_upscale(
                                gen["image_path"],
                                selected_upscaler,
                                checkpoint=gen.get("checkpoint", ""),
                                prompt=gen.get("prompt", ""),
                                negative=NEGATIVE_BASE
                            ):
                                if event["type"] == "progress":
                                    progress_ph.progress(event["value"], text=event["text"])
                                elif event["type"] == "done":
                                    output_filename = os.path.basename(event["image_path"])
                                    database.update_upscaled_image(gen["id"], output_filename)
                                    progress_ph.empty()
                                    st.success(f"업스케일 완료: {output_filename}")
                                    st.session_state.history_dirty = True
                                    st.rerun()
                    else:
                        st.markdown(f"✅ 업스케일 완료")



                    # 인페인팅 버튼 (Gradio 서브프로세스 실행)
                    if upscaled_path and os.path.exists(upscaled_path):
                        inpaint_target = st.radio(
                            "🖌️ 인페인팅 대상",
                            ["원본", "업스케일"],
                            horizontal=True,
                            key=f"inpaint_target_{gen['id']}"
                        )
                        inpaint_path = upscaled_path if inpaint_target == "업스케일" else gen["image_path"]
                    else:
                        inpaint_path = gen["image_path"]

                    if st.button("🖌️ 인페인팅", key=f"inpaint_btn_{gen['id']}", width='stretch'):
                        _launch_gradio_inpaint(gen['id'], inpaint_path)
                        st.info("브라우저에서 인페인팅 창이 열립니다.")



                    # 피드백 편집 팝오버 (패스 유형 / 좋아요·싫어요 태그 수정)
                    with st.popover("피드백 편집하기 ⚙️", width='stretch'):
                        gen_id = gen["id"]
                        tags = gen["tags"]


                        # 패스 유형 라디오 / 문제 부위 멀티셀렉트 (인체 디테일 선택 시에만 노출)
                        current_pass_type = feedback.get("pass_type") if feedback else None
                        pass_options = ["문제 없음", "그림체", "인체 디테일"]
                        default_index = 1 if current_pass_type == "style" else 2 if current_pass_type == "quality" else 0

                        edit_pass_type = st.radio("패스 유형", pass_options, index=default_index, horizontal=True, key=f"pass_type_{gen_id}")

                        edit_pass_reasons = st.multiselect(
                            "문제 부위", ["eye", "hand", "face", "body", "body_penetration", "extra_limb"],
                            default=feedback.get("pass_reasons", []) if feedback else [],
                            key=f"pass_reason_{gen_id}"
                        ) if edit_pass_type == "인체 디테일" else []


                        # 좋아요/싫어요 컬럼 헤더
                        col_title_like, col_title_dis = st.columns(2)
                        with col_title_like:
                            st.markdown("<p style='text-align: center; margin: 0;'><strong>👍 좋아요</strong></p>", unsafe_allow_html=True)
                        with col_title_dis:
                            st.markdown("<p style='text-align: center; margin: 0;'><strong>👎 싫어요</strong></p>", unsafe_allow_html=True)


                        # 좋아요/싫어요 세션 상태 초기화 (기존 피드백 기반)
                        edit_like_key = f"edit_like_{gen_id}"
                        edit_dis_key  = f"edit_dis_{gen_id}"
                        if edit_like_key not in st.session_state:
                            st.session_state[edit_like_key] = set(feedback.get("liked_tags", [])) if feedback else set()
                        if edit_dis_key not in st.session_state:
                            st.session_state[edit_dis_key] = set(feedback.get("disliked_tags", [])) if feedback else set()


                        # 태그 좋아요/싫어요 버튼 스크롤 영역
                        with st.container(height=550):
                            # 태그 카테고리 정렬 / 가중치 bulk 조회
                            sorted_tags_h = sorted(tags, key=_sort_key)
                            all_tag_values_h = [t.get("tag", "") for t in sorted_tags_h]
                            weight_map_h = database.get_tag_weights_bulk(all_tag_values_h)

                            # 카테고리별 그룹핑
                            grouped_h = {}
                            for t in sorted_tags_h:
                                cl = _cat_label(t)
                                grouped_h.setdefault(cl, []).append(t)

                            # 카테고리 순서대로 태그 버튼 렌더링 (좌=좋아요, 우=싫어요)
                            render_order = TAG_CATEGORY_ORDER + ["기타"]
                            for cat in render_order:
                                cat_label = CAT_KO.get(cat, cat)
                                t_list_h = grouped_h.get(cat, [])
                                if not t_list_h:
                                    continue
                                st.markdown(f"<div style='font-size: 20px; font-weight: bold; text-align: center;'>────{cat_label}────</div>", unsafe_allow_html=True)
                                five_cols = st.columns([1, 1, 0.1, 1, 1])

                                for i, t in enumerate(t_list_h):
                                    tag_value  = t.get("tag", "unknown")
                                    liked_h    = tag_value in st.session_state[edit_like_key]
                                    disliked_h = tag_value in st.session_state[edit_dis_key]
                                    display    = tag_ko.get(tag_value, tag_value)
                                    w          = weight_map_h.get(tag_value)
                                    w_str      = f" W{w:.2f}" if w is not None else "W0.00"

                                    like_label = f"{'✅' if liked_h else '👍'} {display}\n{w_str}"
                                    dis_label  = f"{'❌' if disliked_h else '👎'} {display}\n{w_str}"

                                    with five_cols[i % 2]:
                                        st.button(like_label, key=f"po_el_{gen_id}_{cat}_{i}",
                                                on_click=_toggle_edit_like,
                                                args=(tag_value, edit_like_key, edit_dis_key), use_container_width=True)
                                    with five_cols[3 + (i % 2)]:
                                        st.button(dis_label, key=f"po_ed_{gen_id}_{cat}_{i}",
                                                on_click=_toggle_edit_dislike,
                                                args=(tag_value, edit_like_key, edit_dis_key), use_container_width=True)


                        # 스코어 슬라이더 / 피드백 저장 버튼
                        edit_score_key = f"edit_score_{gen_id}"
                        current_score = feedback.get("score", 5) if feedback else 5
                        st.slider("Score 조정", 0, 10, current_score, key=edit_score_key)

                        if st.button("변경 사항 저장", key=f"po_save_{gen_id}", width='stretch', type="primary"):
                            pass_type = None if edit_pass_type == "문제 없음" else "style" if edit_pass_type == "그림체" else "quality"
                            database.save_feedback(
                                gen_id,
                                st.session_state[edit_score_key],
                                list(st.session_state[edit_like_key]),
                                list(st.session_state[edit_dis_key]),
                                pass_type,
                                edit_pass_reasons
                            )
                            database.update_tag_weights(
                                list(st.session_state[edit_like_key]),
                                list(st.session_state[edit_dis_key]),
                                st.session_state[edit_score_key]
                            )
                            st.success("저장 완료")
                            st.rerun()


        elif total == 0:
            st.info("필터 조건에 해당하는 이미지가 없습니다.")