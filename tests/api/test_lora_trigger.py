"""LoRA 트리거 단어 위치 검증 (TC LR-08, LR-10).

실제 워크플로우 JSON(T2I: WORKFLOW_PATH, 마스크 I2I: I2I_MASK)에 apply_lora_patch를 적용한다.
트리거 파일(lora_triggers.json)은 임시 파일로 바꿔서 쓰므로 실제 파일 내용과 무관하다.
ComfyUI는 호출하지 않는다.
"""
import json

import pytest

from config.PATH import I2I_MASK, WORKFLOW_PATH
from core.image import generate as gen

LORA = "test_lora.safetensors"
TRIGGER = "trigword_xyz"


@pytest.fixture
def triggers(tmp_path, monkeypatch):
    f = tmp_path / "lora_triggers.json"
    f.write_text(json.dumps({LORA: TRIGGER}), encoding="utf-8")
    monkeypatch.setattr(gen, "LORA_TRIGGERS", f)


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_lr08_t2i_trigger_is_prepended_to_prompt_node(triggers):
    wf = load(WORKFLOW_PATH)
    wf["6"]["inputs"]["text"] = "1girl, smile"           # sd.py 가 프롬프트를 먼저 넣은 상태
    wf = gen.apply_lora_patch(wf, LORA, 0.8, positive_node_id="6")
    assert wf["6"]["inputs"]["text"] == f"{TRIGGER}, 1girl, smile"


def test_lr10_mask_i2i_trigger_goes_to_positive_node_18(triggers):
    wf = load(I2I_MASK)
    wf["18"]["inputs"]["text"] = "1girl, smile"
    before6 = wf.get("6", {}).get("inputs", {}).get("text")
    wf = gen.apply_lora_patch(wf, LORA, 0.8, positive_node_id="18")
    assert wf["18"]["inputs"]["text"] == f"{TRIGGER}, 1girl, smile"
    assert wf.get("6", {}).get("inputs", {}).get("text") == before6   # 노드 6은 건드리지 않음
