"""I2I 옵션 패널 (TC IP-01~18).

태그·체크포인트·LoRA·업로드·히스토리 응답은 가짜로 대체하고, 생성 요청(POST /api/sd/queue/i2i)은 가로채
본문을 확인한다(실제 생성이 시작되지 않게 하기 위해). 마스크 드로잉은 그리지 않고 '완료'만 눌러 빈 마스크를 만든다
(마스크 그림 내용은 검증 대상이 아니라 슬롯 상태와 전송 여부를 본다).
IP-08(베이스 삭제 시 마스크 삭제)은 결함 DEF-010, IP-13b/c(업로드 실패 문구)는 DEF-011 수정 전까지 실패한다.
"""
import json
import os
import re

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


def json_reply(route: Route, body, status=200):
    route.fulfill(status=status, headers=CORS, content_type="application/json", body=json.dumps(body))


def make_png(tmp_path, name, size=(64, 48)):
    p = tmp_path / name
    Image.new("RGB", size, (200, 80, 40)).save(p)
    return str(p)


def open_i2i(page: Page, loras=(LORA,), lora_status=200):
    page.route("**/api/system/tags/*", lambda r: json_reply(r, {}))
    page.route("**/api/sd/checkpoints", lambda r: json_reply(r, {"checkpoints": CKPTS}))
    page.route("**/api/sd/loras", lambda r: json_reply(r, {"loras": list(loras)}, lora_status))
    page.goto(BASE)
    expect(page.locator(".app-header")).to_be_visible()
    page.get_by_test_id("mode-I2I").click()
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
    page.route("**/api/sd/queue/i2i", handler)


def panel(page):        return page.get_by_test_id("i2i-panel")
def generate_btn(page): return page.get_by_test_id("generate-btn")
def slot(page, key):    return page.get_by_test_id(f"i2i-{key}")
def name(page, key):    return page.get_by_test_id(f"i2i-{key}-name")


def is_i2i_post(r):
    return r.method == "POST" and r.url.endswith("/api/sd/queue/i2i")


def set_base(page, tmp_path, file="base.png"):
    upload_ok(page)
    page.get_by_test_id("i2i-base-file").set_input_files(make_png(tmp_path, file))
    expect(name(page, "base")).to_have_text(file)


def draw_mask(page):
    page.get_by_test_id("i2i-mask-draw").click()
    expect(page.get_by_test_id("mask-overlay")).to_be_visible()
    page.get_by_test_id("mask-done").click()
    expect(page.get_by_test_id("mask-overlay")).to_have_count(0)


def form_parts(req):
    """multipart 본문을 {필드명: (머리말, 값 bytes)} 로 푼다."""
    boundary = req.headers["content-type"].split("boundary=")[1].encode()
    parts = {}
    for chunk in req.post_data_buffer.split(b"--" + boundary):
        if b"Content-Disposition" not in chunk:
            continue
        head, _, body = chunk.partition(b"\r\n\r\n")
        key = re.search(rb'name="([^"]+)"', head).group(1).decode()
        parts[key] = (head.decode(errors="replace"), body[:-2] if body.endswith(b"\r\n") else body)
    return parts


def text(parts, key):
    return parts[key][1].decode()


def take_dialog(page, action):
    """알럿 문구를 돌려준다. 클릭 처리 중에 알럿이 뜨는 경우(동기 alert)에도 막히지 않도록 핸들러로 받는다."""
    box = []

    def on_dialog(dialog):
        box.append(dialog.message)
        dialog.accept()

    page.once("dialog", on_dialog)
    action()
    for _ in range(100):                      # 알럿이 뜰 때까지 최대 10초
        if box:
            return box[0]
        page.wait_for_timeout(100)
    raise AssertionError("알럿이 뜨지 않음")


# IP-01 I2I 모드: 패널이 보이고 T2I 로 돌아가면 사라진다. 베이스가 없으면 생성 버튼 비활성
def test_ip01_mode_switch_and_generate_disabled(page: Page):
    open_i2i(page)
    expect(generate_btn(page)).to_be_disabled()
    expect(name(page, "base")).to_have_count(0)
    page.get_by_test_id("mode-T2I").click()
    expect(panel(page)).to_have_count(0)
    page.get_by_test_id("mode-I2I").click()
    expect(panel(page)).to_be_visible()


# IP-02 프롬프트·네거티브 입력과 × 초기화 (내용이 있을 때만 × 표시)
@pytest.mark.parametrize("key", ["prompt", "neg"], ids=["prompt", "negative"])
def test_ip02_textarea_clear_button(page: Page, key):
    open_i2i(page)
    box = page.get_by_test_id(f"i2i-{key}-text")
    clear = page.get_by_test_id(f"i2i-{key}-clear")
    expect(clear).to_have_count(0)
    box.fill("alpha, beta")
    expect(box).to_have_value("alpha, beta")
    clear.click()
    expect(box).to_have_value("")
    expect(clear).to_have_count(0)


# IP-03 Denoise: 기본 0.7, 범위 0.1~1, 단계 0.05, 값이 라벨에 반영
def test_ip03_denoise_slider(page: Page):
    open_i2i(page)
    d = page.get_by_test_id("i2i-denoise")
    expect(d).to_have_value("0.7")
    expect(d).to_have_attribute("min", "0.1")
    expect(d).to_have_attribute("max", "1")
    expect(d).to_have_attribute("step", "0.05")
    expect(page.get_by_test_id("i2i-denoise-label")).to_contain_text("Denoise: 0.7")
    d.fill("0.35")
    expect(page.get_by_test_id("i2i-denoise-label")).to_contain_text("Denoise: 0.35")


# IP-04 LoRA: 기본 없음(Strength 숨김), 선택하면 Strength 0.8 표시, 다시 없음으로 돌리면 숨김
def test_ip04_lora_select_shows_strength(page: Page):
    open_i2i(page)
    select = page.get_by_test_id("i2i-lora-select")
    strength = page.get_by_test_id("i2i-lora-strength")
    expect(select).to_have_value("")
    expect(strength).to_have_count(0)
    select.select_option(LORA)
    expect(strength).to_have_value("0.8")
    strength.fill("0.35")
    expect(page.get_by_test_id("i2i-lora-strength-label")).to_have_text("Strength: 0.35")
    select.select_option("")
    expect(strength).to_have_count(0)


# IP-05 LoRA 목록이 비었을 때 / 서버 오류일 때 안내와 다시 시도 버튼
def test_ip05_lora_empty_notice(page: Page):
    open_i2i(page, loras=())
    status = page.get_by_test_id("i2i-lora-status")
    expect(status).to_contain_text(LORA_EMPTY)
    expect(status.get_by_role("button")).to_have_text("다시 시도")


def test_ip05_lora_error_notice(page: Page):
    open_i2i(page, lora_status=500)
    status = page.get_by_test_id("i2i-lora-status")
    expect(status).to_contain_text(LORA_ERROR, timeout=15000)   # react-query 재시도 3회(1+2+4초) 후 오류 상태
    expect(status.get_by_role("button")).to_have_text("다시 시도")


# IP-06 베이스 업로드: 파일명·썸네일 표시, 생성 버튼 활성
def test_ip06_base_upload(page: Page, tmp_path):
    open_i2i(page)
    set_base(page, tmp_path)
    expect(page.get_by_test_id("i2i-base-img")).to_be_visible()
    expect(generate_btn(page)).to_be_enabled()
    expect(page.get_by_test_id("i2i-base-file")).to_have_count(0)    # 채워진 슬롯에는 업로드 버튼이 없다


# IP-07 베이스를 히스토리에서 선택: 이미지 목록이 뜨고, 고르면 파일명 표시 + 피커 닫힘
def test_ip07_base_from_history(page: Page):
    gens = [{"id": 1, "image_path": "C:\\out\\a.png", "media_type": "image"},
            {"id": 2, "image_path": "C:\\out\\b.png", "media_type": "image"},
            {"id": 3, "image_path": "C:\\out\\c.mp4", "media_type": "video"}]
    page.route("**/api/history/generations", lambda r: json_reply(r, {"generations": gens}))
    page.route("**/api/system/image**", lambda r: r.fulfill(status=200, headers=CORS, content_type="image/png",
               body=bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cf000001010100185dd9340000000049454e44ae426082")))
    open_i2i(page)                                                    # 히스토리 응답은 페이지를 열기 전에 가짜로 바꿔 둔다
    page.get_by_test_id("i2i-base-history").click()
    expect(page.get_by_test_id("history-picker")).to_be_visible()
    expect(page.get_by_test_id("history-item")).to_have_count(2)      # 영상은 제외
    page.get_by_test_id("history-item").first.click()
    expect(name(page, "base")).to_have_text("a.png")
    expect(page.get_by_test_id("history-picker")).to_have_count(0)
    expect(generate_btn(page)).to_be_enabled()


# IP-08 베이스를 지우면 슬롯이 비고 생성 버튼이 꺼지며, 마스크도 함께 지워진다 (DEF-010)
def test_ip08_removing_base_also_removes_mask(page: Page, tmp_path):
    open_i2i(page)
    set_base(page, tmp_path)
    draw_mask(page)
    expect(name(page, "mask")).to_have_text("마스크")
    page.get_by_test_id("i2i-base-remove").click()
    expect(name(page, "base")).to_have_count(0)
    expect(name(page, "mask")).to_have_count(0)
    expect(generate_btn(page)).to_be_disabled()


# IP-09 베이스 없이 마스크 그리기: 안내 알럿만 뜨고 오버레이는 열리지 않는다
def test_ip09_mask_draw_requires_base(page: Page):
    open_i2i(page)
    message = take_dialog(page, lambda: page.get_by_test_id("i2i-mask-draw").click())
    assert message == "베이스 이미지를 먼저 선택해주세요"
    expect(page.get_by_test_id("mask-overlay")).to_have_count(0)


# IP-10 마스크: 열었다 닫으면 슬롯은 비어 있고, 완료하면 슬롯에 '마스크'가 표시되며, ×로 지울 수 있다
def test_ip10_mask_draw_done_remove(page: Page, tmp_path):
    open_i2i(page)
    set_base(page, tmp_path)
    page.get_by_test_id("i2i-mask-draw").click()
    expect(page.get_by_test_id("mask-overlay")).to_be_visible()
    page.get_by_test_id("mask-close").click()
    expect(page.get_by_test_id("mask-overlay")).to_have_count(0)
    expect(name(page, "mask")).to_have_count(0)
    draw_mask(page)
    expect(name(page, "mask")).to_have_text("마스크")
    expect(page.get_by_test_id("i2i-mask-img")).to_be_visible()
    page.get_by_test_id("i2i-mask-remove").click()
    expect(name(page, "mask")).to_have_count(0)
    expect(name(page, "base")).to_have_text("base.png")              # 마스크만 지워지고 베이스는 남는다


# IP-11 레퍼런스: 업로드하면 파일명 표시, ×로 삭제
def test_ip11_reference_upload_and_remove(page: Page, tmp_path):
    open_i2i(page)
    upload_ok(page, "C:\\fake\\ref.png")
    page.get_by_test_id("i2i-ref-file").set_input_files(make_png(tmp_path, "ref.png"))
    expect(name(page, "ref")).to_have_text("ref.png")
    page.get_by_test_id("i2i-ref-remove").click()
    expect(name(page, "ref")).to_have_count(0)


# IP-12 썸네일을 누르면 확대 오버레이, 오버레이를 누르면 닫힘
def test_ip12_thumbnail_preview(page: Page, tmp_path):
    open_i2i(page)
    set_base(page, tmp_path)
    page.get_by_test_id("i2i-base-img").click()
    expect(page.get_by_test_id("image-overlay")).to_be_visible()
    page.get_by_test_id("image-overlay").click()
    expect(page.get_by_test_id("image-overlay")).to_have_count(0)


# IP-13 업로드 실패: (a) 서버가 사유를 준 경우 그대로, (b) 서버 오류 사유 없음, (c) 연결 실패. 슬롯은 비어 있어야 한다 (DEF-011)
@pytest.mark.parametrize("mode, expected", [
    ("reject",  "이미지 파일만 업로드 가능합니다"),
    ("500",     "이미지를 업로드하지 못했습니다. (서버 응답 500)"),
    ("network", NETWORK_UPLOAD),
], ids=["IP-13a", "IP-13b", "IP-13c"])
def test_ip13_upload_failure_alert(page: Page, tmp_path, mode, expected):
    open_i2i(page)

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
    message = take_dialog(page, lambda: page.get_by_test_id("i2i-base-file").set_input_files(png))
    assert message == expected
    expect(name(page, "base")).to_have_count(0)
    expect(generate_btn(page)).to_be_disabled()


# IP-14 생성 요청 본문: 입력한 값이 그대로, seed 는 -1, 마스크 없으면 mask_file 없음, 레퍼런스는 전송하지 않음 (Q-09)
def test_ip14_request_fields(page: Page, tmp_path):
    open_i2i(page)
    set_base(page, tmp_path)
    upload_ok(page, "C:\\fake\\ref.png")
    page.get_by_test_id("i2i-ref-file").set_input_files(make_png(tmp_path, "ref.png"))
    expect(name(page, "ref")).to_have_text("ref.png")
    upload_ok(page)                                                  # 이후 다른 업로드는 없다
    page.get_by_test_id("ckpt-select").select_option("modelB.safetensors")
    page.get_by_test_id("i2i-prompt-text").fill("alpha, beta")
    page.get_by_test_id("i2i-neg-text").fill("bad")
    page.get_by_test_id("i2i-denoise").fill("0.35")
    page.get_by_test_id("i2i-lora-select").select_option(LORA)
    page.get_by_test_id("i2i-lora-strength").fill("0.45")
    queue_reply(page)
    with page.expect_request(is_i2i_post) as info:
        generate_btn(page).click()
    parts = form_parts(info.value)
    assert {k: text(parts, k) for k in parts if k != "mask_file"} == {
        "image_path": FAKE_PATH, "checkpoint": "modelB.safetensors", "prompt": "alpha, beta",
        "negative": "bad", "denoise": "0.35", "seed": "-1",
        "lora_name": LORA, "lora_strength": "0.45"}
    assert "mask_file" not in parts


# IP-15 마스크를 만들었으면 mask_file(PNG, 파일명 mask.png)이 함께 전송된다
def test_ip15_request_includes_mask_file(page: Page, tmp_path):
    open_i2i(page)
    set_base(page, tmp_path)
    draw_mask(page)
    queue_reply(page)
    with page.expect_request(is_i2i_post) as info:
        generate_btn(page).click()
    head, body = form_parts(info.value)["mask_file"]
    assert 'filename="mask.png"' in head
    assert body.startswith(b"\x89PNG")


# IP-16 서버가 요청을 거부하면(422) 사유를 알럿으로 보여준다
def test_ip16_server_rejection_is_shown(page: Page, tmp_path):
    open_i2i(page)
    set_base(page, tmp_path)
    queue_reply(page, 422, {"detail": "체크포인트를 선택해 주세요."})
    message = take_dialog(page, lambda: generate_btn(page).click())
    assert message == "체크포인트를 선택해 주세요."
