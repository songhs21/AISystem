# CHANGELOG

## v0.1 — 단일 스크립트 생성기
- generate.py 단일 파일 구조
- ComfyUI API 호출 → 이미지 생성 → WD14 태그 추출 → SQLite 저장
- UI 없음, 피드백 없음

## v0.2 — Streamlit UI 도입 + 모듈 분리
- main.py / comfyApi.py / tagger.py / database.py 4파일 구조로 분리
- 생성 탭 기본 UI 구성
- 태그 좋아요/싫어요 버튼 + score 슬라이더
- generations / feedback / user_tag_weights 3테이블 DB 설계
- polling 방식 ComfyUI 연동

## v0.3 — WebSocket 진행률 + 레이아웃 개선
- ComfyUI polling → WebSocket 실시간 진행률로 교체
- st.progress + 상태 텍스트 실시간 출력
- 태그 박스 고정 높이 + 내부 스크롤 구조
- 이미지 비율 기반 레이아웃 자동 전환 (세로→좌우, 가로→상하)
- st.set_page_config(layout="wide") 적용

## v0.4 — 히스토리 탭 신설
- 히스토리 탭 추가
- 생성 이력 조회 + 피드백 편집 기능
- 페이지네이션 (10개 단위)
- 전체 이미지 수 제한 없음

## v0.5 — 히스토리 UI 고도화
- 태그 필터 + 제외 태그 멀티셀렉트
- 이미지 on/off 토글
- 이미지 비율 기반 동적 컬럼 비율 조정
- st.popover 기반 인라인 피드백 편집
- 팝오버 내 태그 버튼 4열 + 세로 구분선 시도 → 프레임워크 한계로 드롭

## v0.6 — 생성 폼 고도화
- st.form 도입으로 체크포인트 + 프롬프트 + 생성 버튼 통합
- 로컬 체크포인트 드롭다운 자동 스캔
- 프롬프트 입력창 추가 (비우면 기본 태그, 입력하면 override)
- Regenerate 버튼 → 자동 재생성 플래그 구조
- prompt_id (UUID) 생성 기록에 추가

## v0.7 — DB 스키마 확장 + 마이그레이션
- checkpoint 컬럼 추가 + ALTER TABLE 마이그레이션
- prompt_id 컬럼 추가
- save_generation 함수에 체크포인트 인자 추가
- 히스토리에 사용 모델명 표시
- 히스토리 프롬프트 표시 버그 수정 (WD14 태그 → 실제 입력 프롬프트로 교체)
- SQL 인라인 주석 제거 (syntax error 수정)

## v0.8 — 랜덤 요소 주입 시스템
- poses.txt 기반 랜덤 포즈 자동 주입
- hairstyle.txt 추가
- bg.txt 추가 (실내/실외 대분류 포함 구조)
- load_txt() 범용 로더 함수로 통합
- 모드 A (사용자 입력) / 모드 B (자동 조합) 분기 구조 명확화
- get_top_weighted_tags 주석 처리 유지 (데이터 축적 대기 중)

## v0.9 — 태그 가중치 시스템 + 워커 분리
- threading 기반 워커 스레드 분리 (watch_comfy)
- 태그 가중치 이동평균 방식 확정 (누적 합산 → 롤백)
- 가중치 TOP 태그 팝오버 UI (카테고리별 그룹핑)
- 팝오버 클릭 → 긍정 프롬프트 자동 주입
- st.form 제거 → 독립 위젯으로 전환 (태그 버튼 rerun 충돌 해결)
- Streamlit 위젯 key= / value= 동시 사용 금지 원칙 확립
- MCut 적응형 임계값 실험 → 태그 수 감소로 롤백, 고정 0.25 + 블랙리스트 방식 확정

## v0.10 — 히스토리 필터 고도화 + 업스케일 통합
- config.json 기반 필터 설정 영속화 (excluded/included tags, score filter)
- save_filter_config 자기참조 버그 수정
- AND/OR 포함 태그 조건 선택
- 점수 필터 (이상/이하/동일/피드백 없음)
- feedback_map 2패스 필터링 구조
- 업스케일 파이프라인 통합 (run_upscale, upscaled_image 컬럼)

## v0.10.1 — 외부 접속
- ngrok으로 외부 접속 시도 → 기 사용중인 WireGuard VPN으로 외부 접속 안정화

## v0.11 — Gradio 인페인팅 파이프라인
- Gradio 서브프로세스 기반 인페인팅 UI 분리
- inpainting 테이블 추가
- 레이어 순차처리 + 크롭-블렌딩 + 가우시안 페더링
- VAEEncodeForInpaint + ControlNet 동시 사용 충돌 확인 → detail 모드 분리
- Gradio 레이어 미분리 시 BBox 붕괴 원인 규명 및 해결
- 마스크 저장 L→RGB 변환, 반전 제거

## v0.11.1 — 태그 동기화 + Git 구조 정비
- config/PATH.py + config/constants.py 중앙화 리팩토링
- tag_util.py / tagger.py / ui_generate.py / ui_history.py / main.py 전 파일 import 정리
- sys.path 동적 추가로 ModuleNotFoundError 해결
- sync_unregistered_images 도입 (디스크 미등록 이미지 복구)
- sync_unregistered_tags 도입 (liked_tags 기준 tag_meta 자동 갱신)
- tag_meta.json FileNotFoundError 폴백 처리 (빈 dict로 graceful degradation)
- tag/ 폴더 gitignore 추가 + example 파일 구조화

## v0.12 — gen_id 기반 파일명 통일 (작업 예정)
- gen_id 선발급 방식으로 생성 타이밍 확정
- 파일명 ComfyUI_{gen_id}_generated / inpainting_{count} 통일
- sync_unregistered_images 제거
- feedback created_at KST 수정

## v0.12 — gen_id 기반 파일명 통일 + 버그 수정

- gen_id 선발급 방식으로 생성 타이밍 확정 (save_generation_start → prefix 주입 → worker UPDATE)
- 파일명 ComfyUI_{gen_id}_generated / ComfyUI_{gen_id}_inpainting_{count} 통일
- save_generation_complete INSERT → UPDATE 방식으로 변경
- worker.py pre_gen_id 인자 추가
- run_inpaint gen_id 파라미터 추가
- feedback created_at KST 수정 (datetime('now', 'localtime'))
- sync_unregistered_images 주석 처리 (gen_id 선발급으로 누락 케이스 제거)
- run_upscale ComfyUI 노드 검증 실패 에러 핸들링 추가
- 히스토리 업스케일 이미지 표시 + 인페인팅 대상 선택 라디오 추가 (원본/업스케일)
- DB 중복 레코드 정리 (sync_unregistered_images가 업스케일 파일 긁어 생성한 중복)
- gradio_inpaint.py내 sys.path.append(r"D:\Python\AISystem/PreferenceMemory") 경로 현재 구조에 맞게 수정

## v0.13 — 피드백 시스템 고도화

- `false_tags` 컬럼 추가 (feedback 테이블) — 오탐 태그 전용, pass_reasons 부위 enum과 분리
- `PASS_REASON_KO` 딕셔너리 추가 (constants.py) — 15개 부위 enum 한국어 매핑
- `pass_reasons` 15개로 확장 (eye/ear/nose/mouth/face_overall/hand/finger/arm/leg/foot/body_overall/body_penetration/extra_limb/clothing_fit/background)
- 패스 유형 라디오 확장: "마음에 들지 않음(dislike)" 추가 → 태그/스코어 영역 비활성화
- 태그 버튼 2열(좋/싫) → 3열(좋/싫/패) 변경 (생성 탭 + 히스토리 팝오버)
- 히스토리 필터에 패스 유형 필터 추가 (그림체/인체 디테일/마음에 들지 않음)
- 히스토리 새로고침 버튼 `history_dirty = True` 누락 버그 수정
