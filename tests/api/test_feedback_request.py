"""피드백 저장 서버 처리 (TC FB-20~23).

POST /api/history/feedback 은 DB 저장(save_feedback)과 태그 가중치 갱신(update_tag_weights)을 가짜로 바꿔
넘어간 인자만 확인한다. DB 는 쓰지 않는다.
결함: DEF-015("마음에 들지 않음"인데 좋아요/싫어요/패스 태그와 점수가 저장됨).
"""
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routers import history

client = TestClient(app)
URL = "/api/history/feedback"


@pytest.fixture
def env(monkeypatch):
    box = {"saved": [], "weights": []}
    monkeypatch.setattr(history, "save_feedback", lambda *a: box["saved"].append(a))
    monkeypatch.setattr(history, "update_tag_weights", lambda *a: box["weights"].append(a))
    return box


# FB-20 마음에 들지 않음: 태그·점수는 비우고 사유만 저장, 가중치 갱신 없음 (FBD-04~06)  DEF-015
def test_fb20_dislike_saves_reasons_only(env):
    body = {"generation_id": 7, "score": 9, "liked_tags": ["a"], "disliked_tags": ["b"], "false_tags": ["c"],
            "pass_type": "dislike", "pass_reasons": ["hand", "eye"]}
    assert client.post(URL, json=body).json() == {"ok": True}
    assert env["saved"] == [(7, None, [], [], "dislike", ["hand", "eye"], [])]
    assert env["weights"] == []


# FB-21 그 외 유형: 태그·점수 그대로 저장하고 가중치 갱신, 사유는 저장하지 않음 (FBD-01~03)
@pytest.mark.parametrize("pass_type", [None, "style", "quality"])
def test_fb21_normal_keeps_tags_and_updates_weights(env, pass_type):
    body = {"generation_id": 3, "score": 8, "liked_tags": ["a"], "disliked_tags": ["b"], "false_tags": ["c"],
            "pass_type": pass_type, "pass_reasons": ["hand"]}
    assert client.post(URL, json=body).status_code == 200
    assert env["saved"] == [(3, 8, ["a"], ["b"], pass_type, [], ["c"])]
    assert env["weights"] == [(["a"], ["b"], 8)]


# FB-22 알 수 없는 사유는 422, 아무것도 저장하지 않음 (FBD-07)
def test_fb22_unknown_reason_rejected(env):
    body = {"generation_id": 1, "pass_type": "dislike", "pass_reasons": ["hand", "nope"]}
    r = client.post(URL, json=body)
    assert r.status_code == 422 and "nope" in str(r.json()["detail"])
    assert env["saved"] == [] and env["weights"] == []


# FB-23 점수가 없으면 저장은 하되 가중치는 갱신하지 않음 (FBD-08)
def test_fb23_no_score_skips_weights(env):
    assert client.post(URL, json={"generation_id": 2, "liked_tags": ["a"]}).status_code == 200
    assert env["saved"] == [(2, None, ["a"], [], None, [], [])]
    assert env["weights"] == []
