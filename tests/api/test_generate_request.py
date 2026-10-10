"""생성 요청 서버 처리 (TC GN-03·04·11~19·21~24).

_t2i_events 를 직접 실행하되 ComfyUI 호출(run_comfy)은 가짜로 바꾼다. 워크플로우의 긍정 프롬프트(노드 6),
부정 프롬프트(노드 7), seed(노드 3)를 확인한다. prefix 는 가짜 모델 설정으로 고정한다.
GN-24 는 실제 data.db 의 구조만 복사한 테스트 DB 를 쓴다(행은 모두 지움).
결함 후보(GN-12·13·15·16·18·19·23)는 코드를 고치기 전까지 실패한다. 실패하면 결함 리포트를 쓴 뒤 수정한다.
GN-20(부정 프롬프트 중복)은 사용자가 직접 작성한다: run(captured, negative="...")["7"]["inputs"]["text"] 로 확인.
"""
# parametrize 읽는 법:
#   @pytest.mark.parametrize("raw, expected", [(a1, b1), (a2, b2)], ids=[...])
#   → 아래 테스트 함수를 (raw=a1, expected=b1), (raw=a2, expected=b2) 로 각각 한 번씩 실행한다.
#   → 함수 인자 이름은 첫 문자열의 이름과 같아야 한다. ids 는 결과에 [GND-10] 처럼 표시될 이름.

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.main import app
from api.routers import sd
from config.PATH import DB_PATH

client = TestClient(app)
QUEUE_T2I = "/api/sd/queue/t2i"
PREFIX = "masterpiece, high score"
WITH_PREFIX = "with_prefix.safetensors"
NO_PREFIX = "no_prefix.safetensors"
SEED_MAX = 999999999999999      # sd.py 의 난수 상한
SEED_LIMIT = 2**64 - 1          # 요청으로 보낼 수 있는 seed 상한


def fake_config(ckpt):
    cfg = {"width": 512, "height": 768}
    if ckpt == WITH_PREFIX:
        cfg["prefix"] = PREFIX
    return cfg


@pytest.fixture
def captured(monkeypatch):
    box = {}
    monkeypatch.setattr(sd, "is_comfy_alive", lambda: True)
    monkeypatch.setattr(sd, "get_model_config", fake_config)
    monkeypatch.setattr(sd, "save_generation_start", lambda *a, **k: 1)
    monkeypatch.setattr(sd, "update_generation_meta", lambda *a, **k: None)

    def fake_run_comfy(workflow):
        box["workflow"] = workflow
        return iter(())          # 이벤트 없음: 생성은 일어나지 않는다

    monkeypatch.setattr(sd, "run_comfy", fake_run_comfy)
    return box


@pytest.fixture
def queued(monkeypatch):
    calls = []

    def fake_enqueue(kind, payload, summary, cleanup=None):
        calls.append(payload)
        return "test-id"

    monkeypatch.setattr(sd.gen_queue, "enqueue", fake_enqueue)
    # 체크포인트 존재 검증용: 로컬 목록을 가짜로 고정
    monkeypatch.setattr(sd, "get_local_checkpoints",
                        lambda: ["x.safetensors", WITH_PREFIX, NO_PREFIX])
    return calls


def run(captured, checkpoint=WITH_PREFIX, **fields):
    req = sd.GenerateRequest(checkpoint=checkpoint, **fields)
    list(sd._t2i_events(req))
    return captured["workflow"]


def positive(captured, text, checkpoint=WITH_PREFIX):
    return run(captured, checkpoint, prompt=text)["6"]["inputs"]["text"]

def negative(captured, text, checkpoint=WITH_PREFIX):
    return run(captured, checkpoint, negative=text)["7"]["inputs"]["text"]

def norm_tags(text):
    return [t.strip().replace("_", " ").lower() for t in text.split(",") if t.strip()]


def post_raw(body):
    return client.post(QUEUE_T2I, content=body, headers={"content-type": "application/json"})


# ── GN-03 prefix 모델: prefix 가 앞에 붙는다
def test_gn03_prefix_is_prepended(captured):
    assert positive(captured, "1girl, smile") == f"{PREFIX}, 1girl, smile"


# ── GN-04 이미 prefix 로 시작하면 다시 붙이지 않는다 (prefix 태그가 정확히 한 번)
@pytest.mark.parametrize("raw", [f"{PREFIX}, 1girl", "Masterpiece, High_Score, 1girl"],
                         ids=["exact", "case-underscore"])
def test_gn04_prefix_not_attached_twice(captured, raw):
    tags = norm_tags(positive(captured, raw))
    assert tags.count("masterpiece") == 1 and tags.count("high score") == 1 and "1girl" in tags


# ── GN-11 필드 생략 시 기본값
def test_gn11_defaults_when_fields_omitted(queued):
    r = post_raw('{"checkpoint": "x.safetensors"}')
    assert r.status_code == 200
    p = queued[-1]
    assert (p["prompt"], p["negative"], p["seed"], p["lora_name"], p["lora_strength"]) == ("", "", -1, "", 0.8)


# ── GN-12 checkpoint 생략 / GN-13 빈 문자열: 422, 큐 미등록, 누락 메시지
def _assert_missing_checkpoint(r, queued):
    assert r.status_code == 422
    assert queued == []
    assert "체크포인트" in json.dumps(r.json(), ensure_ascii=False), "오류 메시지에 체크포인트 누락이 명시되지 않음"


def test_gn12_checkpoint_omitted_rejected(queued):
    _assert_missing_checkpoint(post_raw("{}"), queued)


def test_gn13_checkpoint_empty_rejected(queued):
    _assert_missing_checkpoint(post_raw('{"checkpoint": ""}'), queued)


# ── GN-26 로컬 목록에 없는 체크포인트 이름: 422, 큐 미등록, 이름이 담긴 메시지 (GND-29~32)
@pytest.mark.parametrize("name", ["ghost.safetensors", "model.txt", "../x.safetensors", " x.safetensors"],
                         ids=["GND-29", "GND-30", "GND-31", "GND-32"])
def test_gn26_unknown_checkpoint_rejected(queued, name):
    r = post_raw(json.dumps({"checkpoint": name}))
    assert r.status_code == 422
    assert queued == []
    text = json.dumps(r.json(), ensure_ascii=False)
    assert "체크포인트를 찾을 수 없습니다" in text and name in text


# ── GN-27 공백만 있는 checkpoint 는 누락으로 취급 (GND-33)
def test_gn27_checkpoint_blank_rejected(queued):
    _assert_missing_checkpoint(post_raw('{"checkpoint": "   "}'), queued)


# ── GN-14 / GN-17 prefix 없는 모델
def test_gn14_no_prefix_model_uses_prompt_only(captured):
    assert positive(captured, "1girl", NO_PREFIX) == "1girl"


def test_gn17_empty_prompt_no_prefix_model(captured):
    assert positive(captured, "", NO_PREFIX) == ""


# ── GN-15 prefix 와 같은 태그는 프롬프트 쪽을 제거 (GND-01~03)
@pytest.mark.parametrize("raw", ["1girl, masterpiece", "Masterpiece, 1girl", "high_score, 1girl"],
                         ids=["GND-01", "GND-02", "GND-03"])
def test_gn15_duplicate_with_prefix_removed_from_prompt(captured, raw):
    assert positive(captured, raw) == f"{PREFIX}, 1girl"


# ── GN-16 빈 프롬프트 + prefix 모델 (GND-04)
def test_gn16_empty_prompt_gives_prefix_only(captured):
    assert positive(captured, "") == PREFIX


# ── GN-18 앞쪽 쉼표 제거 (GND-05~06)
@pytest.mark.parametrize("raw", [", 1girl", " ,, 1girl"], ids=["GND-05", "GND-06"])
def test_gn18_leading_commas_removed(captured, raw):
    assert positive(captured, raw) == f"{PREFIX}, 1girl"


# ── GN-19 프롬프트 내부 중복 제거, 처음 철자 유지 (GND-07~09)
@pytest.mark.parametrize("raw, expected", [
    ("1girl, 1girl, smile", "1girl, smile"),
    ("1girl, 1GIRL", "1girl"),
    ("long hair, long_hair", "long hair"),
], ids=["GND-07", "GND-08", "GND-09"])
def test_gn19_duplicates_inside_prompt_removed(captured, raw, expected):
    assert positive(captured, raw, NO_PREFIX) == expected


# ── GN-20 네거티브 양 끝 공백 제거 (GND 10~12, 26~28)
@pytest.mark.parametrize("raw, expected", [
    ("bad anatomy, BaD AnaToMY, naked", "bad anatomy, naked"),
    ("bad anatomy, BAD ANATOMY, naked", "bad anatomy, naked"),
    ("bad anatomy, bad anatomy, naked", "bad anatomy, naked"),
    (" bad anatomy, skeleton, naked,kid", "bad anatomy, skeleton, naked, kid"),
    ("bad anatomy, skeleton, naked,kid   ", "bad anatomy, skeleton, naked, kid"),
    (" bad anatomy, skeleton, naked,kid   ", "bad anatomy, skeleton, naked, kid"),
], ids=["GND-10", "GND-11", "GND-12", "GND-26", "GND-27", "GND-28"])
def test_gn20_negative_dedupe_and_trim(captured, raw, expected):
    assert negative(captured, raw) == expected

# ── GN-21 음수 seed 는 난수 (GND-13~15)
@pytest.mark.parametrize("seed", [-1, -2, -2**63], ids=["GND-13", "GND-14", "GND-15"])
def test_gn21_negative_seed_becomes_random(captured, seed):
    used = run(captured, seed=seed)["3"]["inputs"]["seed"]
    assert used != seed and 1 <= used <= SEED_MAX


# ── GN-22 0 이상 ~ 2^64-1 은 그대로 (GND-16~22)
@pytest.mark.parametrize("seed", [0, 1, 2**31 - 1, 2**31, 2**53 + 1, 2**63 - 1, 2**64 - 1],
                         ids=[f"GND-{i}" for i in range(16, 23)])
def test_gn22_valid_seed_used_as_is(captured, seed):
    assert run(captured, seed=seed)["3"]["inputs"]["seed"] == seed


# ── GN-23 2^64-1 초과는 422, 큐 미등록 (GND-23~25)
@pytest.mark.parametrize("literal", ["18446744073709551616", "36893488147419103232", "1e304"],
                         ids=["GND-23", "GND-24", "GND-25"])
def test_gn23_seed_above_limit_rejected(queued, literal):
    r = post_raw('{"checkpoint": "x.safetensors", "seed": %s}' % literal)
    assert r.status_code == 422
    assert queued == []


# ── GN-24 DB 저장값: 실제 data.db 의 구조만 복사한 테스트 DB 사용
@pytest.fixture
def test_db(tmp_path, monkeypatch):
    if not Path(DB_PATH).exists():
        pytest.skip("data.db 가 없어 구조를 복사할 수 없음")
    dst_path = tmp_path / "test.db"
    src = sqlite3.connect(Path(DB_PATH).as_uri() + "?mode=ro", uri=True)
    dst = sqlite3.connect(dst_path)
    src.backup(dst)
    src.close()
    tables = [r[0] for r in dst.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    for t in tables:
        dst.execute(f'DELETE FROM "{t}"')       # 구조만 남기고 행은 모두 지운다
    dst.commit()
    dst.close()
    monkeypatch.setattr("core.db.DB_PATH", dst_path)    # get_conn 이 호출될 때마다 이 값을 읽는다
    return dst_path


@pytest.mark.parametrize("lora, strength", [("", 0.8), ("lora1.safetensors", 0.6)], ids=["no-lora", "lora"])
def test_gn24_db_row_matches_input(test_db, monkeypatch, lora, strength):
    monkeypatch.setattr(sd, "is_comfy_alive", lambda: True)
    monkeypatch.setattr(sd, "get_model_config", fake_config)
    monkeypatch.setattr(sd, "run_comfy", lambda workflow: iter(()))
    req = sd.GenerateRequest(prompt="1girl, smile", negative="a, A, b", checkpoint=WITH_PREFIX,
                             lora_name=lora, lora_strength=strength)
    list(sd._t2i_events(req))

    conn = sqlite3.connect(test_db)
    row = conn.execute("SELECT prompt, negative, checkpoint, lora_name, lora_strength "
                       "FROM generations ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    expected = (f"{PREFIX}, 1girl, smile", "a, b", WITH_PREFIX,
                lora or None, strength if lora else None)
    assert row == expected


# ── GN-28 seed 상한은 업스케일·I2I·I2V 요청 모델에도 적용 (GND-34·35)
@pytest.mark.parametrize("model, fields", [
    (sd.UpscaleRequest, dict(gen_id=1, image_path="a.png", upscale_model="m.pth", checkpoint="c")),
    (sd.I2IRequest, dict(image_path="a.png", checkpoint="c")),
    (sd.I2VRequest, dict(image_path="a.png")),
], ids=["upscale", "i2i", "i2v"])
def test_gn28_seed_limit_on_other_requests(model, fields):
    assert model(seed=SEED_LIMIT, **fields).seed == SEED_LIMIT        # GND-34
    with pytest.raises(ValidationError):                              # GND-35
        model(seed=SEED_LIMIT + 1, **fields)
