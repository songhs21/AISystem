"""I2V 요청 서버 처리 (TC IV-20~23·35).

/api/sd/queue/i2v 는 큐 등록(gen_queue.enqueue)을 가짜로 바꿔 payload 와 summary 만 확인한다. ComfyUI 는 쓰지 않는다.
IV-23 은 core.video.i2v_generate.pad_to_wan_resolution 을 임시 폴더에서 직접 실행한다.
결함: DEF-012(image_path 검증 없음).
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from api.main import app
from api.routers import sd
from core.video.i2v_generate import pad_to_wan_resolution

client = TestClient(app)
QUEUE_I2V = "/api/sd/queue/i2v"
COLOR = (200, 80, 40)
WHITE = (255, 255, 255)


@pytest.fixture
def env(monkeypatch, tmp_path):
    box = {"calls": [], "summaries": []}

    def fake_enqueue(kind, payload, summary, cleanup=None):
        assert kind == "i2v"
        box["calls"].append(payload)
        box["summaries"].append(summary)
        return "test-id"

    monkeypatch.setattr(sd.gen_queue, "enqueue", fake_enqueue)
    img = tmp_path / "base.png"
    Image.new("RGB", (8, 8)).save(img)
    box["image"] = str(img)
    box["dir"] = tmp_path
    return box


# ── IV-20 정상 요청: 생략한 필드는 기본값, 지정한 값은 그대로 (IVD-01~02)
def test_iv20_defaults_when_only_image_given(env):
    r = client.post(QUEUE_I2V, json={"image_path": env["image"]})
    assert r.status_code == 200 and r.json() == {"id": "test-id"}
    assert env["calls"][-1] == {
        "image_path": env["image"], "prompt": "", "negative": "", "seed": -1,
        "width": 832, "height": 480, "length": 81, "high_steps": 2, "low_steps": 3,
        "cfg": 1.0, "frame_rate": 10}
    s = env["summaries"][-1]
    assert (s["mode"], s["base_image"], s["width"], s["height"], s["length"]) == ("i2v", env["image"], 832, 480, 81)


def test_iv20_given_values_are_kept(env):
    body = {"image_path": env["image"], "prompt": "p", "negative": "n", "seed": 12, "width": 1024, "height": 576,
            "length": 49, "high_steps": 4, "low_steps": 6, "cfg": 2.5, "frame_rate": 16}
    assert client.post(QUEUE_I2V, json=body).status_code == 200
    assert env["calls"][-1] == body


# ── IV-21 image_path 빈값·없는 파일·폴더 거부 (IVD-03~05)  DEF-012
@pytest.mark.parametrize("which, msg", [
    ("empty",   "베이스 이미지를 선택해 주세요."),
    ("missing", "이미지 파일을 찾을 수 없습니다: "),
    ("dir",     "이미지 파일을 찾을 수 없습니다: "),
], ids=["IVD-03", "IVD-04", "IVD-05"])
def test_iv21_bad_image_path_rejected(env, which, msg):
    path = {"empty": "", "missing": str(env["dir"] / "nope.png"), "dir": str(env["dir"])}[which]
    r = client.post(QUEUE_I2V, json={"image_path": path})
    assert r.status_code == 422
    assert r.json()["detail"].startswith(msg)
    assert env["calls"] == []


# ── IV-22 seed 상한 (IVD-06~07)
@pytest.mark.parametrize("seed, code", [(2**64 - 1, 200), (2**64, 422)], ids=["IVD-06", "IVD-07"])
def test_iv22_seed_limit(env, seed, code):
    assert client.post(QUEUE_I2V, json={"image_path": env["image"], "seed": seed}).status_code == code


# ── IV-23 입력 이미지를 목표 해상도 캔버스에 맞춤 (IVD-08~12)
# 비율을 유지해 목표 안에 들어가게 맞추고(확대 포함), 크기는 32의 배수로 내림, 가운데에 놓고 남는 곳은 흰색
def close(px, color, tol=3):
    return all(abs(a - b) <= tol for a, b in zip(px, color))


@pytest.fixture
def pad(tmp_path):
    def run(w, h, tw, th):
        src = tmp_path / "src.png"
        dst = tmp_path / "dst.png"
        Image.new("RGB", (w, h), COLOR).save(src)
        pad_to_wan_resolution(Path(src), Path(dst), tw, th)
        return Image.open(dst).convert("RGB")
    return run


def test_iv23_wide_image_gets_vertical_padding(pad):          # IVD-08: 1000x500 → 832x416, 위아래 32px 흰색
    out = pad(1000, 500, 832, 480)
    assert out.size == (832, 480)
    assert close(out.getpixel((416, 240)), COLOR)
    assert close(out.getpixel((5, 5)), WHITE) and close(out.getpixel((5, 475)), WHITE)
    assert close(out.getpixel((5, 40)), COLOR)


def test_iv23_small_image_is_enlarged(pad):                   # IVD-09: 100x100 → 480x480, 좌우 176px 흰색
    out = pad(100, 100, 832, 480)
    assert out.size == (832, 480)
    assert close(out.getpixel((416, 240)), COLOR) and close(out.getpixel((180, 5)), COLOR)
    assert close(out.getpixel((170, 240)), WHITE) and close(out.getpixel((660, 240)), WHITE)


def test_iv23_same_ratio_has_no_padding(pad):                 # IVD-10: 1664x960 → 832x480
    out = pad(1664, 960, 832, 480)
    assert close(out.getpixel((1, 1)), COLOR) and close(out.getpixel((830, 478)), COLOR)


def test_iv23_resized_size_rounded_down_to_32(pad):           # IVD-11: 1000x1000 → 720 이 아니라 704x704 (1280x720 캔버스)
    out = pad(1000, 1000, 1280, 720)
    assert out.size == (1280, 720)
    assert close(out.getpixel((290, 10)), COLOR) and close(out.getpixel((988, 710)), COLOR)
    assert close(out.getpixel((286, 360)), WHITE) and close(out.getpixel((640, 4)), WHITE)


def test_iv23_portrait_image_gets_side_padding(pad):          # IVD-12: 500x1000 → 224x480(내림), 좌우 흰색
    out = pad(500, 1000, 832, 480)
    assert out.size == (832, 480)
    assert close(out.getpixel((416, 240)), COLOR)
    assert close(out.getpixel((100, 240)), WHITE) and close(out.getpixel((730, 240)), WHITE)


# ── IV-35 최소값 미만은 422, 최소값은 허용 (IVD-13~18)
# 사용자 결정(2026-10-10): Width 832, Height 480, Frames 10, High·Low Steps 각 2. 상한은 두지 않는다.
@pytest.mark.parametrize("field, value", [
    ("width", 831), ("width", 0), ("height", 479), ("height", -1),
    ("length", 9), ("length", 0), ("high_steps", 1), ("high_steps", 0), ("low_steps", 1), ("low_steps", -3),
], ids=["IVD-13", "IVD-14", "IVD-15", "IVD-16", "IVD-17", "IVD-18", "IVD-19", "IVD-20", "IVD-21", "IVD-22"])
def test_iv35_below_minimum_rejected(env, field, value):
    r = client.post(QUEUE_I2V, json={"image_path": env["image"], field: value})
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"][-1] == field
    assert env["calls"] == []


def test_iv35_minimum_values_accepted(env):                    # IVD-23
    body = {"image_path": env["image"], "width": 832, "height": 480, "length": 10, "high_steps": 2, "low_steps": 2}
    assert client.post(QUEUE_I2V, json=body).status_code == 200
    assert env["calls"][-1] == {**body, "prompt": "", "negative": "", "seed": -1, "cfg": 1.0, "frame_rate": 10}
