"""I2V(영상) 옵션 패널 (TC IV-01~16·30~33·37).

태그·체크포인트·LoRA·업로드·히스토리·이미지 응답은 가짜로 대체하고, 생성 요청(POST /api/sd/queue/i2v)은 가로채
본문을 확인한다(실제 생성이 시작되지 않게 하기 위해). 입력값은 브라우저 저장소(i2vDraft)에 저장되므로
테스트마다 새 브라우저 컨텍스트(저장소 비어 있음)에서 시작한다.
IV-09(업로드 실패 알럿)는 DEF-013 수정 전에는 알럿 없이 처리되지 않은 오류만 남아 실패한다.
"""
import json
import os

import pytest
from PIL import Image
from playwright.sync_api import Page, Route, expect

BASE = os.environ.get("AISYSTEM_URL", "http://localhost:5173")
CORS = {"access-control-allow-origin": "*", "access-control-allow-headers": "*",
        "access-control-allow-methods": "*"}
CKPTS = ["modelA.safetensors", "modelB.safetensors"]
LORA = "lora1.safetensors"
FAKE_PATH = "C:\\fake\\base.png"
LORA_ERROR = "LoRA 목록을 불러오지 못했습니다."
LORA_EMPTY = "설치 폴더/models/LoRAS 에 모델 파일을 옮긴 뒤 다시 시도하세요."
NETWORK_UPLOAD = "네트워크 오류로 이미지를 업로드하지 못했습니다. 연결을 확인한 뒤 다시 시도해 주세요."
PNG_1X1 = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cf000001010100185dd9340000000049454e44ae426082")


def json_reply(route: Route, body, status=200):
    route.fulfill(status=status, headers=CORS, content_type="application/json", body=json.dumps(body))


def make_png(tmp_path, name, size=(64, 48)):
    p = tmp_path / name
    Image.new("RGB", size, (200, 80, 40)).save(p)
    return str(p)


def mock_common(page: Page, loras=(LORA,), lora_status=200):
    page.route("**/api/system/tags/*", lambda r: json_reply(r, {}))
    page.route("**/api/sd/checkpoints", lambda r: json_reply(r, {"checkpoints": CKPTS}))
    page.route("**/api/sd/loras", lambda r: json_reply(r, {"loras": list(loras)}, lora_status))
    page.route("**/api/system/image**", lambda r: r.fulfill(
        status=200, headers=CORS, content_type="image/png", body=PNG_1X1))


def open_video(page: Page, loras=(LORA,), lora_status=200):
    mock_common(page, loras, lora_status)
    page.goto(BASE)
    expect(page.locator(".app-header")).to_be_visible()
    page.get_by_test_id("tab-video").click()
    expect(panel(page)).to_be_visible()


def upload_ok(page: Page, path=FAKE_PATH):
    def handler(route: Route):
        if route.request.method == "OPTIONS":
            route.fulfill(status=204, headers=CORS)
            return
        json_reply(route, {"path": path, "filename": os.path.basename(path.replace("\\", "/"))})
    page.route("**/api/system/upload", handler)


def queue_reply(page: Page, status=200, body=None):
    def handler(route: Route):
        if route.request.method == "OPTIONS":
            route.fulfill(status=204, headers=CORS)
            return
        json_reply(route, body if body is not None else {"id": "test-id"}, status)
    page.route("**/api/sd/queue/i2v", handler)


def panel(page):        return page.get_by_test_id("video-panel")
def generate_btn(page): return page.get_by_test_id("generate-btn")
def base_name(page):    return page.get_by_test_id("video-base-name")
def field(page, key):   return page.get_by_test_id(f"video-{key}")


def is_i2v_post(r):
    return r.method == "POST" and r.url.endswith("/api/sd/queue/i2v")


def set_base(page, tmp_path, file="base.png"):
    upload_ok(page)
    page.get_by_test_id("video-base-file").set_input_files(make_png(tmp_path, file))
    expect(base_name(page)).to_have_text(file)


def take_dialog(page, action):
    box = []

    def on_dialog(dialog):
        box.append(dialog.message)
        dialog.accept()

    page.once("dialog", on_dialog)
    action()
    for _ in range(100):
        if box:
            return box[0]
        page.wait_for_timeout(100)
    raise AssertionError("알럿이 뜨지 않음")


# IV-01 영상 탭: I2V 패널 표시, I2V 선택·T2V 비활성(준비중), 베이스 없으면 생성 버튼 비활성, 이미지 탭으로 돌아가면 패널 사라짐
def test_iv01_video_tab_and_submodes(page: Page):
    open_video(page)
    expect(field(page, "sub-i2v")).to_be_enabled()
    expect(field(page, "sub-t2v")).to_be_disabled()
    expect(field(page, "sub-t2v")).to_contain_text("준비중")
    expect(generate_btn(page)).to_be_disabled()
    expect(generate_btn(page)).to_contain_text("영상 생성")
    page.get_by_test_id("tab-image").click()
    expect(panel(page)).to_have_count(0)


# IV-02 프롬프트·네거티브 입력과 × 초기화
@pytest.mark.parametrize("key", ["prompt", "neg"], ids=["prompt", "negative"])
def test_iv02_textarea_clear_button(page: Page, key):
    open_video(page)
    box = page.get_by_test_id(f"video-{key}-text")
    clear = page.get_by_test_id(f"video-{key}-clear")
    expect(clear).to_have_count(0)
    box.fill("alpha, beta")
    expect(box).to_have_value("alpha, beta")
    clear.click()
    expect(box).to_have_value("")
    expect(clear).to_have_count(0)


# IV-03 LoRA: 기본 없음(Strength 숨김), 선택하면 Strength 0.8, 다시 없음이면 숨김
def test_iv03_lora_select_shows_strength(page: Page):
    open_video(page)
    select = field(page, "lora-select")
    strength = field(page, "lora-strength")
    expect(select).to_have_value("")
    expect(strength).to_have_count(0)
    select.select_option(LORA)
    expect(strength).to_have_value("0.8")
    strength.fill("0.35")
    expect(field(page, "lora-strength-label")).to_have_text("Strength: 0.35")
    select.select_option("")
    expect(strength).to_have_count(0)


# IV-04 LoRA 목록이 비었을 때 / 서버 오류일 때 안내와 다시 시도
def test_iv04_lora_empty_notice(page: Page):
    open_video(page, loras=())
    status = field(page, "lora-status")
    expect(status).to_contain_text(LORA_EMPTY)
    expect(status.get_by_role("button")).to_have_text("다시 시도")


def test_iv04_lora_error_notice(page: Page):
    open_video(page, lora_status=500)
    status = field(page, "lora-status")
    expect(status).to_contain_text(LORA_ERROR, timeout=15000)
    expect(status.get_by_role("button")).to_have_text("다시 시도")


# IV-05 베이스 업로드: 파일명·썸네일, 생성 버튼 활성
def test_iv05_base_upload(page: Page, tmp_path):
    open_video(page)
    set_base(page, tmp_path)
    expect(page.get_by_test_id("video-base-img")).to_be_visible()
    expect(generate_btn(page)).to_be_enabled()
    expect(page.get_by_test_id("video-base-file")).to_have_count(0)


# IV-06 히스토리에서 선택: 이미지만 표시(영상 제외), 선택하면 파일명 표시 + 창 닫힘
def test_iv06_base_from_history(page: Page):
    gens = [{"id": 1, "image_path": "C:\\out\\a.png", "media_type": "image"},
            {"id": 2, "image_path": "C:\\out\\b.png", "media_type": "image"},
            {"id": 3, "image_path": "C:\\out\\c.mp4", "media_type": "video"}]
    page.route("**/api/history/generations", lambda r: json_reply(r, {"generations": gens}))
    open_video(page)
    page.get_by_test_id("video-base-history").click()
    expect(page.get_by_test_id("history-picker")).to_be_visible()
    expect(page.get_by_test_id("history-item")).to_have_count(2)
    page.get_by_test_id("history-item").first.click()
    expect(base_name(page)).to_have_text("a.png")
    expect(page.get_by_test_id("history-picker")).to_have_count(0)
    expect(generate_btn(page)).to_be_enabled()


# IV-07 베이스 삭제: 슬롯이 비고 생성 버튼 비활성
def test_iv07_remove_base(page: Page, tmp_path):
    open_video(page)
    set_base(page, tmp_path)
    page.get_by_test_id("video-base-remove").click()
    expect(base_name(page)).to_have_count(0)
    expect(generate_btn(page)).to_be_disabled()


# IV-08 썸네일 확대 오버레이 열기·닫기
def test_iv08_thumbnail_preview(page: Page, tmp_path):
    open_video(page)
    set_base(page, tmp_path)
    page.get_by_test_id("video-base-img").click()
    expect(page.get_by_test_id("image-overlay")).to_be_visible()
    page.get_by_test_id("image-overlay").click()
    expect(page.get_by_test_id("image-overlay")).to_have_count(0)


# IV-09 업로드 실패: (a) 서버 사유 그대로, (b) 사유 없는 서버 오류, (c) 연결 실패. 슬롯은 비어 있어야 한다 (DEF-013)
@pytest.mark.parametrize("mode, expected", [
    ("reject",  "이미지 파일만 업로드 가능합니다"),
    ("500",     "이미지를 업로드하지 못했습니다. (서버 응답 500)"),
    ("network", NETWORK_UPLOAD),
], ids=["IV-09a", "IV-09b", "IV-09c"])
def test_iv09_upload_failure_alert(page: Page, tmp_path, mode, expected):
    open_video(page)

    def handler(route: Route):
        if route.request.method == "OPTIONS":
            route.fulfill(status=204, headers=CORS)
        elif mode == "reject":
            json_reply(route, {"detail": "이미지 파일만 업로드 가능합니다"}, 400)
        elif mode == "500":
            route.fulfill(status=500, headers=CORS, content_type="text/plain", body="boom")
        else:
            route.abort("failed")

    page.route("**/api/system/upload", handler)
    png = make_png(tmp_path, "base.png")
    message = take_dialog(page, lambda: page.get_by_test_id("video-base-file").set_input_files(png))
    assert message == expected
    expect(base_name(page)).to_have_count(0)
    expect(generate_btn(page)).to_be_disabled()


# IV-10 초기 입력값: Width 832, Height 480(480p), Frames 81, Seed -1, High 2, Low 3, CFG 1
def test_iv10_initial_values(page: Page):
    open_video(page)
    expected = {"width": "832", "height": "480", "length": "81", "seed": "-1",
                "high-steps": "2", "low-steps": "3", "cfg": "1"}
    for key, value in expected.items():
        expect(field(page, key)).to_have_value(value)
    expect(field(page, "cfg-label")).to_have_text("CFG: 1")


# IV-11 CFG 슬라이더: 범위 1~10, 단계 0.5, 값이 라벨에 반영
def test_iv11_cfg_slider(page: Page):
    open_video(page)
    cfg = field(page, "cfg")
    expect(cfg).to_have_attribute("min", "1")
    expect(cfg).to_have_attribute("max", "10")
    expect(cfg).to_have_attribute("step", "0.5")
    cfg.fill("2.5")
    expect(field(page, "cfg-label")).to_have_text("CFG: 2.5")


def fill_all(page):
    page.get_by_test_id("video-prompt-text").fill("alpha")
    page.get_by_test_id("video-neg-text").fill("bad")
    field(page, "seed").fill("123")
    field(page, "width").fill("1024")
    field(page, "height").fill("576")
    field(page, "length").fill("49")
    field(page, "high-steps").fill("4")
    field(page, "low-steps").fill("6")
    field(page, "cfg").fill("2.5")
    field(page, "lora-select").select_option(LORA)
    field(page, "lora-strength").fill("0.45")


def check_all(page):
    expect(page.get_by_test_id("video-prompt-text")).to_have_value("alpha")
    expect(page.get_by_test_id("video-neg-text")).to_have_value("bad")
    for key, value in {"seed": "123", "width": "1024", "height": "576", "length": "49",
                       "high-steps": "4", "low-steps": "6", "cfg": "2.5"}.items():
        expect(field(page, key)).to_have_value(value)
    expect(field(page, "lora-select")).to_have_value(LORA)
    expect(field(page, "lora-strength")).to_have_value("0.45")


# IV-12 입력값 저장·복원: 새로고침 후 영상 탭을 다시 열면 베이스 이미지와 모든 입력값이 그대로
def test_iv12_inputs_restored_after_reload(page: Page, tmp_path):
    open_video(page)
    set_base(page, tmp_path)
    fill_all(page)
    page.reload()
    expect(page.locator(".app-header")).to_be_visible()
    page.get_by_test_id("tab-video").click()
    expect(panel(page)).to_be_visible()
    expect(base_name(page)).to_have_text("base.png")
    expect(generate_btn(page)).to_be_enabled()
    check_all(page)


# IV-13 이미지 탭에 갔다 와도 입력값 유지
def test_iv13_inputs_kept_after_tab_switch(page: Page, tmp_path):
    open_video(page)
    set_base(page, tmp_path)
    fill_all(page)
    page.get_by_test_id("tab-image").click()
    expect(panel(page)).to_have_count(0)
    page.get_by_test_id("tab-video").click()
    expect(base_name(page)).to_have_text("base.png")
    check_all(page)


# IV-14 생성 요청 본문: 입력값 그대로. frame_rate 는 보내지 않음(서버 기본값 10)
def test_iv14_request_body(page: Page, tmp_path):
    open_video(page)
    set_base(page, tmp_path)
    fill_all(page)
    queue_reply(page)
    with page.expect_request(is_i2v_post) as info:
        generate_btn(page).click()
    assert info.value.post_data_json == {
        "image_path": FAKE_PATH, "prompt": "alpha", "negative": "bad", "seed": 123,
        "width": 1024, "height": 576, "length": 49, "high_steps": 4, "low_steps": 6, "cfg": 2.5,
        "lora_name": LORA, "lora_strength": 0.45}


# IV-15 서버가 요청을 거부하면(422) 사유를 알럿으로 보여준다
def test_iv15_server_rejection_is_shown(page: Page, tmp_path):
    open_video(page)
    set_base(page, tmp_path)
    queue_reply(page, 422, {"detail": "이미지 파일을 찾을 수 없습니다: C:\\fake\\base.png"})
    message = take_dialog(page, lambda: generate_btn(page).click())
    assert message == "이미지 파일을 찾을 수 없습니다: C:\\fake\\base.png"


# IV-16 생성 요청 성공 후에도 입력값과 베이스 이미지는 유지된다(연속 생성)
def test_iv16_inputs_kept_after_enqueue(page: Page, tmp_path):
    open_video(page)
    set_base(page, tmp_path)
    fill_all(page)
    queue_reply(page)
    with page.expect_request(is_i2v_post):
        generate_btn(page).click()
    expect(base_name(page)).to_have_text("base.png")
    check_all(page)


# ── 입력 최소값 (사용자 결정 2026-10-10): Width 832, Height 480, Frames 10, Steps 각 2.
# 입력 중에는 값을 비울 수 있고, 포커스가 빠지면 비었거나 최소 미만인 값을 최소값으로 되돌린다. 알럿은 없다.
MINIMUMS = {"width": "832", "height": "480", "length": "10", "high-steps": "2", "low-steps": "2", "seed": "-1"}


# IV-30 해상도: 최소 미만이면 최소값으로, 최소 이상이면 그대로 (IVD-13~16)
@pytest.mark.parametrize("key, below, ok", [
    ("width", "831", "900"), ("width", "0", "832"), ("height", "479", "600"), ("height", "-5", "480"),
], ids=["IV-30a", "IV-30b", "IV-30c", "IV-30d"])
def test_iv30_size_below_minimum_restored(page: Page, key, below, ok):
    open_video(page)
    field(page, key).fill(below)
    field(page, key).blur()
    expect(field(page, key)).to_have_value(MINIMUMS[key])
    field(page, key).fill(ok)
    field(page, key).blur()
    expect(field(page, key)).to_have_value(ok)


# IV-31 Frames: 10 미만이면 10으로, 10 이상이면 그대로
@pytest.mark.parametrize("below, ok", [("9", "10"), ("0", "49")], ids=["IV-31a", "IV-31b"])
def test_iv31_frames_below_minimum_restored(page: Page, below, ok):
    open_video(page)
    field(page, "length").fill(below)
    field(page, "length").blur()
    expect(field(page, "length")).to_have_value("10")
    field(page, "length").fill(ok)
    field(page, "length").blur()
    expect(field(page, "length")).to_have_value(ok)


# IV-32 Steps: High·Low 각각 2 미만이면 2로, 2 이상이면 그대로
@pytest.mark.parametrize("key", ["high-steps", "low-steps"], ids=["high", "low"])
def test_iv32_steps_below_minimum_restored(page: Page, key):
    open_video(page)
    field(page, key).fill("1")
    field(page, key).blur()
    expect(field(page, key)).to_have_value("2")
    field(page, key).fill("8")
    field(page, key).blur()
    expect(field(page, key)).to_have_value("8")


# IV-33 입력란 비우기: 포커스 중에는 비어 있을 수 있고, 포커스가 빠지면 최소값(Seed 는 -1)으로 채워진다
@pytest.mark.parametrize("key", list(MINIMUMS), ids=list(MINIMUMS))
def test_iv33_empty_input_filled_with_minimum_on_blur(page: Page, key):
    open_video(page)
    field(page, key).fill("")
    expect(field(page, key)).to_have_value("")
    expect(field(page, key)).to_be_focused()
    field(page, key).blur()
    expect(field(page, key)).to_have_value(MINIMUMS[key])


# IV-37 최소 미만으로 입력한 채 바로 생성 버튼을 눌러도 보정된 값이 전송된다
def test_iv37_corrected_values_are_sent(page: Page, tmp_path):
    open_video(page)
    set_base(page, tmp_path)
    field(page, "width").fill("700")
    field(page, "height").fill("400")
    field(page, "length").fill("5")
    field(page, "high-steps").fill("1")
    field(page, "low-steps").fill("")
    queue_reply(page)
    with page.expect_request(is_i2v_post) as info:
        generate_btn(page).click()
    body = info.value.post_data_json
    assert (body["width"], body["height"], body["length"], body["high_steps"], body["low_steps"]) == (832, 480, 10, 2, 2)
