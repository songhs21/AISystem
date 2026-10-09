import pytest
from fastapi.testclient import TestClient

from api.main import app

# with 문 없이 생성 → startup(ComfyUI 유휴 감시, 메모리 워커) 실행 안 됨
client = TestClient(app)

T2I = {"checkpoint": "dummy.safetensors"}
UPSCALE = {"gen_id": 1, "image_path": "x.png", "upscale_model": "m", "checkpoint": "dummy.safetensors"}
I2I = {"image_path": "x.png", "checkpoint": "dummy.safetensors"}
I2V = {"image_path": "x.png"}

# (엔드포인트, 기본 body, 필드, 범위 밖 값)
JSON_CASES = [
    ("/api/sd/generate",   T2I,     "lora_strength", [-0.1, 1.1]),
    ("/api/sd/queue/t2i",  T2I,     "lora_strength", [-0.1, 1.1]),
    ("/api/sd/upscale",    UPSCALE, "denoise",       [0.09, 1.01]),
    ("/api/sd/upscale",    UPSCALE, "lora_strength", [-0.1, 1.1]),
    ("/api/sd/i2i",        I2I,     "denoise",       [0.09, 1.01]),
    ("/api/sd/i2i",        I2I,     "lora_strength", [-0.1, 1.1]),
    ("/api/sd/i2v",        I2V,     "cfg",           [0.9, 10.1]),
    ("/api/sd/queue/i2v",  I2V,     "cfg",           [0.9, 10.1]),
]

FORM_CASES = [
    ("/api/sd/i2i-mask",   "denoise",       [0.09, 1.01]),
    ("/api/sd/i2i-mask",   "lora_strength", [-0.1, 1.1]),
    ("/api/sd/queue/i2i",  "denoise",       [0.09, 1.01]),
    ("/api/sd/queue/i2i",  "lora_strength", [-0.1, 1.1]),
]


def _flat(cases):
    return [(p, b, f, v) for p, b, f, vals in cases for v in vals]


@pytest.mark.parametrize("path,body,field,value", _flat(JSON_CASES))
def test_json_out_of_range_422(path, body, field, value):
    r = client.post(path, json={**body, field: value})
    assert r.status_code == 422, f"{path} {field}={value} → {r.status_code}"
    assert r.json()["detail"][0]["loc"][-1] == field


@pytest.mark.parametrize(
    "path,field,value",
    [(p, f, v) for p, f, vals in FORM_CASES for v in vals],
)
def test_form_out_of_range_422(path, field, value):
    r = client.post(path, data={"image_path": "x.png", field: value})
    assert r.status_code == 422, f"{path} {field}={value} → {r.status_code}"
    assert r.json()["detail"][0]["loc"][-1] == field


# 경계값은 엔드포인트가 아니라 모델에서 확인 (엔드포인트는 ComfyUI를 호출하므로)
@pytest.mark.parametrize("v", [0.1, 1.0])
def test_denoise_boundary_ok(v):
    from api.routers.sd import UpscaleRequest
    UpscaleRequest(**UPSCALE, denoise=v)


@pytest.mark.parametrize("v", [0.0, 1.0])
def test_lora_strength_boundary_ok(v):
    from api.routers.sd import GenerateRequest
    GenerateRequest(**T2I, lora_strength=v)


@pytest.mark.parametrize("v", [1.0, 10.0])
def test_i2v_cfg_boundary_ok(v):
    from api.routers.sd import I2VRequest
    I2VRequest(**I2V, cfg=v)