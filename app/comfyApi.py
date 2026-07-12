# comfyApi.py
import requests
import websocket
import json
import glob
import os
import subprocess
import time
import uuid
import sqlite3
import random
import shutil
from config.PATH import DB_PATH, COMFY_DIR, COMFY_URL, COMFY_WS, COMFY_INPUT, COMFY_OUTPUT, PYTHON_EXE, UPSCALE_WORKFLOW_DIR, INPAINTING_DIR, DETAIL_INPAINTING_DIR


# ComfyUI 서버 생존 확인
def is_comfy_alive():
    try:
        requests.get(f"{COMFY_URL}/system_stats", timeout=1)
        return True
    except:
        return False


# ComfyUI 서버 서브프로세스 실행
def start_comfy():
    main_py = os.path.join(COMFY_DIR, "main.py")
    subprocess.Popen([PYTHON_EXE, main_py], cwd=COMFY_DIR)


# ComfyUI 서버 응답 대기 (alive 확인될 때까지 폴링)
def wait_for_comfy():
    while not is_comfy_alive():
        time.sleep(2)


# 업스케일 워크플로우 JSON 로드
def load_upscale_workflow():
    with open(UPSCALE_WORKFLOW_DIR, "r", encoding="utf-8") as f:
        return json.load(f)


# 인페인팅 워크플로우 JSON 로드 (mode: replace=일반, detail=디테일)
def load_inpaint_workflow(mode="replace"):
    path = INPAINTING_DIR if mode == "replace" else DETAIL_INPAINTING_DIR
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# 파일 I/O 완료 대기 (존재 + size > 0 확인, timeout 초과 시 False 반환)
def wait_for_file_ready(filepath, timeout=3):
    start_time = time.time()

    while time.time() - start_time < timeout:
        exists = os.path.exists(filepath)
        size = os.path.getsize(filepath) if exists else -1

        if exists and size > 0:
            return True

        time.sleep(0.1)

    return False


# 이미지 생성 요청 → WebSocket 진행 이벤트 yield → 완료 시 image_path yield
# yield {"type": "progress", "value": 0.0~1.0, "text": str}
# yield {"type": "prompt_id", "prompt_id": str, "before": float}
# yield {"type": "done", "image_path": str, "prompt_id": str}
def run_comfy(workflow, client_id=None):
    if client_id is None:
        client_id = str(uuid.uuid4())

    # ComfyUI 미실행 시 자동 기동
    if not is_comfy_alive():
        yield {"type": "progress", "value": 0.0, "text": "ComfyUI 시작 중..."}
        start_comfy()
        wait_for_comfy()

    before = time.time()

    # 워크플로우 전송 및 prompt_id 수신
    response = requests.post(f"{COMFY_URL}/prompt", json={"prompt": workflow, "client_id": client_id})
    prompt_id = response.json()["prompt_id"]

    yield {"type": "prompt_id", "prompt_id": prompt_id, "before": before}
    yield {"type": "progress", "value": 0.02, "text": "큐 등록됨..."}

    # WebSocket 연결 및 진행 이벤트 수신
    ws = websocket.WebSocket()
    ws.connect(f"{COMFY_WS}?clientId={client_id}")

    try:
        while True:
            raw = ws.recv()
            if isinstance(raw, bytes):
                continue

            msg = json.loads(raw)
            mtype = msg.get("type")
            data  = msg.get("data", {})

            if mtype == "status":
                remaining = data.get("status", {}).get("exec_info", {}).get("queue_remaining", None)
                if remaining is not None and remaining > 0:
                    yield {"type": "progress", "value": 0.05, "text": f"큐 대기 중... (앞 {remaining}개)"}

            elif mtype == "execution_start":
                yield {"type": "progress", "value": 0.1, "text": "생성 시작..."}

            elif mtype == "execution_cached":
                yield {"type": "progress", "value": 0.15, "text": "캐시 로드 중..."}

            elif mtype == "progress":
                value = data.get("value", 0)
                max_v = data.get("max", 1)
                # 스텝 진행률을 0.15~0.95 구간에 매핑
                mapped = 0.15 + (value / max_v if max_v > 0 else 0) * 0.80
                yield {"type": "progress", "value": mapped, "text": f"스텝 {value}/{max_v}"}

            elif mtype == "executing" and data.get("node") is None:
                yield {"type": "progress", "value": 0.97, "text": "후처리 중..."}
                break

    finally:
        ws.close()

    # 생성 시작 이후 신규 파일 탐색
    files = glob.glob(os.path.join(COMFY_OUTPUT, "*.png"))
    new_files = [f for f in files if os.path.getctime(f) > before]

    if not new_files:
        raise RuntimeError("생성된 이미지를 찾을 수 없음")

    image_path = max(new_files, key=os.path.getctime)
    yield {"type": "done", "image_path": image_path, "prompt_id": prompt_id}


# 이미지 업스케일 요청 → WebSocket 진행 이벤트 yield → 완료 시 image_path yield
# yield {"type": "progress", "value": 0.0~1.0, "text": str}
# yield {"type": "done", "image_path": str}
def run_upscale(image_path, select_upscaler, checkpoint, prompt, negative="", client_id=None):
    if client_id is None:
        client_id = str(uuid.uuid4())

    # ComfyUI 미실행 시 자동 기동
    if not is_comfy_alive():
        yield {"type": "progress", "value": 0.0, "text": "ComfyUI 시작 중..."}
        start_comfy()
        wait_for_comfy()

    # 원본 이미지를 ComfyUI input 폴더로 복사
    filename = os.path.basename(image_path)
    shutil.copy2(image_path, os.path.join(COMFY_INPUT, filename))

    # 워크플로우 로드 및 노드 주입 (이미지/체크포인트/프롬프트/업스케일 모델)
    workflow = load_upscale_workflow()
    workflow["4"]["inputs"]["image"] = filename
    workflow["10"]["inputs"]["ckpt_name"] = checkpoint
    workflow["16"]["inputs"]["text"] = prompt
    workflow["17"]["inputs"]["text"] = negative
    if select_upscaler:
        workflow["14"]["inputs"]["model_name"] = select_upscaler

    # 출력 파일명 prefix 설정 (origin_stem + model_stem 조합)
    origin_stem = os.path.splitext(filename)[0].strip()
    model_stem = os.path.splitext(workflow["14"]["inputs"]["model_name"])[0].strip()
    workflow["3"]["inputs"]["filename_prefix"] = f"{origin_stem}_{model_stem}"

    before = time.time()

    # 워크플로우 전송
    response = requests.post(f"{COMFY_URL}/prompt", json={"prompt": workflow, "client_id": client_id})
    prompt_id = response.json()["prompt_id"]
    yield {"type": "progress", "value": 0.05, "text": "업스케일 큐 등록됨..."}

    # WebSocket 연결 및 진행 이벤트 수신
    ws = websocket.WebSocket()
    ws.connect(f"{COMFY_WS}?clientId={client_id}")

    try:
        while True:
            raw = ws.recv()
            if isinstance(raw, bytes):
                continue

            msg = json.loads(raw)
            mtype = msg.get("type")
            data  = msg.get("data", {})

            if mtype == "execution_start":
                yield {"type": "progress", "value": 0.1, "text": "업스케일 시작..."}

            elif mtype == "progress":
                value = data.get("value", 0)
                max_v = data.get("max", 1)
                mapped = 0.1 + (value / max_v if max_v > 0 else 0) * 0.80
                yield {"type": "progress", "value": mapped, "text": f"스텝 {value}/{max_v}"}

            elif mtype == "executing" and data.get("node") is None:
                yield {"type": "progress", "value": 0.97, "text": "업스케일 저장 중..."}
                break

    finally:
        ws.close()

    # 생성 시작 이후 신규 파일 탐색
    files = glob.glob(os.path.join(COMFY_OUTPUT, f"{origin_stem}*{model_stem}*.png"))
    new_files = [f for f in files if os.path.getctime(f) > before]

    if not new_files:
        actual_files = [os.path.basename(f) for f in glob.glob(os.path.join(COMFY_OUTPUT, "*.png"))[-3:]]
        raise RuntimeError(
            f"업스케일된 이미지를 찾을 수 없음\n"
            f"▶ 검색 패턴: {origin_stem}*{model_stem}*.png\n"
            f"▶ 최근 파일들: {actual_files}"
        )

    yield {"type": "done", "image_path": max(new_files, key=os.path.getctime)}


# 인페인팅 요청 → WebSocket 진행 이벤트 yield → 완료 시 image_path yield
# mode: "replace" = VAEEncodeForInpaint (복장/배경), "detail" = InpaintModelConditioning (눈/손)
# yield {"type": "progress", "value": 0.0~1.0, "text": str}
# yield {"type": "done", "image_path": str}
def run_inpaint(image_path, mask_path, checkpoint, prompt, negative="", denoise=0.75, steps=20, mode="replace", client_id=None):
    if client_id is None:
        client_id = str(uuid.uuid4())

    # ComfyUI 미실행 시 자동 기동
    if not is_comfy_alive():
        yield {"type": "progress", "value": 0.0, "text": "ComfyUI 시작 중..."}
        start_comfy()
        wait_for_comfy()

    # 원본 이미지 / 마스크 파일을 ComfyUI input 폴더로 복사 및 I/O 완료 대기
    filename = os.path.basename(image_path)
    origin_stem = os.path.splitext(filename)[0].strip()

    assert os.path.exists(mask_path), f"마스크 파일 없음: {repr(mask_path)}"

    mask_filename = os.path.basename(mask_path)
    mask_input_path = os.path.join(COMFY_INPUT, mask_filename)

    if os.path.normpath(mask_path) != os.path.normpath(mask_input_path):
        shutil.copy2(mask_path, mask_input_path)

    if not wait_for_file_ready(mask_input_path):
        raise TimeoutError("마스크 파일 I/O 대기 시간 초과")
    if not os.path.exists(mask_input_path):
        raise FileNotFoundError(mask_input_path)

    # 모드별 워크플로우 로드 및 노드 주입
    if mode == "detail":
        with open(DETAIL_INPAINTING_DIR, "r", encoding="utf-8") as f:
            workflow = json.load(f)

        # 이미지 / 체크포인트 주입
        workflow["1"]["inputs"]["image"] = filename
        workflow["3"]["inputs"]["ckpt_name"] = checkpoint

        # 마스크 주입 (LoadImageMask 노드22, channel=red 고정)
        if "22" in workflow:
            workflow["22"]["inputs"]["image"] = mask_filename
            workflow["22"]["inputs"]["channel"] = "red"

        # 프롬프트 주입 (텍스트 인코더 18=긍정, 19=부정)
        if "18" in workflow: workflow["18"]["inputs"]["text"] = prompt
        if "19" in workflow: workflow["19"]["inputs"]["text"] = negative

        # 샘플러 파라미터 주입 (KSampler 노드8)
        workflow["8"]["inputs"]["seed"]    = random.randint(1, 1125899906842624)
        workflow["8"]["inputs"]["steps"]   = steps
        workflow["8"]["inputs"]["denoise"] = denoise

    else:
        with open(INPAINTING_DIR, "r", encoding="utf-8") as f:
            workflow = json.load(f)

        # 이미지 / 마스크 주입 (노드1=이미지, 노드2=마스크, channel=red 고정)
        workflow["1"]["inputs"]["image"]   = filename
        workflow["2"]["inputs"]["image"]   = mask_filename
        workflow["2"]["inputs"]["channel"] = "red"

        # 프롬프트 주입 (텍스트 인코더 4=긍정, 5=부정)
        workflow["4"]["inputs"]["text"] = prompt
        workflow["5"]["inputs"]["text"] = negative

        # 샘플러 파라미터 주입 (KSampler 노드8)
        workflow["8"]["inputs"]["seed"]    = random.randint(1, 1125899906842624)
        workflow["8"]["inputs"]["steps"]   = steps
        workflow["8"]["inputs"]["denoise"] = denoise

    # 인페인팅 누적 횟수 기반 출력 파일명 prefix 생성
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM inpainting WHERE file_name LIKE ?", (f"{origin_stem}_inpainting%",))
    count = cursor.fetchone()[0] + 1
    conn.close()

    output_prefix = f"{origin_stem}_inpainting_{count:04d}"
    workflow["10"]["inputs"]["filename_prefix"] = output_prefix

    before = time.time()

    # 워크플로우 전송 및 응답 검증
    resp_json = None
    try:
        response = requests.post(
            f"{COMFY_URL}/prompt",
            json={"prompt": workflow, "client_id": client_id},
            timeout=5
        )
        response.raise_for_status()
        resp_json = response.json()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"ComfyUI 서버 통신 실패: {e}")
    except ValueError:
        raise RuntimeError("ComfyUI 서버가 올바른 JSON 응답을 반환하지 않았습니다.")

    if not resp_json or "prompt_id" not in resp_json:
        error_obj = resp_json.get("error", {}) if (resp_json and isinstance(resp_json.get("error"), dict)) else {}
        raise ValueError(
            f"ComfyUI 노드 검증 실패: {error_obj.get('message', '유효성 검증 실패')}\n"
            f"▶ 노드 에러: {resp_json.get('node_errors', {}) if resp_json else {}}"
        )

    prompt_id = resp_json["prompt_id"]
    yield {"type": "progress", "value": 0.05, "text": "인페인팅 큐 등록됨..."}

    # WebSocket 연결 및 진행 이벤트 수신
    ws = websocket.WebSocket()
    ws.connect(f"{COMFY_WS}?clientId={client_id}")

    try:
        while True:
            raw = ws.recv()
            if isinstance(raw, bytes):
                continue

            msg = json.loads(raw)
            mtype = msg.get("type")
            data  = msg.get("data", {})

            if mtype == "execution_start":
                yield {"type": "progress", "value": 0.1, "text": "인페인팅 시작..."}

            elif mtype == "progress":
                value = data.get("value", 0)
                max_v = data.get("max", 1)
                mapped = 0.1 + (value / max_v if max_v > 0 else 0) * 0.85
                yield {"type": "progress", "value": mapped, "text": f"스텝 {value}/{max_v}"}

            elif mtype == "executing" and data.get("node") is None:
                yield {"type": "progress", "value": 0.97, "text": "저장 중..."}
                break

    finally:
        ws.close()

    # 생성 시작 이후 신규 파일 탐색
    files = glob.glob(os.path.join(COMFY_OUTPUT, f"{output_prefix}*.png"))
    new_files = [f for f in files if os.path.getctime(f) > before]

    if not new_files:
        actual_files = [os.path.basename(f) for f in glob.glob(os.path.join(COMFY_OUTPUT, "*.png"))[-3:]]
        raise RuntimeError(
            f"인페인팅 이미지를 찾을 수 없음\n"
            f"▶ 검색 패턴: {output_prefix}*.png\n"
            f"▶ 최근 파일들: {actual_files}"
        )

    yield {"type": "done", "image_path": max(new_files, key=os.path.getctime)}