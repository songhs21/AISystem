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
변경 파일: GeneratePage.jsx (import Fuse, buildFuse(), allTagsFlat, globalResults, 검색창 + 후보 목록 블록 전체 교체), package.json (fuse.js 의존성 추가)
```

## v1.2.0 I2I 모드 추가
### 1. 텍스트 모드 → i2i 모드 통합
- 변경: 모드명 ✏️ 텍스트 → 🖼️ i2i, 텍스트 모드 UI 제거
- 문제/배경: 텍스트 모드가 드롭박스 모드와 기능 중복, i2i 슬롯만 추가하면 통합 - 가능
- 결정: 텍스트 모드 제거하고 i2i 모드로 대체. 프롬프트 수기 입력 유지
- 이유: 드롭박스 모드에서 태그 선택 + 프롬프트 직접 입력 모두 가능하므로 텍스트 모드 별도 유지 불필요
- 대안: 텍스트 모드 유지하고 i2i를 별도 탭으로 분리 → 기각 (UI 복잡도 증가)
```변경 파일: GeneratePage.jsx```

### 2. i2i 이미지 슬롯 UI
- 변경: 베이스/마스크/레퍼런스 슬롯 추가 (썸네일 카드, 클릭 시 오버레이)
- 문제/배경: 이미지 원본을 그대로 띄우면 스크롤 문제 발생
- 결정: 48px 썸네일로 표시, 클릭 시 fullscreen 오버레이. 히스토리 이미지 피커로 인페인팅/i2i 양쪽에서 접근 가능
- 이유: 공간 효율 + 원본 확인 가능
```변경 파일: GeneratePage.jsx```

### 3. i2i 해상도 제어
- 변경: 1600px 초과 이미지 업로드 차단
- 문제/배경: VRAM 초과 위험 방지. 업스케일 이미지 선택 시 원본보다 클 수 있음
- 결정: 1600px 초과 시 alert 후 차단. 히스토리에서 업스케일 이미지 선택 시 원본 image_path 자동 선택 (파일명 패턴 판별)
- 이유: 업스케일 이미지는 1600px 초과 가능성 높음
- 대안: 자동 리사이즈 → 장기 계획으로 이연
```변경 파일: GeneratePage.jsx```

### 4. i2i 백엔드
- 변경: run_i2i 함수 추가, /api/sd/i2i 엔드포인트 추가, i2iUrl client 등록
- 문제/배경: 단순 i2i 워크플로우(i2i_base_workflow.json) 기반 생성 필요
- 결정: 기존 run_inpaint 구조와 동일하게 SSE 스트림으로 구현. 노드 매핑: 1=LoadImage, 6=positive, 7=negative, 9=checkpoint, 11=KSampler(denoise), 14=SaveImage
- 이유: 인페인팅과 동일한 SSE 패턴으로 프론트 재사용 가능
```변경 파일: core/image/generate.py, api/routers/sd.py, src/api/client.js```

---
## v1.2.1 I2I 마스크 지원

### 5. i2i 마스크 드로잉
- 변경: 마스크 슬롯 클릭 시 드로잉 오버레이 열림, 완료 시 마스크 blob 메모리 보관 후 생성 시 서버 전송
- 문제/배경: i2i에서 특정 영역만 변경하려면 마스크가 필요. 기존 인페인팅과 달리 DB 저장 없이 임시 처리
- 결정: MaskDrawOverlay 컴포넌트 추가. 브러시 드로잉 + 휠 줌 + 중클릭 패닝. 완료 버튼으로 마스크 blob 확정. 생성 시 마스크 있으면 `/api/sd/i2i-mask`, 없으면 `/api/sd/i2i` 분기
- 이유: 인페인팅 캔버스 구조 재활용, DB 저장 불필요한 임시 마스크는 메모리에만 보관
- 대안: InpaintCanvas 그대로 재사용 → 기각 (DB 저장 로직 포함, i2i 슬롯 UI와 맞지 않음)
```변경 파일: GeneratePage.jsx, core/image/generate.py, api/routers/sd.py, src/api/client.js, src/hooks/useSSE.js```

### 6. i2i 마스크 워크플로우
- 변경: `i2i_mask_workflow.json` 추가, `run_i2i_mask` 함수 추가, `/api/sd/i2i-mask` 엔드포인트 추가
- 문제/배경: 마스크 영역만 재생성하는 인페인팅 파이프라인 필요
- 결정: 기존 인페인팅 replace 워크플로우(ControlNet inpainting 구조) 재활용. 노드 매핑: 1=LoadImage(베이스), 22=LoadImageMask, 18=positive, 19=negative, 3=checkpoint, 8=KSampler, 10=SaveImage
- 이유: 워크플로우 구조가 동일하고 DB 저장만 제거하면 되므로 재활용이 효율적
```변경 파일: assets/workflow/i2i_mask_workflow.json, core/image/generate.py, api/routers/sd.py, config/PATH.py```

---

## v1.2.2 전체 태그 검색 입력 및 최적화

### 11. 전체 태그 검색 방향키 네비게이션 + 엔터 입력
- 변경: 전체 태그 검색 드롭다운에서 방향키 위/아래로 항목 이동, 엔터로 선택 항목 추가
- 문제/배경: 검색 후 마우스 클릭만 가능해서 키보드로 빠르게 태그 추가 불가
- 결정: `globalNavIndex` state 추가, 방향키로 인덱스 이동, 엔터로 선택 항목 dropSelections에 추가. 마우스 호버 시에도 navIndex 동기화. 검색어 변경 시 navIndex 초기화
- 이유: 키보드 네비게이션으로 태그 선택 속도 향상
- 변경 파일: src/pages/GeneratePage.jsx

### 12. 전체 태그 검색 공백 → 언더바 자동 치환
- 변경: 검색 input onChange에서 스페이스바 입력 시 언더바로 자동 치환
- 문제/배경: SD 태그는 공백 대신 언더바를 사용하는데 검색 시 공백 입력하면 매칭 안 됨
- 결정: `e.target.value.replace(/ /g, '_')` 적용
- 이유: 태그 입력 규칙에 맞게 자동 변환
- 변경 파일: src/pages/GeneratePage.jsx

### 13. 직접 입력 태그(manualTags) 추가
- 변경: 전체 검색창에서 방향키 선택 없이 엔터 입력 시 검색어를 manualTags로 추가, 최종 프롬프트에 반영
- 문제/배경: 드롭박스 카테고리에 없는 태그를 프롬프트에 추가할 방법 없음
- 결정: `manualTags` state 추가, dropPrompt useMemo에서 dropPart + manualPart 합산. 미리보기에 초록색 칩으로 별도 표시, 클릭으로 제거 가능
- 이유: 카테고리 미등록 태그도 프롬프트에 자유롭게 추가 가능하게
- 변경 파일: src/pages/GeneratePage.jsx

### 14. WebSocket prompt_id 필터링
- 변경: `_ws_progress`에 `prompt_id` 파라미터 추가, 다른 프롬프트 이벤트 무시
- 문제/배경: 큐 대기/캐시 로드 중 다른 프롬프트의 `executing node=None` 이벤트를 받아 조기 종료되는 경우 발생
- 결정: `data.prompt_id` 체크해서 현재 프롬프트 이벤트만 처리. 모든 run 함수에 prompt_id 전달
- 이유: 멀티 큐 환경에서 WebSocket 이벤트 혼선 방지
- 변경 파일: core/image/generate.py

### 15. constants 모델별 설정 갱신 및 sd.py 반영
- 변경: `MODEL_RESOLUTION`에 모델별 sampler_name, scheduler, hires_* 키 추가. sd.py에서 sampler/scheduler를 ComfyUI 형식으로 변환 후 워크플로우에 반영
- 문제/배경: 추가된 모델들의 권장 KSampler 설정(sampler, scheduler)이 워크플로우에 반영되지 않고 기본값으로만 동작
- 결정: constants.py에 모델별 sampler_name/scheduler 추가. sd.py에 SAMPLER_MAP/SCHEDULER_MAP 상수 추가해서 A1111 표기를 ComfyUI 표기로 변환 후 workflow["3"]에 주입
- 이유: 모델별 권장 설정 준수로 생성 품질 최적화. A1111과 ComfyUI의 sampler/scheduler 명칭이 달라 매핑 테이블 필요
- 대안: 없음
- 변경 파일: config/constants.py, api/routers/sd.py


## v1.2.3 LoRA 지원 추가

### 16. LoRA 동적 패치 지원

- 변경: 드롭박스/i2i/i2i-mask 모드 전체에 LoRA 적용 기능 추가
- 문제/배경: 특정 캐릭터/화풍 재현을 위해 LoRA 적용 필요. JSON 파일 분리 방식은 기능 조합 증가 시 파일 수 기하급수적 증가
- 결정: Python 패치 함수 방식으로 베이스 워크플로우에 동적 노드 추가. find_node_by_type()으로 노드 ID 하드코딩 없이 탐색
- 이유: 워크플로우 JSON 파일 추가 없이 기능 조합 자유롭게 확장 가능. ControlNet/IP-Adapter 추가 시 동일 패턴 재사용
- 대안: 기능 조합별 JSON 파일 분리 관리 (A안) — 조합 증가 시 최대 16개 파일 필요로 기각

- 변경 파일:
```
  - config/PATH.py — LORA_DIR 추가
  - core/image/generate.py — find_node_by_type(), apply_lora_patch() 추가, run_i2i/run_i2i_mask 시그니처에 lora_name/lora_strength 추가
  - api/routers/sd.py — GenerateRequest/I2IRequest lora 필드 추가, /loras 엔드포인트 추가, i2i-mask Form 파라미터 추가, 중복 GenerateRequest 선언 제거
  - src/api/client.js — sdApi.loras() 추가
  - src/pages/GeneratePage.jsx — loraName/loraStrength state 추가, LoRA UI 추가, generate 함수 전 엔드포인트 payload에 lora 파라미터 반영
  ```

### 17. 전체 태그 검색 버그 수정 및 성능 개선

- 변경: 검색 결과 없을 때 엔터 입력 시 manualTags 추가 안 되는 버그 수정, Fuse 검색 성능 개선
- 문제/배경: globalResults.length === 0 조건에서 early return해버려 검색 결과 없는 태그를 엔터로 추가 불가. 매 입력마다 Fuse 인스턴스 새로 생성 + 6449개 전체 순회로 14자 이상 입력 시 버벅임
- 결정: 방향키/엔터 조건 분리. Fuse 인스턴스 useRef로 캐싱, 검색에 150ms 디바운스 적용
- 이유: 검색 결과 없는 태그도 manualTags로 추가 가능해야 함. Fuse 인스턴스 재생성 비용 제거 + 디바운스로 타이핑 중 불필요한 순회 방지
- 변경 파일: src/pages/GeneratePage.jsx


## v1.2.4 UI 개선 및 버그 수정

### 18. 부정 프롬프트 위치 개편 + 고급 옵션 토글
- 변경: 우측 패널 제거, 부정 프롬프트를 최종 프롬프트 미리보기 아래로 이동, 1차/2차 카테고리 버튼을 고급 옵션 토글로 이동
- 문제/배경: 우측 패널이 textarea 하나만 들고 18% 공간 차지, 카테고리 버튼이 항상 표시돼 헤더가 복잡함
- 결정: 부정 프롬프트 고정 헤더 내 배치, 카테고리 버튼 고급 옵션 접기/펼치기로 이동
- 이유: 중앙 스크롤 영역 확보, 평소엔 검색+미리보기+부정 프롬프트만 보여서 깔끔
- 변경 파일: src/pages/GeneratePage.jsx

### 19. tagConfig.js 분리
- 변경: CATEGORY_ORDER, CATEGORY_CONFIG, 순수 유틸 함수들을 src/constants/tagConfig.js로 분리
- 문제/배경: GeneratePage.jsx가 카테고리 설정으로 인해 과도하게 길어짐
- 결정: export로 분리, GeneratePage.jsx에서 import
- 이유: 파일 가독성 향상, 나중에 다른 페이지에서도 재사용 가능
- 변경 파일: src/constants/tagConfig.js, src/pages/GeneratePage.jsx

### 20. LoRA 트리거 워드 지원
- 변경: lora_triggers.json 추가, apply_lora_patch에서 LoRA별 트리거 워드를 positive 프롬프트 앞에 자동 추가
- 문제/배경: LoRA마다 활성화 트리거 워드가 다른데 매번 수동 입력 필요
- 결정: JSON 파일로 LoRA명→트리거 워드 매핑 관리, positive_node_id 파라미터로 워크플로우별 대응
- 이유: JSON만 편집하면 코드 수정 없이 트리거 워드 관리 가능
- 변경 파일: assets/lora_triggers.json, config/PATH.py, core/image/generate.py

### 21. manualTags + dropSelections 통합 순서 관리
- 변경: manualTags 별도 state 제거, promptOrder에 isManual 필드 추가해 통합 관리. 쉼표 기반 멀티 태그 입력, localStorage 유지, 드래그 순서 통합
- 문제/배경: manualTags가 별도 배열이라 드롭박스 태그와 순서 섞기 불가능. 새로고침 시 날아감
- 결정: promptOrder = [{subKey, en, isManual}] 단일 구조로 통합. isManual=true는 초록색, false는 보라색으로 구분
- 이유: dnd-kit으로 전체 순서 통합 관리, localStorage로 새로고침 후 복원
- 대안: manualTags 유지하고 별도 dnd 컨텍스트 — 두 영역 간 드래그 불가로 기각
- 변경 파일: src/pages/GeneratePage.jsx

### 22. 최종 프롬프트 카테고리 표시
- 변경: 프롬프트 칩 앞에 [서브카테고리] 표시 추가
- 문제/배경: 복장 태그가 겹쳐서 생성이 안 될 때 어느 카테고리인지 파악하기 어려움
- 결정: SortableTag에 subLabel prop 추가, 칩 앞에 [카테고리명] 항상 표시
- 이유: 태그 카테고리 파악이 빨라져 프롬프트 정리 시간 단축
- 변경 파일: src/pages/GeneratePage.jsx

### 23. 전체 태그 검색 공백 처리 개선
- 변경: onChange 공백→언더바 치환 제거, 엔터 입력 시 각 태그에 trim+언더바 치환 적용
- 문제/배경: onChange에서 치환하면 쉼표 뒤 공백도 언더바로 변환돼 멀티 태그 입력 방해
- 결정: 입력 중엔 공백 그대로 표시, 엔터로 확정할 때만 치환
- 변경 파일: src/pages/GeneratePage.jsx

### 24. ComfyUI 시작/종료 상태 표시
- 변경: SD 토글 시 시작중/종료중 텍스트 + 프로그레스 바 표시, 시작 시 실제 로그 SSE 수신
- 문제/배경: ComfyUI 켜고 끌 때 진행 상태를 알 수 없었음
- 결정: 시작은 stdout 캡처 → SSE 스트림으로 실제 로그 표시, 종료는 폴링 기반 가짜 프로그레스
- 이유: 시작 로그는 실제 진행 상황 반영 가능, 종료는 로그 없어서 폴링으로 대체
- 변경 파일: core/system/comfy_manager.py, api/routers/system.py, src/components/SystemStatus.jsx

### 25. ComfyUI kill 버그 수정
- 변경: kill_comfy에 psutil 기반 포트 8188 프로세스 강제 종료 추가
- 문제/배경: AISystem 외부에서 실행된 ComfyUI는 _comfy_process가 None이라 kill 스킵됨
- 결정: psutil로 8188 포트 점유 프로세스 탐색 후 강제 종료
- 변경 파일: core/system/comfy_manager.py

### 26. 히스토리 피드백 오버레이 스크롤 수정
- 변경: FeedbackEditorPanel 태그 목록 div overflow hidden → minHeight:0 추가로 스크롤 정상화
- 문제/배경: TagPanel 영역에 스크롤이 안 됨
- 변경 파일: src/pages/HistoryPage.jsx

### 27. I2V 생성 + V2V 인페인팅 파이프라인 (v1.3.0)

- 변경
  - `core/video/i2v_generate.py`: 이미지→비디오 생성 (Wan2.1 I2V 14B GGUF, `run_i2v()` SSE 제너레이터)
  - `core/video/v2v_inpainting.py`: 영상 프레임 단위 의류/부위 교체 인페인팅 파이프라인
    - 감지: BiRefNet(ONNX, 캐릭터 분리) → GroundingDINO(부위 탐지, dress/hand/arm/face) → SAM(정밀 마스크)
    - 마스크 병합: IoU 기반 Union-Find로 겹치는 부위 마스크 통합
    - 생성: 크롭 → IPAdapter(원본 프레임을 참조 이미지로) → ComfyUI 인페인팅 워크플로우 → 언샤프 블렌딩
    - 프레임 추출/합성: OpenCV + ffmpeg
  - `api/routers/sd.py`: `/api/sd/i2v` 엔드포인트로 I2V 생성 연동 (SSE progress/done)
  - `assets/workflow/i2v_workflow.json`: WanImageToVideo 기반 I2V 워크플로우 (GGUF 로더, CLIP Vision 인코딩 포함)

- 문제·배경
  - Phase 로드맵상 정지 이미지 생성 다음 단계인 영상 생성/편집 착수
  - ComfyUI 노드 그래프 상에서 장기간 시행착오(파라미터, 워크플로우 구조 실험) 후, 동작 확인된 방식을 코드로 편입

- 결정
  - I2V: Wan2.1 14B 720p GGUF(Q4_K_M) 모델 채택, 해상도는 32배수 정렬 + 패딩으로 입력 이미지 보정
  - V2V 인페인팅: 프레임별 2-패스 처리 — 1패스 감지(모델 로드 후 전체 프레임 마스크 추출, 이후 언로드), 2패스 인페인팅(ComfyUI 반복 호출) — VRAM 확보 목적
  - IPAdapter를 원본 프레임 자체를 참조 이미지로 사용해 프레임 간 일관성 확보
  - 인페인팅 시드 고정(42)으로 프레임 간 통일성 확보

- 대안 (시행착오 경과)
  - VACE 모델 사용 → 소형 모델의 경우 인페인팅 영향도가 낮아 기각, 대형 모델의 경우 사양 부족으로 기각
  - RMBG 세그먼트 기반 부위별 마스크 자동화 → 마스크 인식률이 낮아 기각, SAM으로 전환
  - SAM 부위별 마스크 → 동작은 하나 손처럼 상대적으로 작은 부위를 인식 못하는 문제 발생
  - 해결책: 입력 이미지에서 배경 제거 후 이미지 사이즈를 키워 손 인식률 확보
  - 부위별 개별 인페인팅 시도 → 마스크 경계마다 노이즈 발생, 프레임 퀄리티 저하
  - 해결책: 마스크를 통합해 프레임당 한 번의 인페인팅으로 처리 → 퀄리티 유지 (현재 채택된 IoU 기반 마스크 병합 로직의 근거)
  - 이후 IPAdapter, 템포럴 일관성 등 프레임 간 통일성 확보 기법 추가 적용

- 변경 파일
  - 신규: `core/video/i2v_generate.py`, `core/video/v2v_inpainting.py`, `assets/workflow/i2v_workflow.json`
  - 수정: `api/routers/sd.py` (`/i2v` 엔드포인트 추가)

- 미해결 (다음 마일스톤 — v1.3.x 또는 이후)
  - 색상 캐스트 (배경색이 VAE 인코딩에 섞여듦 — 크롭 전 배경 중립화 필요)
  - `ImageUncropByMask` 경계부 색 번짐(chromatic aberration 유사 아티팩트)
  - 손 복구 파이프라인 미구현 (A/B/C안 중 미선택 — Optical Flow 기반 C안 유력)
  - CUDA DLL 수동 등록 블록 메인 엔트리포인트 미통합
  - `v2v_pipeline.py`(01-test 실험용) 잔존 여부 확인 필요 — `v2v_inpainting.py`와 중복/구버전 가능성

### 28. 로컬 LLM 통합 (Ollama) (v1.4.0)

- 변경
  - Ollama 기반 로컬 LLM 채팅 기능 신규 추가
  - `core/llm_db.py`: 채팅 전용 별도 SQLite DB (`llm_chat.db`) — `chat_sessions`, `chat_messages` 테이블
  - `api/routers/llm.py`: `/api/llm/chat`, `/api/llm/sessions` (생성/목록/삭제/수정), `/api/llm/history/{id}`
  - `core/system/ollama_manager.py`: Ollama 프로세스 start/kill, `/api/ps` 기반 VRAM 조회
  - `api/routers/system.py`: `/api/system/ollama/start`, `/kill`, `/vram`, `/unload-model` 추가, `/status`의 llm 체크를 `is_ollama_alive()`로 교체
  - `config/PATH.py`: `LLM_DB_PATH`, `OLLAMA_APP_PATH` 추가
  - `src/pages/LLMPage.jsx`: 세션 목록(생성/전환/삭제/제목 수정), 메시지별 소요시간(초) 표기, FastAPI 경유로 전면 교체 (기존 Ollama 직접 호출 방식 제거)
  - `src/api/client.js`: `llmApi`, `ollamaApi` 추가
  - `src/components/SystemStatus.jsx`: SD/LLM VRAM 두 줄 표시, LLM 상태 3단계 색상(꺼짐/서버만 켜짐·모델 언로드/모델 로드됨), LLM start/kill 토글 + 모델 언로드 버튼

- 문제·배경
  - Phase 5 계획에 있던 로컬 LLM(day-to-day 채팅용) 착수
  - 용도: 범용 대화, 코딩 보조, 추후 SD 프롬프트 검색/추천/번역, Live2D 컴패니언 확장의 기반

- 결정
  - 서빙 백엔드: Ollama (FastAPI 연동 용이성, RTX 5070 Ti 16GB에서 14B 4bit 여유)
  - 모델: `qwen2.5:14b` (Q4_K_M) — 한국어 품질 + 코딩 보조 + 범용 대화 균형
  - 채팅 DB: 이미지 생성 DB(`data.db`)와 별도 파일(`llm_chat.db`)로 분리, 필요시 애플리케이션 레벨에서 조인/캐시하는 방식으로 확장 예정
  - 세션 관리: `chat_sessions` 단위로 분리, 세션별 삭제/제목 수정 가능
  - 응답 방식: 스트리밍 대신 일반 응답 채택 (완료까지 총 소요시간은 동일, 소요시간 텍스트 표기로 대체) — 추후 필요시 재검토
  - LLM VRAM 표시: Ollama `/api/ps`로 로드된 모델 기준 개별 조회, GPU 총 용량은 ComfyUI `system_stats` 값을 공유해서 퍼센트 계산
  - LLM start/kill: Ollama 프로세스(`ollama.exe`, `ollama app.exe`) 자체를 종료/재실행하는 방식 (서비스 등록 아님, 시작프로그램에 등록되어 있음을 확인)

- 대안
  - LLM 서빙: vLLM, LM Studio 검토 후 기각 (1인 로컬 사용에 오버스펙이거나 API 연동이 Ollama보다 번거로움)
  - VRAM 표시: GPU 전체 사용량 통합 표시(`nvidia-smi` 기반) 검토했으나, SD/LLM 개별 정확도를 우선해 각 프로세스 자체 기준으로 결정

- 변경 파일
  - 신규: `core/llm_db.py`, `api/routers/llm.py`, `core/system/ollama_manager.py`
  - 수정: `api/main.py`, `config/PATH.py`, `api/routers/system.py`, `src/pages/LLMPage.jsx`, `src/api/client.js`, `src/components/SystemStatus.jsx`

- 미해결 (다음 마일스톤)
  - `start_ollama()` 콘솔 창 숨김(`CREATE_NO_WINDOW`) 반영 확인
  - 타임아웃(현재 300초) — ComfyUI 동시 구동 시 응답 지연 대응 여부 재검토
  - 실제 통합 테스트 (세션 생성/삭제/수정, VRAM 3단계 전환, start/kill 토글) 미완료
  - SD 프롬프트 검색/추천/번역 기능 연동 (미착수)
  - Live2D 컴패니언 확장 (장기, 미착수)

  ### 29. 로컬 LLM 통합 (Ollama) (v1.4.0)

- 변경
  - Ollama 기반 로컬 LLM 채팅 신규 추가
  - `core/llm_db.py`: 채팅 전용 별도 SQLite DB(`llm_chat.db`), `chat_sessions` / `chat_messages`(`image_path` 컬럼 포함)
  - `api/routers/llm.py`
    - `/api/llm/chat`(일반 응답), `/api/llm/chat-stream`(SSE 스트리밍, `token`/`done`/`error` 이벤트)
    - 세션 생성/목록/삭제/제목 수정, 히스토리 조회(`elapsed_ms`, `image_path` 포함)
    - 이미지 첨부(base64 인코딩 후 Ollama `images` 필드로 전달), 이전 이미지 문맥 포함 on/off 및 최대 장수 제한
    - 스트리밍 중 연결이 끊겨도 그때까지 생성된 부분 응답을 DB에 저장
  - `core/system/ollama_manager.py`: Ollama 프로세스 start/kill, 생존 확인, `/api/ps` 기반 VRAM 조회
  - `api/routers/system.py`: `/ollama/start`, `/kill`, `/vram`, `/unload-model` 추가, `/status`의 llm 체크를 `is_ollama_alive()`로 교체
  - `config/PATH.py`: `LLM_DB_PATH`, `OLLAMA_APP_PATH` 추가
  - `src/pages/LLMPage.jsx`
    - 세션 목록(생성/전환/삭제/제목 수정), 신규 세션 버튼 중복 클릭 방지
    - 답변별 소요시간 표기, 스트리밍 실시간 출력 및 중단 버튼
    - 이미지 첨부 3방식: 파일 선택, 클립보드 붙여넣기, 드래그앤드롭 + 생성 탭 히스토리 이미지 피커
    - 세션 복원 시 첨부 이미지 썸네일 표시
    - 기존 Ollama 직접 호출 방식 제거, FastAPI 경유로 전환
  - `src/api/client.js`: `llmApi`, `ollamaApi` 추가
  - `src/components/SystemStatus.jsx`: SD/LLM VRAM 두 줄 표시, LLM 상태 3단계 색상(꺼짐 / 서버만 켜짐·모델 언로드 / 모델 로드됨), LLM start·kill 토글, 모델 언로드 버튼
  - `src/styles/global.css`: `100vh`를 `100dvh`로 보완 (안드로이드 브라우저 주소 표시줄 표시/숨김 시 화면 하단 잘림 해소)

- 문제·배경
  - Phase 5의 로컬 LLM 착수. 용도는 범용 대화, 코딩 보조, SD 프롬프트 검색/추천/번역, 이미지 입력 기반 I2V 프롬프트 생성, 장기적으로 Live2D 컴패니언 확장
  - 기존 `LLMPage.jsx`는 브라우저에서 Ollama를 직접 호출하고 세션·기록 개념이 없었음
  - 세션 생성 버튼에 반응 피드백이 없어 연속 클릭으로 세션이 여러 개 생성되는 문제 발생
  - ComfyUI 영상 생성 중 채팅 시 응답이 느려짐(GPU 경합)

- 결정
  - 서빙: Ollama (FastAPI 연동 용이, 1인 로컬 사용에 적합)
  - 모델: 초기 `qwen2.5:14b`로 설치 후, 검열 해제 및 이미지 분석 용도로 `sorc/qwen3.5-instruct-heretic:9b`(비전 지원)로 교체. 이미지 분석 품질 등을 보고 14B급 추가 검토
  - 채팅 DB는 이미지 생성 DB(`data.db`)와 별도 파일로 분리. 필요 시 애플리케이션 레벨에서 조인, 부하가 크면 캐시로 확장
  - 세션 단위로 대화 분리
  - 소요시간은 답변 완료 후 총 시간(초)으로 표기
  - LLM VRAM은 Ollama `/api/ps`로 로드된 모델 기준 개별 조회, 총 VRAM은 ComfyUI `system_stats` 값을 공유해 퍼센트 계산
  - LLM start/kill은 Ollama 프로세스(`ollama.exe`, `ollama app.exe`) 종료/재실행. 시작프로그램 등록으로 서비스가 아님을 확인. 트레이 앱이라 콘솔 로그가 없어 창은 숨김 처리(`CREATE_NO_WINDOW`)
  - 이미지 첨부는 파일 복사 없이 경로만 DB에 기록. 붙여넣기·드롭 이미지는 기존 `/api/system/upload` 재사용, 히스토리 이미지는 원본 `image_path` 참조
  - 이전 이미지의 문맥 포함은 사용자가 on/off 및 최대 장수를 조절(기본 off, 최대 2장)
  - 스트리밍은 기존 `/chat`을 유지한 채 `/chat-stream`을 신규 추가해 롤백 가능하게 구성, 프론트는 `useSSE` 훅 수정 없이 `LLMPage`에서 `fetch`로 직접 수신
  - 스트리밍 중 끊김 시 부분 응답도 저장

- 사용자 제안 (직접 낸 아이디어)
  - 채팅 DB를 이미지 DB와 분리하고, 부하가 크면 캐시로 들고 있다가 DB 변경 시 갱신하는 방식으로 확장
  - LLM 서비스도 SD처럼 VRAM 표시, 모델 언로드, start/kill 토글과 진행 표시를 두는 구조 제안
  - VRAM 표시를 SD/LLM 윗줄·아랫줄로 구분
  - 서버는 켜져 있으나 모델이 언로드된 상태를 노랑/주황색으로 구분하는 3단계 상태 표시 (Claude가 3단계 구조를 제시했고 색상 구분은 사용자가 확정)
  - 이전 이미지 참조를 요청별로 on/off, 안 되면 횟수 상한으로 제어하자는 요구
  - 이미지 입력 방식을 파일 선택 + 붙여넣기 + 드래그앤드롭으로 확장, 별도 파일 저장 없이 기존 히스토리 피커 재사용
  - 스트리밍 중 끊겨도 부분 응답 저장

- 대안
  - LLM 서빙: vLLM, LM Studio 검토 후 기각 (1인 로컬 사용에 오버스펙이거나 API 연동이 번거로움)
  - VRAM 표시: GPU 전체 사용량 통합 표시(`nvidia-smi` 기반) 검토 후 각 프로세스 자체 기준으로 결정
  - 모델: 검열 해제 방식으로 abliterated와 uncensored 파인튜닝(Dolphin, Hermes 계열) 비교. 한국어 품질 유지를 위해 Qwen 계열 베이스 우선
  - 스트리밍 수신: `useSSE` 훅 확장 검토 후 기각 (다른 곳에서 쓰는 훅에 부작용 위험)
  - 이미지 저장: 별도 파일 저장 방식 검토 후 기각 (기존 경로 재사용으로 충분)
  - DB 마이그레이션: `PRAGMA` 기반 코드 마이그레이션 대신 1회 수동 쿼리 + `CREATE TABLE`에 컬럼 추가로 진행

- 변경 파일
  - 신규: `core/llm_db.py`, `api/routers/llm.py`, `core/system/ollama_manager.py`
  - 수정: `api/main.py`, `config/PATH.py`, `api/routers/system.py`, `src/pages/LLMPage.jsx`, `src/api/client.js`, `src/components/SystemStatus.jsx`, `src/styles/global.css`

- 미해결 (다음 마일스톤)
  - 히스토리 이미지 피커를 `LLMPage.jsx` 안에 임시로 정의해 둔 상태, 공용 컴포넌트로 분리 필요 (생성 탭 쪽 정의와 함께 정리)
  - I2V 프롬프트 생성 전용 시스템 프롬프트/프리셋 미구현 (현재는 매번 직접 요청)
  - SD 프롬프트 검색/추천/번역 연동 미구현
  - 세션별 모델 선택 UI 없음 (현재 서버 `DEFAULT_MODEL` 고정), 기존 세션의 표시 모델명이 옛 값으로 남을 수 있음
  - 14B급 모델 추가 여부 결정 (이미지 분석 품질과 VRAM 여유 비교 필요)
  - thinking 모드 사용 시 `<think>` 블록 노출 여부 미확인
  - 스트리밍 중 중단 시 부분 응답 저장 동작의 실측 확인 필요
  - LLM VRAM 퍼센트가 ComfyUI 생존에 의존 (ComfyUI가 꺼져 있으면 `-` 표시), GPU 총 용량을 별도로 구하는 방식 미결정
  - ComfyUI 동시 구동 시 채팅 응답 지연 및 타임아웃(현재 300초) 대응 여부 결정
  - `start_ollama()`의 `CREATE_NO_WINDOW` 반영 여부 확인
  - `/api/system/image`, `/video`에 경로 검증이 없음 (임의 경로 읽기 가능, 로컬 전용이라 우선순위 낮음)
  - `system.py`의 `SwitchRequest`, `client.js`의 `systemApi.switch`에 남은 옛 모델명(`qwen3:14b`) 정리
  - 미사용이 된 `/api/llm/chat`(비스트리밍)과 `llmApi.chat` 유지 여부 결정
  - Live2D 컴패니언 확장 (장기)


### 30. GeneratePage 모드별 함수 분리 및 레이아웃 개편 (v1.5.0)

- 변경
  - `GeneratePage.jsx`를 드롭박스(`DropdownModePanel`)/i2i(`I2iModePanel`)/비디오(`VideoModePanel`) 세 개의 독립 함수 컴포넌트로 분리
  - 레이아웃을 상단 고정 바 방식에서, 뷰포트를 중심에 두고 왼쪽에 생성 옵션 서랍(오버레이, 뷰포트를 밀지 않음), 오른쪽에 태그 패널(뷰포트를 밀어냄)을 두는 구조로 변경
- 문제/배경
  - 새로고침 시 i2v 입력값 유지 로직을 작성하던 중, `negative` 등 동일한 이름의 state가 `GeneratePage`와 `VideoModePanel` 두 스코프에 따로 존재해 혼동 발생
  - 저장/복원 로직을 실수로 `GeneratePage`에 작성해 실제 입력 필드(`VideoModePanel` 소유)에 반영되지 않는 문제 발견
  - 기존 레이아웃(결과 미리보기 좌측 세로 배치)은 정사각형 결과 이미지가 잘리거나 옵션 UI가 한 화면에 안 들어오는 문제가 있었음
- 결정
  - 모드별 state를 각자의 함수 컴포넌트 스코프로 캡슐화
  - 공유 state(`checkpoint`, `result`, `meta`, `i2iOverlay`, `showHistoryPicker`, job 관련 상태)만 `GeneratePage`에 유지하고 props로 하위 전달
  - 레이아웃은 뷰포트 중심 + 좌측 오버레이 서랍(옵션) + 우측 밀림형 패널(태그)로 변경
- 이유
  - state 스코프를 명확히 분리하면 동일 이름 변수로 인한 혼동을 원천 차단할 수 있음
  - 오버레이형 서랍은 뷰포트 크기를 최대한 보존하면서도 옵션을 언제든 접근 가능하게 함
- 대안
  - 옵션 패널을 상단 고정 바로 유지하고 이미지 비율만 조정하는 방식도 검토했으나, 옵션이 많아 한 화면에 안 들어오는 문제가 근본적으로 해결되지 않아 기각
- 변경 파일: `src/pages/GeneratePage.jsx`

### 31. LoRA 모드별 지역화 및 폴더 공유 이슈 확인 (v1.5.0)

- 변경
  - LoRA 선택(`loraName`, `loraStrength`) UI를 드롭박스/i2i/비디오 세 모드 각각에 독립적으로 노출
  - LoRA 목록 조회(`sdApi.loras()`)는 각 패널에서 개별 호출(react-query 캐시로 중복 요청 없음)
- 문제/배경
  - 기존엔 드롭박스 모드에만 LoRA UI가 있었음
  - 확장 과정에서 이미지(SDXL)용과 동영상(Wan) LoRA가 동일한 `LORA_DIR` 폴더를 공유하고 있다는 사실 확인 — 두 아키텍처는 LoRA 레이어 구조가 달라 호환되지 않을 가능성이 높음
- 결정
  - 지금은 폴더 분리 없이 모드별 UI만 노출. 폴더 분리는 추후 과제로 보류
- 이유
  - 당장 기능 확장에 폴더 분리가 필수는 아니며, 실제 비호환 여부를 검증한 뒤 분리하는 것이 효율적
- 변경 파일: `src/pages/GeneratePage.jsx`

### 32. i2v 워크플로우 High/Low 듀얼 KSampler 전환 (v1.5.0)

- 변경
  - `core/video/i2v_generate.py`의 `run_i2v`를 단일 모델/단일 KSampler 구조에서 High/Low 듀얼 GGUF 로더 + `KSamplerAdvanced` 2단 구조로 변경
  - `api/routers/sd.py`의 `I2VRequest`를 `steps`/`cfg`/`denoise` 대신 `high_steps`/`low_steps`/`cfg` 필드로 변경
- 문제/배경
  - Wan 2.2 기반 파인튜닝 모델(Lightning Edition 등)이 High-noise/Low-noise 두 체크포인트로 배포되며, 단일 모델로 전체 스텝을 처리하면 결과가 붕괴(형체 소실, 모자이크성 노이즈)됨
  - 초기엔 바닐라 Wan 2.1 기준 워크플로우(steps 25, cfg 5.5)를 그대로 쓰다가 과노출 문제 발생 → steps/cfg를 낮추며 원인을 좁혀가다 High/Low 분리 필요성 확인
- 결정
  - GGUF 로더 2개(High/Low) + `KSamplerAdvanced` 2개를 순차 연결(High의 LATENT 출력 → Low의 latent_image 입력)하는 구조로 전환
  - 프론트에서 `high_steps`/`low_steps`를 각각 입력받아 최종 `steps`(합산)와 `start_at_step`/`end_at_step`으로 변환
- 이유
  - Wan 2.2 파인튜닝 모델의 표준 사용 방식이 High/Low 분리 샘플링이며, 이를 따르지 않으면 모델 자체가 정상 동작하지 않음
- 변경 파일: `core/video/i2v_generate.py`, `api/routers/sd.py`, `assets/workflow/i2v_workflow.json`, `src/pages/GeneratePage.jsx`

### 33. i2v 입력 새로고침 유지 (v1.5.0)

- 변경
  - `VideoModePanel`의 입력값(baseImage, prompt, negative, seed, width, height, length, highSteps, lowSteps, cfg, loraName, loraStrength)을 `localStorage`의 `i2vDraft` 키에 객체로 통합 저장. 마운트 시 자동 복원
- 문제/배경
  - 새로고침 시 i2v 탭의 입력값이 전부 초기화됨
- 결정
  - t2i 모드(`dropSelections` 등)가 쓰던 개별 `useEffect` + localStorage 패턴 대신, 여러 필드를 객체 하나로 묶어 단일 `useEffect`로 저장/복원
- 이유
  - 필드 수가 많아 개별 관리 시 코드량이 늘어남. t2i 쪽도 추후 동일 패턴으로 통합 예정
- 변경 파일: `src/pages/GeneratePage.jsx`

### 34. 태그 패널/왼쪽 서랍 상호작용 버그 수정 (v1.5.0)

- 변경
  - 왼쪽 서랍을 닫아도 오른쪽 태그 패널이 함께 사라지는 문제 수정
  - 이미지 생성 시작 시 태그 패널이 닫히지 않고 이전 상태가 유지되는 문제 수정
  - 최종 프롬프트 미리보기의 태그 칩 영역이 고정 높이(`maxHeight: 80`)로 잘리는 문제 수정
- 문제/배경
  - `DropdownModePanel` 내부에 태그 패널 UI와 관련 state(`tags`, `tagPanelOpen` 등)가 중복 선언되어 있었고, 이 중복 패널이 왼쪽 서랍 DOM 안에 위치해 있어 서랍이 `display: none`이 되면 함께 사라졌음
  - `generate()` 함수가 `setTagPanelOpen`을 호출할 방법이 없어 새 생성 시작 시 이전 태그 패널 상태(펼침/접힘, 뷰포트 밀림)가 그대로 유지됐음
  - 카테고리 라벨이 길어 태그 칩이 2줄로 줄바꿈될 때 `overflow` 처리가 없어 내용이 잘림
- 결정
  - `DropdownModePanel`의 지역 `tags`/`tagPanelOpen` 등 관련 state와 중복 UI 블록을 전부 제거하고 `GeneratePage`가 소유한 것을 props로 전달받아 사용하도록 통일
  - `setTagPanelOpen`을 `DropdownModePanel`에 props로 전달, `generate()` 시작 시 `setTagPanelOpen(false)` 호출, 완료 시 `onGenerated` 콜백으로 `setTagPanelOpen(true)` 호출
  - 태그 칩 컨테이너에 `maxHeight: 150, overflowY: 'auto'` 적용
- 이유
  - state는 단일 소유자(`GeneratePage`)만 가져야 중복/동기화 문제가 발생하지 않음
- 변경 파일: `src/pages/GeneratePage.jsx`

### 35. 왼쪽 서랍 UI 개선 — 스플릿 리사이즈, 파일탭 버튼 (v1.5.0)

- 변경
  - `DropdownModePanel` 내부에서 상단 헤더(검색/프롬프트 미리보기/LoRA/부정 프롬프트/고급 옵션)와 하단 카테고리 목록을 드래그로 비율 조절 가능한 2단 스플릿 구조로 변경(초기 비율 4:6, 각 단 독립 스크롤)
  - 왼쪽 서랍 토글 버튼을 화면 좌상단 고정에서, 서랍이 열렸을 때 서랍 오른쪽 가장자리에 붙는 파일탭 형태로 변경
- 문제/배경
  - 카테고리 목록이 길어 스크롤이 필요했으나 헤더 영역과 비율 조절이 불가능했음
  - 토글 버튼이 좌상단에 고정되어 있어 서랍이 열려도 위치가 바뀌지 않아 사용성이 떨어짐
- 결정
  - `topRatio` state와 마우스/터치 드래그 핸들러로 두 영역 높이를 15%~85% 범위에서 조절 가능하게 구현
  - 토글 버튼은 `left` 값을 `leftDrawerOpen` 상태에 따라 0 또는 380(서랍 폭)으로 전환
- 이유
  - 파일 탭처럼 서랍에 붙어 이동하는 버튼이 서랍 상태를 직관적으로 보여줌
- 변경 파일: `src/pages/GeneratePage.jsx`

## v1.6.0 히스토리 생성 DNA / 영상 DB 등록

### 36. generations 테이블 컬럼 확장 (생성 DNA + 영상 등록)

- 변경: `generations`에 13개 컬럼 추가
  - 생성 DNA: `negative`, `lora_name`, `lora_strength`, `width`, `height`, `steps`, `cfg`, `sampler`, `scheduler`
  - 영상 등록: `media_type`(기본 `'image'`), `video_path`, `source_image`, `params`(JSON)
- 문제/배경: 히스토리에 긍정/부정/시드 등 생성 DNA를 보여주려면 DB에 값이 있어야 함. 기존엔 prompt/seed/checkpoint만 저장됐고 영상은 DB에 등록되지 않았음
- 결정: 영상용 별도 테이블 없이 `generations`에 `media_type`으로 구분. 마이그레이션은 앱 기동 코드가 아니라 DB Browser에서 직접 쿼리로 적용 (사용자 제안: 코드는 제거하고 쿼리로 진행)
- 이유: 히스토리 목록/필터 로직을 영상 행에도 그대로 재사용 가능. `DEFAULT 'image'`로 기존 행은 영향 없음. 1회성 작업이라 기동 시마다 실행되는 코드가 필요 없음
- 대안: 영상 전용 테이블 신설 → 미채택 (목록 조회/필터/페이지네이션을 두 테이블에서 따로 구현해야 함)
- 검증: `PRAGMA table_info(generations)`로 24개 컬럼 확인. 이미지 3019(1024x1024, steps 40, cfg 5.0, euler_ancestral/sgm_uniform), 영상 3020(`media_type=video`, `video_path`, 1280x720) 저장 확인
- 변경 파일: `data/data.db` (수동 마이그레이션, `core/db.py` 변경 없음)

### 37. 동영상 DB 등록 및 히스토리 영상 노출

- 변경
  - I2V 완료 시 `generations`에 영상 행 등록 (`save_video`, `status='done'`, `checkpoint='I2V'`, `source_image`, `params`에 length/frame_rate/high_steps/low_steps)
  - 히스토리 카드에 `<video>` 플레이어 표시, 영상 행은 업스케일/인페인팅/피드백 편집 버튼 숨김
  - 생성 탭 히스토리 이미지 피커에서 영상 행 제외
- 문제/배경: 영상이 DB에 없어 히스토리에서 볼 수 없었음. 영상 행은 `image_path`가 비어 있어 이미지 전용 UI(피커 썸네일, 업스케일, 인페인팅)가 깨짐
- 결정: 등록은 이번부터 시작하고 이전에 생성한 영상은 등록하지 않음 (사용자 지정). 등록 실패가 영상 생성 결과에 영향을 주지 않도록 `try`로 감쌈
- 이유: 프론트가 완료 이벤트를 받기 전에 DB 등록이 끝나 있어야 히스토리 갱신과 어긋나지 않음
- 미해결: `I2VRequest`에 LoRA 필드가 없어 영상의 LoRA는 적용/저장되지 않음 (I2V LoRA 작업에서 처리, 보류). 영상 seed 기록은 #42에서 해결
- 변경 파일: `core/image/preference.py`, `api/routers/sd.py`, `src/pages/HistoryPage.jsx`, `src/pages/GeneratePage.jsx`

### 38. 히스토리 생성 DNA 출력

- 변경
  - 이미지 생성 시 실제 워크플로우에 들어간 값을 DNA 컬럼에 저장 (`update_generation_meta`: negative, lora, 가로/세로 스왑이 반영된 width/height, KSampler의 steps/cfg/sampler/scheduler)
  - 히스토리 카드에 `GenerationDna` 출력: 시드, 해상도, 스텝, 샘플러/스케줄러, CFG, LoRA, 긍정/부정 프롬프트(칩). 영상 행은 프레임/FPS/High·Low 스텝/소스 이미지 표시
  - `get_all_generations`/`get_generation_by_id`가 새 컬럼을 반환 (`_GEN_COLS`, `_row_to_gen`)
- 문제/배경: 히스토리가 prompt와 모델명만 보여줘서 생성 조건을 재현하거나 재사용할 수 없었음
- 결정: 요청값이 아니라 워크플로우에 최종 주입된 값 기준으로 저장. DNA 도입 이전 행은 해당 줄을 숨기고 부정 프롬프트는 "기록 없음"으로 표시
- 이유: 모델별 설정(`MODEL_RESOLUTION`)과 해상도 가로/세로 랜덤 스왑이 서버에서 결정되므로 요청값으로는 실제 생성 조건을 알 수 없음
- 비고: `preference.py`에 중복 선언돼 있던 `get_all_generations`/`get_generation_by_id`를 하나로 정리. 실제 동작(목록은 category 미부착, 단건은 category 부착)은 유지
- 변경 파일: `core/image/preference.py`, `api/routers/sd.py`, `src/pages/HistoryPage.jsx`

### 39. 히스토리 프롬프트 인용 버튼

- 변경: 긍정/부정 프롬프트 출력 아래에 각각 "프롬프트 인용" 버튼 추가. 긍정은 드롭박스 최종 프롬프트 미리보기에, 부정은 부정 프롬프트 입력창에 적용하고 생성 탭으로 전환
- 문제/배경: 과거 생성의 프롬프트를 재사용하려면 수동으로 복사·재입력해야 했음
- 결정
  - 긍정/부정 모두 기존 값을 인용 값으로 대체 (사용자 결정)
  - 긍정은 쉼표 단위로 보유 태그 리스트와 대조해 있으면 서브카테고리 선택으로, 없으면 수동 태그로 넣고 히스토리의 순서·표기를 그대로 유지. 기존 선택과 랜덤 설정은 초기화
  - 부정은 중복 태그를 제거한 값으로 대체
  - 탭 간 전달은 `App`의 `quote` state → `GeneratePage`의 `pendingQuote` → `DropdownModePanel`이 소비 후 비움
  - 영상 행은 프롬프트가 자연어라 인용 버튼 없음
- 이유: i2i 모드에서 인용하면 `DropdownModePanel`이 새로 마운트되므로, 소비 후 비우지 않으면 모드를 오갈 때마다 이전 인용이 다시 적용됨
- 대안: 현재 값에 추가(append) 방식 → 미채택 (대체 방식으로 확정)
- 변경 파일: `src/App.jsx`, `src/pages/GeneratePage.jsx`, `src/pages/HistoryPage.jsx`, `src/utils/tags.js` (신규, `dedupeTags`)

### 40. 전체 태그 검색 Enter 동작 개선

- 변경: 방향키로 선택하지 않고 Enter를 칠 때, 수동 입력으로 넘기기 전에 보유 태그 리스트에 있는지 먼저 확인. 있으면 해당 서브카테고리 선택으로, 없으면 기존처럼 수동 태그로 처리
- 문제/배경: 이미 보유한 태그를 직접 입력해 Enter를 치면 카테고리에 연결되지 않고 수동(초록) 태그로만 들어가서 카테고리 표시와 선택 상태가 맞지 않았음
- 결정 (사용자 제시 규칙): 쉼표로 여러 개를 입력해도 토큰별로 판정. 영문은 대소문자와 공백/언더스코어를 무시하고, 한글은 정확히 일치할 때 같은 태그로 취급. 단일 선택 서브카테고리는 기존 값을 교체
- 이유: 직접 입력과 드롭박스 선택이 같은 상태(`dropSelections`)로 합쳐져야 카테고리 표시, 제외 규칙, 랜덤 설정과 일관됨
- 비고: 같은 `en`이 여러 서브카테고리에 있으면 `allTagsFlat` 순서상 먼저 나오는 것으로 들어감
- 변경 파일: `src/pages/GeneratePage.jsx`

### 41. 부정 프롬프트 / 모델 prefix 중복 방지

- 변경
  - `/generate`에서 입력한 부정 프롬프트에 `NEGATIVE_BASE`가 이미 들어 있으면 다시 붙이지 않음. 최종 부정 프롬프트는 `_dedupe_tags`로 중복 제거
  - 프롬프트가 이미 모델 prefix로 시작하면 prefix를 다시 붙이지 않음 (`_`→공백, 소문자로 정규화해 비교)
- 문제/배경: 드롭박스 패널이 `negative_base`를 입력창 초기값으로 채우는데 서버가 한 번 더 붙여, 기본 상태에서 DB에 저장된 부정 프롬프트(3019)에 `NEGATIVE_BASE`가 두 번 들어감. 또 DB `prompt`에는 prefix가 포함돼 저장되므로 그대로 인용해 생성하면 prefix가 이중으로 붙게 됨
- 결정: 서버에서 이미 포함돼 있으면 건너뜀. 인용 시점에는 프론트에서도 `dedupeTags`로 중복 제거
- 이유: 히스토리에는 실제 사용된 프롬프트가 그대로 남아야 하고, 프론트는 모델별 prefix를 알지 못함
- 대안: DB에는 prefix를 뺀 프롬프트만 저장 → 미채택 (히스토리에서 실제 사용 프롬프트를 볼 수 없고, `watcher`와 `save_generation_start`에 넘기는 값도 바꿔야 함)
- 검증: 이후 생성분의 DB 부정 프롬프트에 중복이 없음을 확인 (이미 중복 저장된 기존 행은 그대로 남고 인용 시에만 정리됨)
- 변경 파일: `api/routers/sd.py`

## v1.6.1 버그 수정 및 입력 UX

### 42. I2V High/Low 분할 지점 수정 및 영상 seed 기록

- 변경
  - `_high_end = high_end_step or _high_steps` (기존 `I2V_DEFAULTS["high_end_step"]` 고정값 2)
  - Low KSamplerAdvanced의 `noise_seed` 설정 (기존엔 High 쪽에 중복 작성돼 Low에는 설정이 빠져 있었음)
  - `done` 이벤트에 `seed` 포함, `save_video`가 실제 사용된 seed를 저장
- 문제/배경: UI에서 High 스텝을 2가 아닌 값으로 바꾸면 총 스텝은 `high+low`로 바뀌지만 High/Low 경계는 2로 고정돼, 입력한 `high_steps`가 경계에 반영되지 않았음. 영상 seed는 요청값(-1)이 그대로 저장됨
- 결정: 분할 지점의 기본값을 `high_steps`로 하고 `high_end_step`을 별도 지정하면 그것을 우선. `I2V_DEFAULTS`의 `high_end_step`은 미사용
- 이유: 기본값(High 2 / Low 3)에서는 증상이 없어 놓치기 쉬운 불일치였음
- 검증: 코드 반영 확인. High 3 / Low 3의 스텝 범위(0→3, 3→6)와 새 영상의 DB seed 값은 실행 확인 필요
- 변경 파일: `core/video/i2v_generate.py`, `api/routers/sd.py`

### 43. i2v 입력 새로고침 소실 수정 및 프롬프트 초기화(X) 버튼

- 변경
  - `VideoModePanel`의 state를 `loadI2vDraft()` 지연 초기화로 변경하고 마운트 시 복원 effect를 삭제
  - 공용 `ClearableTextarea` 컴포넌트 추가, 프롬프트 텍스트박스 5곳(i2v 긍정/부정, i2i 긍정/부정, 드롭박스 부정)에 초기화(X) 버튼 적용
- 문제/배경: 새로고침하면 i2v의 선택 이미지는 남지만 프롬프트가 사라짐. 추정 원인은 `StrictMode`의 effect 이중 실행임: 복원 effect가 읽은 뒤 저장 effect가 초기값으로 `i2vDraft`를 덮어쓰고, 두 번째 복원 effect가 빈 draft를 읽어 프롬프트를 비움 (이미지는 첫 복원에서 이미 세팅돼 유지됨)
- 결정: 복원 effect를 쓰지 않고 `useState` 초기값에서 직접 읽도록 변경(드롭박스 모드와 같은 패턴). X 버튼은 사용자 제안 — 모든 칸에서 빈 값으로 초기화
- 이유: 지연 초기화는 첫 렌더부터 복원값이 들어가서 저장 effect가 같은 값을 다시 쓰므로 StrictMode 이중 실행에 안전. 드롭박스 부정 프롬프트를 비워도 서버가 `NEGATIVE_BASE`를 붙임
- 검증: 새로고침 후 프롬프트 유지 확인 (사용자)
- 변경 파일: `src/pages/GeneratePage.jsx`

### 44. 프로그레스 바 "완료!" 고착 수정 및 `useSSE.reset`

- 변경: 이미지 생성(SSE) 시작 시 영상 job 상태(`jobProgress`/`jobStatus`/`jobError`)를 초기화하는 `run` 래퍼 추가. `useSSE`에 `reset` 노출, 영상 시작(`attachJob`) 시 호출
- 문제/배경: 영상 job이 끝나면 `jobProgress`가 1로 남아, 표시 조건(`jobRunning || jobProgress > 0`) 때문에 이후 이미지 생성의 진행률 대신 영상의 "완료!"가 계속 표시됨
- 결정: 표시 소스를 바꾸지 않고 시작 시점에 이전 상태를 초기화
- 이유: 프로그레스 바가 완료! 상태로 고정 되어 있어 이후 생성되는 작업에 대한 진행도를 알 수 없었음.
- 비고: 이후 생성 큐 도입(#51)으로 job state와 SSE 표시 경로는 사용하지 않게 됨 (진행률은 큐 항목 기준)
- 변경 파일: `src/hooks/useSSE.js`, `src/pages/GeneratePage.jsx`

### 45. LLM 잔재 정리

- 변경: `/api/system/switch`의 `llm_model` 기본값을 옛 모델명 `qwen3:14b`에서 서버의 `DEFAULT_MODEL`로 변경, `systemApi.switch`는 모델 미지정 시 서버 기본값 사용. 미사용 `/api/llm/chat`(비스트리밍) 삭제(선택 적용)
- 문제/배경: 전환 API가 설치돼 있지 않은 옛 모델을 로드/언로드하려다 조용히 실패할 수 있었음. `/chat`은 `stream: True`로 요청하면서 응답은 `resp.json()`으로 읽어 동작하지 않는 상태였음
- 결정: 기본 모델을 한 곳(`DEFAULT_MODEL`)에서 가져옴
- 이유: 모델명을 바꿀 때 여러 파일을 고치지 않도록
- 변경 파일: `api/routers/system.py`, `src/api/client.js`, `api/routers/llm.py`

### 46. i2i 입력 해상도 가드

- 변경: i2i/i2i-mask 입력 이미지가 모델 기준 해상도(`MODEL_RESOLUTION`의 가로×세로 픽셀 수)의 1.15배를 넘을 때만 원본 비율을 유지하며 다운스케일 (LANCZOS, 가로·세로 8의 배수). 결과는 ComfyUI input 폴더에 `*_fit.png`로 저장하고 원본은 건드리지 않음. 마스크 모드는 마스크도 같은 크기로 리사이즈한 뒤 페더링. 축소 시 진행률에 안내 문구 표시
- 문제/배경: i2i 결과물이 입력 이미지 크기를 그대로 유지해 큰 이미지에서 VRAM/품질이 불안정했음
- 결정 (사용자): 원본 비율을 유지한 다운스케일, 픽셀 뭉침 등 품질 열화가 최대한 없는 방향
- 이유: 뭉침은 확대·nearest 방식에서 생기므로 축소만 하고 LANCZOS를 사용. 기준 이하/근소 초과 이미지는 재샘플링을 하지 않음
- 대안: 모델 기본 해상도로 맞추거나(확대 포함) 상한만 두는 방식 → 미채택
- 검증: `*_fit.png` 생성과 1024 축소 확인 (사용자). 마스크 모드는 미확인
- 변경 파일: `core/image/generate.py`

### 47. 히스토리 영상 보기/숨기기 토글 및 모델 적용 버튼

- 변경
  - 이미지 보기/숨기기와 별개로 영상 보기/숨기기 토글(`showVideos`) 추가. 이미지 행은 이미지 토글에, 영상 행은 영상 토글에만 반응
  - 히스토리 카드의 모델 표시 옆에 "모델 적용" 버튼 추가. 해당 체크포인트를 생성 탭에 적용(목록에 없으면 안내)
- 문제/배경: `showImages` 하나가 영상 행의 플레이어까지 같이 제어했음. 인용 기능은 프롬프트만 가져오고 모델은 가져오지 못했음
- 결정: 영상 토글은 사용자 지정(이미지 토글과 별개 동작). 모델 적용은 사용자 제안이며, 긍정 프롬프트 인용에 자동으로 묶지 않고 별도 버튼으로 둠
- 이유: 프롬프트만 가져오려다 모델이 바뀌는 일을 막기 위해
- 대안: 긍정 프롬프트 인용 시 체크포인트도 같이 적용 → 미채택 (한 줄 변경으로 전환 가능)
- 변경 파일: `src/pages/HistoryPage.jsx`, `src/pages/GeneratePage.jsx`

### 48. 생성 뷰포트 전 영역 확장 및 태그 패널 토글 개편

- 변경
  - 이미지/영상 표시 영역을 중앙 패널 전체로 확장, 진행률/에러/메타는 하단 오버레이로 변경(이미지 드래그를 막지 않도록 `pointerEvents` 분리)
  - 오른쪽 태그 패널의 열기/닫기 버튼을 패널 밖 파일탭 버튼으로 분리, 닫으면 패널이 완전히 사라지고 탭만 남음(태그가 없으면 버튼도 숨김). 패널 폭/뷰포트 여백/탭 위치를 `TAG_PANEL_W` 하나로 통일
  - 전체 태그 검색 입력과 최종 프롬프트 미리보기 사이 간격 수정(입력은 래퍼 밖에 두고 드롭다운 래퍼를 높이 0 + `marginTop: -6`)
- 문제/배경: 이미지 표시가 뷰포트 일부로 제한돼 확대 후 이미지를 어디로 드래그해도 볼 수 없었음. 태그 패널은 닫아도 40px 띠가 남았고 열기/닫기 버튼이 패널 안에 있었음
- 결정: 두 항목 모두 사용자 제안 (태그 패널은 왼쪽 옵션 서랍과 같은 방식). 태그 패널은 언마운트를 피하려고 `display` 토글 사용
- 이유: 왼쪽 서랍과 같은 상호작용으로 통일. 간격은 빈 flex 항목에도 `gap`이 적용되는 구조 때문이라 높이 0 래퍼로 상쇄
- 검증: 동작 확인 (사용자)
- 변경 파일: `src/pages/GeneratePage.jsx`

### 49. 드롭박스 최종 프롬프트 초기화 버튼

- 변경: 최종 프롬프트 미리보기의 복사 버튼 옆에 초기화 버튼 추가. 드롭박스 선택, 랜덤 설정/고정값, 수동 입력 태그를 모두 비움 (부정 프롬프트와 LoRA는 유지)
- 문제/배경: 드롭박스 긍정 프롬프트는 텍스트박스가 아니라 칩이라 #43의 X 버튼 대상이 아니었음
- 결정: 사용자 제안. 확인창은 넣지 않음, 미리보기가 비어 있으면 비활성화
- 변경 파일: `src/pages/GeneratePage.jsx`

## v1.7.0 생성 큐

### 50. 생성 큐 백엔드 (대기열, 워커, 취소)

- 변경
  - 신규 `core/system/gen_queue.py`: 서버 메모리 큐 + 워커 스레드. 선입 순 순차 처리, 항목 상태(waiting/running/done/error), 대기 항목 제거, 실행 중 항목 중단(ComfyUI `/interrupt`), 전체 취소, 완료·실패 항목 최근 10개 보관
  - `sd.py`: t2i 생성 로직을 `_t2i_events` 제너레이터로 분리(기존 `/generate` SSE는 그 위에 유지). 큐 러너(`t2i`/`i2i`/`i2v`) 등록, `POST /queue/t2i|i2i|i2v`, `GET /queue`, `DELETE /queue/{id}`, `DELETE /queue`
  - `generate.py`의 `_ws_progress`가 `execution_interrupted`(취소)와 `execution_error`(오류)를 처리
  - 취소/실패한 t2i는 선발급한 DB 행을 `failed`로 정리
- 문제/배경: 생성 버튼을 누르면 곧바로 ComfyUI에 제출돼, 연속으로 요청하면 화면이 마지막 항목만 따라가고 순서/취소를 제어할 수 없었음. 기존 job(`jobs.py`)은 실행 중인 작업 하나의 상태를 기록하고 새로고침 후 재연결하는 장부일 뿐 대기열이 아님
- 결정 (사용자)
  - 이미지/영상 구분 없이 선입 순으로 하나의 큐에 쌓아 순차 처리
  - 대상이 바뀌면 모델 교체가 필요하지만 ComfyUI가 이전 모델을 알아서 정리하므로 별도로 신경 쓰지 않음
  - 대기 항목은 삭제하면 큐에서 지우고 빈 자리는 트림
  - 완료 항목은 최근 10개만 표시(나중에 조정)
- 결정 (설계): 큐와 워커는 서버가 소유하고 앱이 한 번에 하나씩 ComfyUI에 제출. 프론트는 폴링으로 상태를 구독
- 이유: 한 번에 하나만 제출하므로 `/interrupt`가 엉뚱한 작업을 끊지 않고, 브라우저를 새로고침/종료해도 큐가 계속 처리됨. 큐에서 하나라도 응답이 없으면 뒤 항목이 모두 막히므로 `execution_error` 처리를 같이 넣음
- 대안
  - ComfyUI 네이티브 큐에 한꺼번에 제출 → 미채택 (취소·순서 변경·제어가 어려움)
  - 완료 항목을 DB에서 다시 불러오기 → 미채택 (i2i 결과는 DB에 등록되지 않음)
  - 생성 버튼을 취소 버튼으로 전환 → 미채택 ("추가"와 "취소"가 충돌, 항목별 ✕ 취소로 대체)
- 한계/미해결
  - 서버를 재시작하면 대기/진행 중 항목과 완료 카드가 사라짐
  - `ws.recv()`에 타임아웃이 없어 ComfyUI가 멈추면 해당 항목이 큐를 잡고 있음
  - 기존 `/api/sd/i2v`(job 방식)와 `/jobs/*`는 사용하지 않지만 롤백용으로 유지
- 변경 파일: `core/system/gen_queue.py`(신규), `api/routers/sd.py`, `core/image/generate.py`

### 51. 생성 큐 프론트 (상단 대기열 패널)

- 변경
  - 신규 `src/components/QueueStrip.jsx`: 화면 상단 메뉴 아래의 열고 닫는 패널. 대기/생성 중/완료/실패를 시간 순 한 리스트로 표시 (대기 #순번, 진행률 바, 실패 표시). i2i/i2v는 베이스 이미지 썸네일, t2i 대기 항목은 프롬프트 앞부분 텍스트 카드, 마우스를 올리면 요청 스냅샷 툴팁
  - 각 카드 ✕: 대기는 제거, 실행 중은 중단, 완료·실패는 목록에서 제거. "전체 취소" 제공
  - `GeneratePage.jsx`: 서버 큐 폴링, 생성 버튼은 큐에 추가(t2i/i2i/i2v 모두), 완료 카드 클릭 시 뷰포트와 태그 패널이 해당 항목 정보를 표시(t2i는 DB에서 태그 로드). 보던 항목이 최신일 때만 새로 완료된 항목을 자동 표시
- 문제/배경: 큐 항목이 어떤 요청인지, 쌓인 결과를 어떻게 다시 볼지 정해야 했음
- 결정: 대기열과 완료 결과를 한 리스트에 담음(요청 사용자 질문에 대한 설계 제안 채택). 선택된 항목이 피드백 대상. 새로고침 후에도 서버 큐를 다시 불러와 진행률 카드가 이어짐(영상 job 재연결을 대체)
- 이유: 두 리스트로 나누면 항목이 대기에서 완료로 넘어갈 때 위치가 바뀌고 확인 장소가 둘로 늘어남. 순번은 저장하지 않고 화면에서 계산해 중간 삭제 시 번호가 자동으로 당겨짐
- 비고: 썸네일은 원본 이미지를 축소 표시 (느리면 서버 썸네일 도입). i2i/i2v 결과는 태그 패널과 피드백이 없음
- 검증 (사용자): 이미지 큐 적재, 영상을 중간에 넣었을 때의 적재 정상. 영상 생성 중 뒤에 쌓인 이미지 큐의 순차 실행은 확인 필요
- 변경 파일: `src/components/QueueStrip.jsx`(신규), `src/pages/GeneratePage.jsx`, `src/api/client.js`

### 52. 대기열 UI 개선 (접기 탭, 생성 중 카드 클릭, 이미지 중앙 정렬)

- 변경
  - 대기열 패널 하단 중앙에 100x30 접기/펼치기 탭 추가 (닫으면 패널이 완전히 사라지고 탭만 남음, 진행·대기 개수 표시)
  - 큐의 생성 중 카드를 클릭하면 뷰포트와 태그 패널을 비우고 화면 중앙에 진행률(바, 퍼센트, 상태)을 표시. 그 항목이 끝나면 결과가 자동으로 뜸
  - `ImageViewer`: 이미지 로드 시와 더블클릭 리셋 시 이미지를 컨테이너 중앙에 배치 (`getCenterOffset`), 세로가 넘치지 않도록 `maxHeight: 100%`
- 문제/배경: 대기열 카드를 클릭하면 이미지가 컨테이너 왼쪽 위(x=0)에 붙어서 표시됐음(`display: block` + `translate(offset)`만 사용)
- 결정: 세 항목 모두 사용자 제안. 이미지 위치는 뷰포트 전체의 중앙 기준이며 왼쪽 서랍에 가려지는 부분은 드래그로 조절(사용자 결정)
- 비고: `ImageViewer`는 히스토리 카드에서도 쓰이므로 히스토리 이미지도 같은 방식으로 중앙에 맞춰짐
- 검증: 미확인
- 변경 파일: `src/components/QueueStrip.jsx`, `src/components/ImageViewer.jsx`, `src/pages/GeneratePage.jsx`

### 53. 대기열 완료 시 PC 종료

- 변경: 전체 취소 옆에 "완료 시 PC 종료" 토글 추가. 켜 두면 서버가 대기·진행 중 항목이 모두 끝났을 때 `shutdown /s /t 60`으로 종료를 예약하고, 화면에 카운트다운과 "종료 취소" 버튼을 표시. 서버: `set_shutdown`/`shutdown_state`/`abort_shutdown`, `POST /queue/shutdown`, `POST /queue/shutdown/abort`
- 문제/배경: 큐에 작업을 걸어 두고 자리를 비울 때 PC를 직접 끄지 않아도 되게 하려는 요구
- 결정: 사용자 제안. 종료 판단은 서버가 하고(브라우저를 닫아도 동작), 60초 유예 + 취소 버튼을 둠. 켤 때 확인창 표시. "전체 취소" 또는 실행 중 항목의 직접 취소 시 예약을 자동 해제. 실패한 항목이 있어도 모두 끝나면 종료
- 이유: 되돌릴 수 없는 동작이라 유예와 취소 수단이 필요하고, 직접 취소한 뒤에 PC가 꺼지는 일을 막기 위함
- 한계: 꺼지는 PC는 백엔드가 실행 중인 PC. Windows 전용. 서버를 수동 종료하면 이미 걸린 Windows 종료 예약은 남으므로 `shutdown /a`로 취소
- 검증: 미확인 (종료 취소까지 테스트 필요)
- 변경 파일: `core/system/gen_queue.py`, `api/routers/sd.py`, `src/api/client.js`, `src/components/QueueStrip.jsx`, `src/pages/GeneratePage.jsx`


## v1.8.0

### 54. 이미지 탭 신설 + 뷰포트 생성 버튼
- 변경: 옵션 서랍 상단을 `🖼️ 이미지 / 🎬 영상` 탭으로 나누고 이미지 탭 아래에 `t2i / i2i` 서브 토글을 배치. `DropdownModePanel`을 `T2iModePanel`로 명칭 변경(localStorage 키는 유지). 패널별 생성 버튼을 없애고 뷰포트 하단 생성 버튼 하나로 통합(탭에 따라 이미지/영상 라벨)
- 문제/배경: 생성 큐 도입으로 패널의 `generate()`가 payload 생성 + `onEnqueue` 호출로 단순해져 핸들러를 상위로 올리기 쉬워짐
- 결정: 패널이 매 렌더마다 `bindGenerate(handler, enabled)`로 현재 핸들러와 활성 여부를 올리고, 뷰포트 버튼이 ref로 호출. 이미지 탭으로 돌아오면 마지막 서브 모드 복원
- 이유: 확인 필요
- 변경 파일: GeneratePage.jsx

### 55. 생성 버튼·프로그레스 한 줄 배치 (사용자 제안)
- 변경: 뷰포트 하단 첫 줄을 왼쪽 프로그레스 70 : 오른쪽 생성 버튼 30으로 배치. 프로그레스는 진행 항목 선택 여부와 무관하게 항상 표시(진행 없으면 "대기 중")
- 결정: 중앙의 큰 프로그레스와 하단 프로그레스가 동시에 표시되는 중복은 허용
- 이유: 확인 필요
- 변경 파일: GeneratePage.jsx

### 56. DNA 서랍 토글 + 뷰포트 하단 패딩 동적화 (사용자 제안)
- 변경: 대기열 토글과 같은 형태의 하단 탭 버튼으로 생성물 DNA(메타) 박스를 열고 닫음. 박스는 화면 아래 바깥에서 올라오고 내려가는 슬라이드. 이미지 영역 하단 패딩은 하단 오버레이 높이를 ResizeObserver로 측정해 동적으로 계산(고정 130/230px 제거). `dnaOpen`은 localStorage 저장. `ImageViewer`는 컨테이너 크기 변경 시 중앙으로 재정렬(사용자가 줌/패닝한 뒤에는 유지)
- 문제/배경: 고정 패딩으로는 에러 박스 등장·DNA 박스 높이 변화에 대응 불가. 컨테이너 크기가 바뀌어도 `ImageViewer`가 로드 시점에만 중앙 오프셋을 계산해 이미지가 어긋남
- 이유: 확인 필요
- 변경 파일: GeneratePage.jsx, ImageViewer.jsx

### 57. localStorage 저장 훅 정리 + 체크포인트 저장 (사용자 제안)
- 변경: `useState` + 저장 `useEffect` 쌍을 `usePersistentState` 훅으로 통합(`dropSelections`, `dropRandom`, `dropRandomFixed`, `promptOrder`는 기존 키 유지). 체크포인트도 저장. 저장된 체크포인트가 목록에서 사라졌으면 기본값으로 복귀
- 이유: 확인 필요
- 변경 파일: hooks/usePersistentState.js(신규), GeneratePage.jsx

### 58. 좌/우 패널 슬라이드 + 패널 크기 조정 (사용자 제안)
- 변경: 옵션 서랍과 태그 패널도 DNA 서랍과 같은 슬라이드 애니메이션(언마운트 없이 transform + visibility). 옵션 서랍 너비·태그 패널 너비·대기열 카드 크기를 드래그로 조정, 더블클릭으로 기본값 복귀, 모두 localStorage 저장. 드래그 중에는 전환 애니메이션 비활성
- 결정: 대기열은 패널 높이 드래그가 썸네일 카드 크기를 바꾸는 방식으로 해석(카드가 고정 88px 가로 스크롤 구조)
- 이유: 확인 필요
- 변경 파일: GeneratePage.jsx, QueueStrip.jsx, hooks/useDragResize.js(신규), components/ResizeHandle.jsx(신규)

### 59. GeneratePage 잔여 정리
- 변경: 미사용 코드 제거(`useSSE`·`run`·`displayRunning`, `job*` state, 주석 처리된 `attachJob`/`startI2v`/`reattach`, `buildFuse`), 미사용 props 제거(`T2iModePanel`의 `result·setResult·setMeta·tags·setTags·usedPrompt·setUsedPrompt·onGenerated·setTagPanelOpen·koMap`, `I2iModePanel`의 `setResult·setMeta`), `SortableTag`를 모듈 레벨로 이동, i2i의 항상 통과하던 `fromHistory` 분기와 낡은 "업로드 엔드포인트 미구현" 알림 제거
- 문제/배경: `run` 안의 `sseReset()`는 정의되지 않은 참조. `SortableTag`가 컴포넌트 안에 정의되어 렌더마다 새 컴포넌트 타입이 생김
- 결정: 동작 변경 없는 정리만 수행. i2i `레퍼런스` 슬롯(전송되지 않는 빈 UI)은 보류
- 이유: 확인 필요
- 변경 파일: GeneratePage.jsx

### 60. 히스토리 이미지/영상 종류 필터 (사용자 결정)
- 변경: `전체 / 이미지 / 영상` 필터를 툴바 버튼과 필터 패널에 모두 두고 `mediaType` state를 공유. 기존 `이미지/영상 보기·숨기기` 버튼은 카드를 유지한 채 미디어 표시만 끄는 별개 기능으로 유지
- 결정: 별도 버튼과 필터 패널 통합 중 하나를 고르지 않고 둘 다 제공
- 이유: 확인 필요
- 변경 파일: HistoryPage.jsx

### 61. ComfyUI 웹소켓 무응답 처리
- 변경: `_ws_progress`에 `settimeout(30)`. 타임아웃 시 `is_comfy_alive()`로 생존 확인 후 죽었으면 실패 처리, 살아 있으면 계속 대기하되 무이벤트가 30분을 넘으면 `/interrupt` 후 실패 처리. 이벤트(바이너리 미리보기 포함)가 오면 타이머 갱신
- 문제/배경: `ws.recv()`가 타임아웃 없이 블로킹되어 ComfyUI가 멈추면 단일 워커가 해당 항목에서 영구 대기하고 이후 큐가 전부 막힘
- 결정: 상한값(30분)이 적정한지는 사용자 확인 대기. 상한은 총 생성 시간이 아니라 한 노드 안에서 이벤트 없이 걸리는 가장 긴 구간(모델 로딩, 샘플러 1스텝, VAE 디코드) 기준
- 대안: 단순 `settimeout(60)` — 모델 로딩 등 정상 무이벤트 구간에서 오탐하므로 미채택
- 이유: 큐 정지 방지(위 배경). 상한값 근거는 확인 필요
- 변경 파일: generate.py

### 62. LLM 전송 실패 시 입력 유지 + 중단/전송 버튼 통합 (사용자 제안)
- 변경: 입력란과 첨부를 전송 시점에 비우지 않고 첫 토큰 수신 시 비움. 전송 중 입력란은 읽기 전용, 첨부 관련 버튼 비활성. 토큰 전에 실패/중단하면 낙관적으로 추가한 메시지 2개를 제거하고 입력/첨부 유지. 스크롤 영역 아래의 중단/전송 버튼을 삭제하고 입력란 옆 버튼 하나로 통합(전송 중에는 중단)
- 문제/배경: 실패해도 입력이 비워져 메시지와 첨부가 사라짐. Ollama 호출 실패는 HTTP 200 안의 SSE `error` 이벤트로 오므로 응답 상태로 성공 판정 불가. 서버는 토큰이 있을 때만 저장
- 결정: 성공 기준을 첫 토큰 수신으로 지정. 토큰이 일부 온 뒤 실패하면 서버에 저장되므로 부분 답변을 남김
- 대안: 입력란은 즉시 비우고 실패 시 복원하는 방식 — 전송 중 사용자가 새로 입력한 내용과 충돌해 미채택
- 이유: 사용자 제안(성공 응답 후 초기화로 고쳐도 되며 전송 중 입력 수정 불가)
- 변경 파일: LLMPage.jsx

### 63. 히스토리 "폴더에서 열기" (사용자 제안)
- 변경: 히스토리 카드(이미지·영상)에 `📂 폴더에서 열기` 버튼. `POST /api/system/reveal`이 탐색기를 파일 선택 상태로 실행
- 결정: ComfyUI 폴더 하위 경로만 허용, 파일이 없으면 404. 탐색기는 서버 PC에서 열리므로 외부 접속에서는 의미 없음. 이미지는 원본 파일 기준(업스케일 파일 전용 버튼 없음)
- 이유: 확인 필요
- 변경 파일: system.py, client.js, HistoryPage.jsx

## v1.8.1

### 64. 생성 탭 태그 패널 내용 누락 버그 수정
- 변경: 생성 탭에서 각 패널들에 이지 애니메이션 코드 적용 중 태그 패널 데이터 삭제
- 결정: 태그 내용 누락 버그 수정
- 이유: 핵심 기능인 태그 기반 피드백이 불가능 해져서 수정 결정.
- 변경 파일: GeneratePage.jsx

### 65. 코드 점검 수정 묶음
- 변경: LLM 라우터 등록(`main.py`), I2I 패널 렌더링 조건을 `'I2I'`로 일치, 오른쪽 태그 패널 토글 버튼 중복 블록 삭제, `useSSE.js`의 도달 불가 `return` 삭제, 히스토리 피드백 편집 오버레이를 선택한 카드에서만 렌더링, `sd.py` 중복 import·미사용 변수 정리
- 문제/배경: 업로드된 코드 점검에서 확인된 문제들(실행 재현 여부는 별도 확인하지 않음). `llm as llm_router`는 import만 있고 `include_router`가 없었음. I2I 상태값 `'I2I'`와 렌더링 조건 `'i2i'`가 불일치. 첫 번째 토글 버튼이 정의되지 않은 `TAG_PANEL_W`를 참조. 오버레이가 `pageGens.map` 안에서 `editTarget`만으로 렌더링되어 모든 카드에 생성됨
- 결정: 위 항목 수정. I2V LoRA(서버 `I2VRequest`가 `lora_name`/`lora_strength`를 버리는 문제)는 구현 범위가 커서 보류
- 이유: 코드 점검에서 확인된 오류를 우선 처리
- 변경 파일: main.py, GeneratePage.jsx, useSSE.js, HistoryPage.jsx, sd.py

## v1.9.0

### 66. 대기열 드래그 순서 변경
- 변경: 대기 중 항목만 드래그로 순서 변경. `gen_queue.reorder`, `POST /api/sd/queue/reorder`, `QueueStrip`에 dnd-kit 적용, 화면에 먼저 반영한 뒤 서버와 동기화
- 결정: 실행 중·완료 항목의 위치는 유지하고, 대기 항목이 차지한 자리에만 새 순서를 채움
- 이유: (미기재)
- 변경 파일: gen_queue.py, sd.py, client.js, QueueStrip.jsx, GeneratePage.jsx

### 67. 대기 중 항목 클릭 시 뷰포트에 `대기 #n` 표시
- 변경: 대기 카드를 클릭할 수 있게 하고 뷰포트 중앙에 `[kind] 대기 #n` 표시. 순서가 바뀌면 번호 갱신, 시작되면 진행률 표시로 전환, 완료되면 결과 자동 표시
- 이유: (미기재)
- 변경 파일: QueueStrip.jsx, GeneratePage.jsx

### 68. LLM 인용 참조
- 변경:
  - 입력창·첨부 버튼 위에 옅은 회색 인용 필드(인용 칩, 개별 삭제). 인용이 있을 때만 표시
  - 텍스트를 드래그한 뒤 우클릭하면 선택 부분을 인용, 말풍선 이미지를 우클릭하면 이미지 인용. 말풍선 아래 `💬 인용`/`🖼️ 이미지 인용` 버튼은 전체 인용용
  - 서버 `ChatRequest.quotes`와 `_build_ollama_messages`로 통합. 인용이 없으면 전체 텍스트 대화를 전송(과거 이미지는 보내지 않음). 인용이 있으면 이전 대화는 보내지 않고 인용 내용만 `[인용]`/`[메시지]` 블록으로 새 메시지에 붙여 전송. 이미지는 인용 → 직접 첨부 순으로 `images`에 담고 개수를 텍스트로 안내. "인용은 참고 자료이며 답변 대상은 [메시지]"라는 지시문 추가
  - 원문 `content`와 `quotes`(JSON)를 분리 저장. `chat_messages`에 `image_path`/`quotes` 컬럼 마이그레이션(없을 때만 추가)
  - `이전 이미지 참조` 체크박스·`max` 입력과 `use_history_images`/`max_history_images` 제거
  - 부수 수정: `/api/llm/chat`이 `stream: True`로 요청하고 `resp.json()`을 호출하던 문제를 `stream: False`로 수정
- 문제/배경: 기존 참조는 최근 N장 이미지 자동 첨부(`use_history_images`) + 텍스트 전체 전송 방식이었음
- 결정: 인용 방식(사용자 방안). 기본값은 인용이 없으면 전체 대화. 이미지는 첨부와 인용을 동일하게 취급
- 이유: 질문에 원하는 내용을 포함해야 정확한 답변이 나오고, 지정한 내용이 시각적으로 보여야 하므로 입력창 위에 표기. 말풍선 전체가 아니라 필요한 부분만 지정해서 인용
- 대안: 메시지 단위 선택(서버에서 id로 필터링), 텍스트 조각을 별도 참조 목록으로 두는 방식, 기본값을 "선택한 것만"으로 하는 방식, 이미지 상시 참조 체크박스 유지
- 후속: 긴 인용 내용을 T2I 드롭박스처럼 접었다 펼칠 수 있게 처리 필요(미구현)
- 변경 파일: llm_db.py, llm.py, client.js, LLMPage.jsx

### 69. 인용 텍스트를 T2I/I2I/I2V 프롬프트로 보내기
- 변경: LLM 텍스트 선택 우클릭 메뉴에서 T2I·I2I·I2V의 긍정/부정 프롬프트로 전송(6개 대상). 전송 시 기존 값 뒤에 추가. T2I·I2I는 쉼표 구분 태그로 정규화(줄바꿈 → 쉼표, 중복 제거), I2V는 줄바꿈으로 이어 붙임. T2I 긍정은 기존 태그 선택 상태·순서를 유지하고, 보유 태그는 해당 칸에 선택하며 나머지는 수동 태그로 추가. 개발 모드의 effect 이중 실행에 의한 중복 삽입은 `nonce`로 방지. 적용 알림 토스트. 히스토리의 `📥 프롬프트 인용` 버튼은 기존대로 대체 방식 유지
- 문제/배경: 초기 구현은 기존 값 대체. 테스트에서 I2V만 동작하고 T2I·I2I는 동작하지 않았는데, `LLMPage.jsx`에 `toTagLine` import가 없어 `ReferenceError`가 났기 때문(I2V는 `toTagLine`을 거치지 않음). import 추가로 해결
- 결정: 기존 값 뒤에 추가 (사용자 요청)
- 이유: 기존 내용을 지워도 되지만 특정 내용만 프롬프트에 더하고 싶을 때가 있어 사용자 선택권을 존중. 초기화는 각 입력란의 X 버튼(T2I 긍정은 `🗑️ 초기화` 버튼)으로 간편해 조작 깊이가 낮음
- 대안: 기존 값 대체(초기 구현 후 변경)
- 변경 파일: tags.js, App.jsx, GeneratePage.jsx, LLMPage.jsx

### 70. LLM 메모리 확인 화면(수정·검토 완료)
- 변경: LLM 탭에서 🧠 버튼으로 메모리 화면 전환(채팅 영역은 `display`로만 숨겨 상태 유지). 카테고리 필터, 미검토만 보기(기본 켜짐). 카드별 검토 완료, 수정(카테고리·타입·내용·키워드, 저장 시 검토 완료 처리), 삭제. `update_memory`, `PATCH /api/llm/memories/{id}` 추가
- 결정: 수정과 검토 완료를 PATCH 하나로 처리
- 이유: (미기재)
- 변경 파일: llm_memory.py, llm.py, client.js, MemoryPanel.jsx(신규), LLMPage.jsx

### 71. ComfyUI 유휴 시 모델 자동 언로드
- 변경: 30초마다 ComfyUI `/queue`를 확인해 실행·대기 작업 없이 5분이 지나면 `/free`로 모델 언로드(프로세스 유지). 작업 제출 시(`_post_workflow`) 로드 상태로 표시해 모든 생성 경로를 포함. 언로드 완료 시 이벤트로 추출 워커를 깨움
- 문제/배경: SD와 LLM이 VRAM·RAM을 함께 점유하면 OOM 우려
- 결정: 유휴 판정은 `gen_queue` 자체 추적이 아니라 ComfyUI `/queue` 폴링
- 이유: 생성 모델의 VRAM·RAM 점유가 커서 LLM까지 올리면 OOM이 날 것이므로 SD/LLM을 서로 언로드하며 자원을 분배. 배포는 계획하지 않고 사용자 사양 기준. (코드 근거) 업스케일·인페인팅·직접 생성은 `gen_queue`를 거치지 않아 자체 추적으로는 누락됨
- 대안: `gen_queue` 자체 추적(마지막 작업 종료 시각 + 언로드 플래그)
- 변경 파일: comfy_idle.py(신규), generate.py, main.py

### 72. LLM 메모리 추출 스케줄러
- 변경:
  - `memory_worker`: 30초 주기 + 언로드 신호로 깨어나, ComfyUI 언로드 상태 + 전체 세션의 마지막 대화 후 5분 경과 + 미추출 존재(`extracted_until` 기준)일 때 묶음 단위로 추출. 묶음마다 조건 재확인, 채팅 중에는 시작·진행하지 않음, 실패 시 10분 백오프
  - 추출 묶음 진행 중에 생성 항목이 시작하려 하면 현재 묶음이 끝날 때까지 지연하고 `LLM 메모리 추출 중` 문구 표시, Ollama 언로드 후 시작
  - 종료 예약 시: 큐 완료 → 즉시 언로드(5분 대기 생략) → 최대 10묶음 추출 → PC 종료 예약. 추출 중 `(n/10)` 표시와 종료 취소, 새 작업이 들어오면 종료 예약 재무장
  - 채팅 활동 추적, `GET /api/llm/memory-status`
- 결정(사용자 방안): 추출을 대기열로 순차 처리하고 ComfyUI 모델이 언로드된 상태에서만 진행. 추출 중 생성 요청은 즉시 정지하지 않고 시작을 지연한 뒤 안내 표시. 지연 범위는 현재 묶음까지이며 이때 상한을 초기화. 진행 위치는 별도 대기열 저장 없이 `extracted_until`로 확인
- 이유:
  - 지연: 추출이 영상·이미지 생성보다 빨리 끝날 것이라 예상(미검증 가정). 작업을 취소하고 해당 쌍을 다시 처리하는 건 이미 한 과정을 반복하는 낭비
  - 상한 초기화: 생성 요청이 왔다는 건 PC를 사용 중이라는 뜻이므로 상한을 초기화하고, 작업이 없을 때 다시 상한만큼 시작
  - 종료 시 10묶음 상한: 전기세. PC 사용 시간이 긴 편이라 추출 대상이 쌓이면 사용 시점과 정리 시점이 어긋나므로 일정량을 처리하며 간극을 맞추고, 너무 오래 켜 두면 PC를 켜 둔 채 자는 것과 다르지 않음
  - 자원: #71 참조
- 대안: 지연 범위를 회차 상한까지 전체로 하는 방식, 상한 단위를 저장 메모리 개수로 하는 방식. (사용자 검토 후 배제) 추출 취소 후 해당 쌍 재처리
- 변경 파일: memory_worker.py(신규), gen_queue.py, llm.py, main.py, QueueStrip.jsx, GeneratePage.jsx

### 73. ws 무응답 상한 확정
- 변경: 코드 변경 없음. `WS_POLL_SEC = 30`, `WS_MAX_IDLE_SEC = 1800` 유지
- 결정: 현재 값 확정
- 이유: ComfyUI progress 이벤트도 수신 메시지로 유휴 타이머(`last_msg`)를 갱신하므로 작업이 살아 있는 동안은 상한에 걸리지 않음. 영상은 이벤트 간격이 길지만 1800초면 충분히 안정적인 수치
- 변경 파일: 없음

### 74. 업스케일·인페인팅·i2i 생성 큐 편입 (Plan)
- 변경(계획): 현재 직접 호출하는 업스케일, 인페인팅, i2i 경로를 `gen_queue`에 담도록 변경
- 문제/배경: 직접 호출 경로는 `gen_queue`를 거치지 않아 대기열에 표시되지 않음. 그래서 지금 어디서 무엇을 작업 중인지, 그리고 대기열이 모두 끝난 뒤에 실행되는지 현재 실행 중인 항목 직후에 실행되는지를 화면에서 정확히 알 수 없음. 우선 처리하고 싶은 작업(예: 인페인팅)이 있어도 드래그로 순서를 바꿀 수 없음. 코드상으로는 `gen_queue`가 실행 중인 항목만 ComfyUI에 제출하므로 직접 호출 작업은 현재 항목 직후, 대기 항목보다 먼저 실행될 것으로 보이나 실측은 하지 않음. 또한 직접 호출 경로에는 추출 지연 게이트가 적용되지 않고, `_maybe_shutdown`이 큐 항목만 확인하므로 직접 호출 작업 중에도 종료 예약이 발동할 수 있음
- 결정: 큐에 편입하고 드래그 순서 변경 기능을 함께 활용
- 이유: 작업 현황과 실행 순서를 대기열에서 시각적으로 확인할 수 있어야 하고, 인페인팅 등을 우선 처리하고 싶을 때 드래그로 순서를 바꿀 수 있어야 함. 
- 상태: 계획(미구현)

