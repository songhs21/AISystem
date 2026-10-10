import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routers import sd

client = TestClient(app)
QUEUE_I2I = "/api/sd/queue/i2i"
QUEUE_T2I = "/api/sd/queue/t2i"


@pytest.fixture
def queued(monkeypatch):
    """큐 등록을 가로채 실제 작업이 생성되지 않게 하고, 등록된 payload를 기록"""
    calls = []

    def fake_enqueue(kind, payload, summary, cleanup=None):
        calls.append(payload)
        return "test-id"

    monkeypatch.setattr(sd.gen_queue, "enqueue", fake_enqueue)
    # I2I 는 체크포인트·이미지 파일 존재 검증이 있으므로 둘 다 통과하도록 고정
    monkeypatch.setattr(sd, "get_local_checkpoints", lambda: ["x.safetensors"])
    monkeypatch.setattr(sd, "_image_exists", lambda p: True)
    return calls


def post_i2i(denoise=None):
    data = {"image_path": "x.png", "checkpoint": "x.safetensors"}
    if denoise is not None:
        data["denoise"] = denoise
    return client.post(QUEUE_I2I, data=data)


# ── DN-01 허용 범위 값 (DND-01~05)
@pytest.mark.parametrize("v", ["0.1", "0.15", "0.5", "0.95", "1.0"],
                         ids=["DND-01", "DND-02", "DND-03", "DND-04", "DND-05"])
def test_dn01_valid_values_are_queued(queued, v):
    r = post_i2i(v)
    assert r.status_code == 200
    assert queued[-1]["denoise"] == float(v)


# ── DN-02 범위 미만 (DND-06~08)
@pytest.mark.parametrize("v", ["0.05", "0", "-1"], ids=["DND-06", "DND-07", "DND-08"])
def test_dn02_below_range_rejected(queued, v):
    assert post_i2i(v).status_code == 422
    assert queued == []


# ── DN-03 범위 초과 (DND-09~10)
@pytest.mark.parametrize("v", ["1.05", "2"], ids=["DND-09", "DND-10"])
def test_dn03_above_range_rejected(queued, v):
    assert post_i2i(v).status_code == 422
    assert queued == []


# ── DN-04 숫자가 아닌 값 (DND-11~12)
@pytest.mark.parametrize("v", ["abc", "0,5"], ids=["DND-11", "DND-12"])
def test_dn04_non_numeric_rejected(queued, v):
    assert post_i2i(v).status_code == 422
    assert queued == []


# ── DN-05 NaN·Infinity (DND-13~16)
@pytest.mark.parametrize("v", ["nan", "inf", "-inf", "1e309"],
                         ids=["DND-13", "DND-14", "DND-15", "DND-16"])
def test_dn05_nan_inf_rejected(queued, v):
    assert post_i2i(v).status_code == 422
    assert queued == []


# ── DN-06 생략 시 기본값 (DND-17)
def test_dn06_default_when_omitted(queued):
    assert post_i2i().status_code == 200
    assert queued[-1]["denoise"] == 0.7


# ── DN-07 step 비배수 허용 (DND-18)
def test_dn07_non_step_value_allowed(queued):
    assert post_i2i("0.33").status_code == 200
    assert queued[-1]["denoise"] == 0.33


# ── LR-06 lora_strength 범위 밖 (LRD-06~10), 대상: /api/sd/queue/t2i
def post_t2i_raw(value_literal):
    body = '{"checkpoint": "dummy.safetensors", "lora_strength": %s}' % value_literal
    return client.post(QUEUE_T2I, content=body, headers={"content-type": "application/json"})


@pytest.mark.parametrize("v", ["-0.05", "1.05", "2", "NaN", "1e309"],
                         ids=["LRD-06", "LRD-07", "LRD-08", "LRD-09", "LRD-10"])
def test_lr06_lora_strength_out_of_range_rejected(queued, v):
    assert post_t2i_raw(v).status_code == 422
    assert queued == []