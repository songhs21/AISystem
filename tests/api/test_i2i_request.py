"""I2I 요청 서버 처리 (TC IP-19~24).

/api/sd/queue/i2i 는 큐 등록(gen_queue.enqueue)을 가짜로 바꿔 payload 만 확인한다. ComfyUI 는 쓰지 않는다.
IP-24 는 core.image.generate._prepare_i2i_input 을 임시 폴더로 직접 실행한다(모델 기준 해상도를 가짜로 고정).
결함: DEF-008(checkpoint 검증 없음), DEF-009(image_path 검증 없음) — 코드 수정 후 통과해야 한다.
"""
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from api.main import app
from api.routers import sd
from core.image import generate as gen

client = TestClient(app)
QUEUE_I2I = "/api/sd/queue/i2i"
CKPT = "x.safetensors"


@pytest.fixture
def env(monkeypatch, tmp_path):
    """enqueue 가로채기 + 체크포인트 목록 고정 + 마스크 임시파일을 tmp_path 로"""
    box = {"calls": [], "cleanup": []}

    def fake_enqueue(kind, payload, summary, cleanup=None):
        box["calls"].append(payload)
        box["cleanup"].append(cleanup)
        return "test-id"

    monkeypatch.setattr(sd.gen_queue, "enqueue", fake_enqueue)
    monkeypatch.setattr(sd, "get_local_checkpoints", lambda: [CKPT])
    monkeypatch.setattr(sd, "COMFY_INPUT", str(tmp_path))
    img = tmp_path / "base.png"
    Image.new("RGB", (8, 8)).save(img)
    box["image"] = str(img)
    box["dir"] = tmp_path
    return box


def post(env, **over):
    data = {"image_path": env["image"], "checkpoint": CKPT}
    data.update(over)
    data = {k: v for k, v in data.items() if v is not None}
    return client.post(QUEUE_I2I, data=data)


# ── IP-19 체크포인트 누락·빈값·없는 이름 거부 (IPD-01~05)  DEF-008
@pytest.mark.parametrize("ckpt, msg", [
    (None,             "체크포인트를 선택해 주세요."),
    ("",               "체크포인트를 선택해 주세요."),
    ("   ",            "체크포인트를 선택해 주세요."),
    ("ghost.safetensors", "체크포인트를 찾을 수 없습니다: ghost.safetensors"),
    (" x.safetensors", "체크포인트를 찾을 수 없습니다:  x.safetensors"),
], ids=["IPD-01", "IPD-02", "IPD-03", "IPD-04", "IPD-05"])
def test_ip19_bad_checkpoint_rejected(env, ckpt, msg):
    r = post(env, checkpoint=ckpt)
    assert r.status_code == 422
    assert r.json()["detail"] == msg
    assert env["calls"] == []


# ── IP-20 image_path 빈값·없는 파일·폴더 거부 (IPD-06~08)  DEF-009
@pytest.mark.parametrize("which, msg", [
    ("empty",   "베이스 이미지를 선택해 주세요."),
    ("missing", "이미지 파일을 찾을 수 없습니다: "),
    ("dir",     "이미지 파일을 찾을 수 없습니다: "),
], ids=["IPD-06", "IPD-07", "IPD-08"])
def test_ip20_bad_image_path_rejected(env, which, msg):
    path = {"empty": "", "missing": str(env["dir"] / "nope.png"), "dir": str(env["dir"])}[which]
    r = post(env, image_path=path)
    assert r.status_code == 422
    assert r.json()["detail"].startswith(msg)
    assert env["calls"] == []


# ── IP-21 거부된 요청은 마스크 임시파일을 만들지 않는다 (IPD-09)
def test_ip21_rejected_request_leaves_no_mask_file(env):
    r = client.post(QUEUE_I2I, data={"image_path": str(env["dir"] / "nope.png"), "checkpoint": CKPT},
                    files={"mask_file": ("mask.png", b"\x89PNG", "image/png")})
    assert r.status_code == 422
    assert list(env["dir"].glob("i2i_mask_tmp_*")) == []


# ── IP-22 정상 요청: payload 와 기본값 (IPD-10)
def test_ip22_valid_request_payload(env):
    r = post(env, prompt="p", negative="n", denoise="0.5", seed="12", lora_name="l.safetensors", lora_strength="0.4")
    assert r.status_code == 200 and r.json() == {"id": "test-id"}
    p = env["calls"][-1]
    assert p["image_path"] == env["image"] and p["checkpoint"] == CKPT
    assert (p["prompt"], p["negative"], p["denoise"], p["seed"]) == ("p", "n", 0.5, 12)
    assert (p["lora_name"], p["lora_strength"]) == ("l.safetensors", 0.4)
    assert p["mask_path"] is None and env["cleanup"][-1] == []


# ── IP-23 마스크 파일이 있으면 임시파일 저장 + 정리 목록 등록 (IPD-11)
def test_ip23_mask_saved_and_registered_for_cleanup(env):
    r = client.post(QUEUE_I2I, data={"image_path": env["image"], "checkpoint": CKPT},
                    files={"mask_file": ("mask.png", b"MASKBYTES", "image/png")})
    assert r.status_code == 200
    mask = env["calls"][-1]["mask_path"]
    assert mask and open(mask, "rb").read() == b"MASKBYTES"
    assert env["cleanup"][-1] == [mask]


# ── IP-25 seed 상한 (IPD-12~13)
@pytest.mark.parametrize("seed, code", [(2**64 - 1, 200), (2**64, 422)], ids=["IPD-12", "IPD-13"])
def test_ip25_seed_limit(env, seed, code):
    assert post(env, seed=str(seed)).status_code == code


# ── IP-24 큰 이미지 축소 (IPD-14~22)
# 모델 기준 1024x1024 로 고정: 픽셀 수 한도 = 1024*1024*1.15 = 1,205,862
@pytest.fixture
def prep(monkeypatch, tmp_path):
    import config.constants as c
    monkeypatch.setattr(c, "MODEL_RESOLUTION", {"mdl": {"width": 1024, "height": 1024}})
    dest = tmp_path / "comfy_input"
    dest.mkdir()
    monkeypatch.setattr(gen, "COMFY_INPUT", dest)
    src = tmp_path / "src"
    src.mkdir()

    def run(w, h, ckpt="my-mdl.safetensors", name="pic.png"):
        p = src / name
        Image.new("RGB", (w, h), (10, 20, 30)).save(p)
        return gen._prepare_i2i_input(str(p), ckpt), dest
    return run


@pytest.mark.parametrize("w, h", [(1024, 1024), (1100, 1096), (300, 200)],
                         ids=["IPD-14", "IPD-15", "IPD-16"])
def test_ip24_within_limit_not_resized(prep, w, h):
    (name, size, note), dest = prep(w, h)
    assert (name, size, note) == ("pic.png", None, None)
    assert Image.open(dest / "pic.png").size == (w, h)      # 확대·축소 없이 그대로 복사


def test_ip24_just_over_limit_is_resized(prep):             # IPD-17: 1104x1100 = 1,214,400 > 1,205,862
    (name, size, note), dest = prep(1104, 1100)
    assert name == "pic_fit.png" and size is not None and note
    assert Image.open(dest / name).size == size


def test_ip24_1600_square_becomes_1024(prep):               # IPD-18
    (name, size, note), dest = prep(1600, 1600)
    assert (name, size) == ("pic_fit.png", (1024, 1024))
    assert note == "입력 이미지 축소: 1600x1600 → 1024x1024"
    assert Image.open(dest / name).size == (1024, 1024)


@pytest.mark.parametrize("w, h", [(2000, 1000), (1000, 2300), (3001, 1777)],
                         ids=["IPD-19", "IPD-20", "IPD-21"])
def test_ip24_resize_keeps_ratio_and_multiple_of_8(prep, w, h):
    (name, size, note), dest = prep(w, h)
    nw, nh = size
    assert nw % 8 == 0 and nh % 8 == 0
    assert abs(nw / nh - w / h) / (w / h) < 0.02            # 8의 배수 반올림으로 생기는 오차만 허용
    assert nw * nh <= 1024 * 1024 * 1.15
    assert nw < w and nh < h                                # 확대 없음


def test_ip24_unknown_checkpoint_uses_default_budget(prep):  # IPD-22: 기본 832x1216
    (_, size_ok, _), _ = prep(1216, 832, ckpt="unknown.safetensors")
    (_, size_big, _), _ = prep(2432, 1664, ckpt="unknown.safetensors")
    assert size_ok is None
    assert size_big == (1216, 832)


# ── IP-26 업로드: 이미지가 아닌 확장자는 400 + 한글 사유 (IPD-23)
# 화면의 업로드 실패 알럿이 이 사유를 그대로 보여준다(DEF-011). 정상 업로드는 실제 ComfyUI input 폴더에 쓰므로 하지 않는다.
def test_ip26_upload_rejects_non_image_extension():
    r = client.post("/api/system/upload", files={"file": ("note.txt", b"x", "text/plain")})
    assert r.status_code == 400
    assert r.json()["detail"] == "이미지 파일만 업로드 가능합니다"
