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

## CHANGELOG v0.10.2 — 미등록 태그 자동 동기화

### Context
- 피드백 누적에 따라 feedback 테이블 liked_tags에 tag_meta.json에 등록되지 않은 태그들이 지속적으로 발생. 매 작업 시 수작업으로 DB 태그 추출 → 중복 제거 → JSON 편집 과정을 반복해야 했음.

- Problem
미등록 태그 확인 자체가 별도 스크립트(db_tag_extracting_code.py) 실행 필요
추출 결과를 보고 tag_meta.json을 직접 편집하는 품이 과도함
누락된 채로 방치되면 태그 한국어 표시, 카테고리 분류 등 전반적인 UI 품질 저하

- Options
기존 방식 유지 (수동 스크립트 실행 + 수동 JSON 편집)
앱 시작 시 자동 감지 → unregistered 카테고리에 자동 삽입

- Decision Criteria
수작업 최소화
기존 tag_meta.json 구조 유지
나중에 번역/분류는 수동으로 할 수 있어야 함

- Decision
Option 2 채택. database.sync_unregistered_tags() 함수 신설, main.py system_initialized 블록에서 앱 시작 1회 호출.

- Reasoning
liked_tags만 대상 (disliked_tags는 피드백 의미가 약하고 0점 태그 다수)
unregistered 카테고리로 격리해두면 번역/분류 작업 시 한눈에 파악 가능
tag_meta에 이미 있는 태그는 스킵하므로 중복 삽입 없음

- Outcome
database.py — sync_unregistered_tags(tag_meta_path, tag_meta) 추가
main.py — system_initialized 블록에 호출 추가
앱 시작 시 미등록 태그 자동으로 tag_meta.json["unregistered"]에 삽입됨

- Trade-off
unregistered 카테고리 번역/분류는 여전히 수동. 단 JSON 구조 편집 품은 완전히 제거됨.


## v0.10.3 patch — ControlNet 인페인팅 (detail 모드) 정상화
### 수정 내용: inpaint_detail_workflow.json

- 노드 21 VAEEncode → VAEEncodeForInpaint → InpaintModelConditioning으로 최종 교체
- noise_mask: true 추가
- 노드 8 KSampler positive/negative를 ["16",0], ["16",1]로 연결, latent를 ["21",2]로 연결
- 노드 16 ControlNet positive/negative를 ["21",0], ["21",1]로 연결
- 노드 22 channel "alpha" → "red"

### gradio_inpaint.py

- 마스크 저장 convert("L") → convert("RGB") (channel: red 호환)
- 마스크 반전 255 - cropped_mask → cropped_mask (noise_mask 방향 일치)

- 디버깅 과정에서 확인된 핵심 원인:

- VAEEncodeForInpaint + ControlNet 동시 사용 시 두 인페인팅 방식 충돌 → 변화 없음
- 마스크를 레이어 분리 없이 한 레이어에 여러 영역 칠하면 BBox가 전체를 감싸 크롭 비율 붕괴 (2780x405 → 512x74)
- InpaintModelConditioning의 noise_mask는 MASK 타입이 아닌 BOOLEAN

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

## v1.0 상세 — ST -> React 마이그레이션
- core/ 레이어 분리 (image/generate, preference, tag, system/watcher, comfy_manager)
- api/ 라우터 (sd, history, inpaint, system)
- React 프론트 (생성/히스토리/LLM 탭, ImageViewer 줌/패닝, InpaintCanvas 오버레이)
- ComfyUI 자동 기동/종료, SD/LLM VRAM 스위칭
- 로그 파일 기반 SSE 실시간 스트리밍 (LogOverlay)
- 히스토리 피드백 편집 오버레이 슬라이드
- 프롬프트 태그 배지 표시 (PromptTags)

## v1.1.1 — UI 개선 및 Electron 설정

### GeneratePage.jsx
- 3단 레이아웃 (이미지뷰어 28% / 드롭박스 flex:1 / 부정프롬프트 18%)
- 고정 헤더 영역 분리: 모드 전환 버튼 + 1차 카테고리 네비 + 2차 카테고리 네비 + 최종 프롬프트 미리보기
- 1차 카테고리 클릭 → 해당 위치 scrollIntoView, 2차 카테고리 클릭 →  서브카테고리 위치 scrollIntoView
- catRefs / subRefs useRef 추가
- 태그 후보 목록 maxHeight 120px 스크롤 (slice 제한 제거)
- 태그 패널 오버레이 width 퍼센트화 (30% / 40px)
- 고정값 → 퍼센트 전환 (이미지뷰어 28%, 부정프롬프트 18%)
- 최종 프롬프트 미리보기 고정 헤더로 이동, 버튼화 (클릭 시 선택 해제)
- electron/main.cjs — Electron 앱 모드 실행 설정 완료
- frontend/package.json — electron:dev 스크립트 추가, concurrently 설치
- start.bat — Electron 실행 방식으로 교체

## v1.1.2 — 태그 시스템 개선 + 드롭박스 UX 개선

---

### tag_to_cat 카테고리 서버 반영 (B안)


- preference.py의 get_all_generations(), get_generation_by_id() 반환 시 tags 각 항목에 category 필드를 서버에서 직접 붙여서 반환하도록 변경.
- _attach_category() 헬퍼 추가, tag.py의 tag_to_cat 딕셔너리 재활용.
- 클라이언트 추가 요청 없이 기존 generations 응답에 포함시키는 B안을 선택한 이유는 "불필요한 로드나 부하는 줄일 수 있으면 줄이는 게 맞다"는 판단에 따른 것.
```
#### 변경 파일: preference.py, core/image/tag.py (import 추가)
```
---

### 전체 태그 가중치 선로드 + ★ 추천 칩


- /api/history/tag-weights-all 엔드포인트 추가 (preference.py get_all_tag_weights() 신규).
- GeneratePage 마운트 시 전체 가중치를 한 번에 로드해 React Query staleTime: Infinity로 캐시 유지.
- 각 서브카테고리 검색창 위에 가중치 상위 5개 태그를 ★ 칩으로 표시, 클릭 시 즉시 선택.
- 전체 선로드 방식(A안)을 선택한 이유는 "지금도 접속할 때 그렇게 오래 걸리는 건 아니라서" lazy 방식의 복잡도를 추가할 필요가 없다는 판단.
- ★ 칩 표시 방식은 "자주 사용 태그를 검색 필드 밑에 띄워주는 형식으로 생각하고 있었다"는 기존 구상과 일치.
```
#### 변경 파일: preference.py, history.py, client.js, GeneratePage.jsx
```
---

### 드롭박스 검색 UX 3종 개선


- 퍼지 검색(fuse.js), 검색창 엔터로 태그 직접 추가, 전체 카테고리 통합 검색창 추가.
- 퍼지 검색 도입 이유는 "두 글자 순서가 바뀌거나 누락, 비슷한 태그가 검색되지 않을 수 있어서 개선하고 싶다"는 실사용 불편에서 출발.
- fuse.js 라이브러리를 직접 구현 대신 선택한 이유는 "나중에 추가하거나 개선할 때 더 낫고, 의존성은 setup.bat으로 자동화 가능"하다는 판단.
- 엔터 직접 추가는 "텍스트 모드랑 왔다갔다 해야 해서 불편"한 실사용 문제 해소. - 전체 통합 검색은 "JSON 태그들을 완전히 내가 구성한 게 아니라서 어디 들어있는지 헷갈릴 때가 있다"는 필요에서 추가.

```
#### 변경 파일: GeneratePage.jsx (import Fuse, buildFuse(), allTagsFlat, globalResults, 검색창 + 후보 목록 블록 전체 교체), package.json (fuse.js 의존성 추가)
```

## v1.2.0 I2I 모드 추가
1. 텍스트 모드 → i2i 모드 통합
- 변경: 모드명 ✏️ 텍스트 → 🖼️ i2i, 텍스트 모드 UI 제거
- 문제/배경: 텍스트 모드가 드롭박스 모드와 기능 중복, i2i 슬롯만 추가하면 통합 - 가능
- 결정: 텍스트 모드 제거하고 i2i 모드로 대체. 프롬프트 수기 입력 유지
- 이유: 드롭박스 모드에서 태그 선택 + 프롬프트 직접 입력 모두 가능하므로 텍스트 모드 별도 유지 불필요
- 대안: 텍스트 모드 유지하고 i2i를 별도 탭으로 분리 → 기각 (UI 복잡도 증가)
```변경 파일: GeneratePage.jsx```

2. i2i 이미지 슬롯 UI
- 변경: 베이스/마스크/레퍼런스 슬롯 추가 (썸네일 카드, 클릭 시 오버레이)
- 문제/배경: 이미지 원본을 그대로 띄우면 스크롤 문제 발생
- 결정: 48px 썸네일로 표시, 클릭 시 fullscreen 오버레이. 히스토리 이미지 피커로 인페인팅/i2i 양쪽에서 접근 가능
- 이유: 공간 효율 + 원본 확인 가능
```변경 파일: GeneratePage.jsx```

3. i2i 해상도 제어
- 변경: 1600px 초과 이미지 업로드 차단
- 문제/배경: VRAM 초과 위험 방지. 업스케일 이미지 선택 시 원본보다 클 수 있음
- 결정: 1600px 초과 시 alert 후 차단. 히스토리에서 업스케일 이미지 선택 시 원본 image_path 자동 선택 (파일명 패턴 판별)
- 이유: 업스케일 이미지는 1600px 초과 가능성 높음
- 대안: 자동 리사이즈 → 장기 계획으로 이연
```변경 파일: GeneratePage.jsx```

4. i2i 백엔드
- 변경: run_i2i 함수 추가, /api/sd/i2i 엔드포인트 추가, i2iUrl client 등록
- 문제/배경: 단순 i2i 워크플로우(i2i_base_workflow.json) 기반 생성 필요
- 결정: 기존 run_inpaint 구조와 동일하게 SSE 스트림으로 구현. 노드 매핑: 1=LoadImage, 6=positive, 7=negative, 9=checkpoint, 11=KSampler(denoise), 14=SaveImage
- 이유: 인페인팅과 동일한 SSE 패턴으로 프론트 재사용 가능
```변경 파일: core/image/generate.py, api/routers/sd.py, src/api/client.js```