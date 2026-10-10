"""DEF-005 관찰: ComfyUI 가 빈 checkpoint(ckpt_name "")를 어떻게 처리하는지 본다.
실행: python tests/api/observe_empty_checkpoint.py   (ComfyUI 8188 기동 필요, 백엔드는 필요 없음)

앱의 DB·큐를 거치지 않고 ComfyUI /prompt 에 직접 보낸다(앱 DB 에 기록이 남지 않는다).
ComfyUI 가 요청을 받아들이면(200, prompt_id 반환) 생성이 시작되므로 곧바로 큐 삭제와 인터럽트를 보낸다.
"""
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # 프로젝트 루트
from api.routers.sd import load_workflow          # noqa: E402
from config.PATH import COMFY_URL                  # noqa: E402


def post(ckpt):
    wf = load_workflow()
    wf["4"]["inputs"]["ckpt_name"] = ckpt
    r = requests.post(f"{COMFY_URL}/prompt", json={"prompt": wf, "client_id": "observe"}, timeout=10)
    print(f"\n[ckpt_name={ckpt!r}] status={r.status_code}")
    print(r.text[:1500])
    if r.ok and "prompt_id" in r.json():
        pid = r.json()["prompt_id"]
        print(f"→ 받아들여짐 prompt_id={pid}. 생성을 취소한다.")
        requests.post(f"{COMFY_URL}/queue", json={"delete": [pid]}, timeout=5)
        requests.post(f"{COMFY_URL}/interrupt", timeout=5)
        time.sleep(1)


names = requests.get(f"{COMFY_URL}/object_info/CheckpointLoaderSimple", timeout=10).json()
allowed = names["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
print("ComfyUI 가 허용하는 ckpt_name 목록:", allowed)

post("")
post("no_such_model.safetensors")
