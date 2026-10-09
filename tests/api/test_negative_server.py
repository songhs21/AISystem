"""부정 프롬프트 서버 처리 (TC NG-07, GN-05).

_t2i_events 를 직접 실행하되 ComfyUI 호출(run_comfy)과 DB 기록은 가짜로 바꾼다.
run_comfy 에 전달된 워크플로우의 부정 프롬프트 노드(7)를 확인한다.
"""
import pytest

from api.routers import sd


@pytest.fixture
def captured(monkeypatch):
    box = {}
    monkeypatch.setattr(sd, "is_comfy_alive", lambda: True)
    monkeypatch.setattr(sd, "get_model_config", lambda ckpt: {"width": 512, "height": 768})
    monkeypatch.setattr(sd, "save_generation_start", lambda *a, **k: 1)
    monkeypatch.setattr(sd, "update_generation_meta", lambda *a, **k: None)

    def fake_run_comfy(workflow):
        box["workflow"] = workflow
        return iter(())          # 이벤트 없음: 생성은 일어나지 않는다

    monkeypatch.setattr(sd, "run_comfy", fake_run_comfy)
    return box


def negative_sent(captured, negative):
    req = sd.GenerateRequest(prompt="1girl", negative=negative, checkpoint="modelA.safetensors")
    list(sd._t2i_events(req))
    return captured["workflow"]["7"]["inputs"]["text"]


def test_ng07_empty_negative_is_not_filled_by_server(captured):
    assert negative_sent(captured, "") == ""


def test_gn05_negative_is_used_as_is_with_duplicates_removed(captured):
    assert negative_sent(captured, "bad hands, bad hands, blurry") == "bad hands, blurry"
