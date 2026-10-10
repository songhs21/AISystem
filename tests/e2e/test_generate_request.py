"""생성 요청 전송 (TC GN-01·02·06·08·09).

태그 파일, 체크포인트, LoRA 응답은 가짜로 대체하고, 생성 요청(POST /api/sd/queue/t2i)은 가로채 본문을 확인한다
(실제 생성이 시작되지 않게 하기 위해). 큐 개수 확인(GN-08·09)에는 실제 서버(8000)를 쓴다.
GN-08·09 는 결함 후보라 알럿 문구를 바꾸기 전까지 실패한다. GN-09 는 axios 타임아웃(30초)을 기다려 약 30초 걸린다.
"""
import json
import os
import re

from playwright.sync_api import Page, Route, expect

BASE = os.environ.get("AISYSTEM_URL", "http://localhost:5173")
API = os.environ.get("AISYSTEM_API", "http://localhost:8000")
CORS = {"access-control-allow-origin": "*", "access-control-allow-headers": "*",
        "access-control-allow-methods": "*"}
CKPTS = ["modelA.safetensors", "modelB.safetensors"]
NETWORK_ALERT = "네트워크 오류로 생성 요청을 보내지 못했습니다. 연결을 확인한 뒤 다시 시도해 주세요."
TIMEOUT_ALERT = "서버 응답이 없습니다. 대기열을 확인한 뒤 다시 시도해 주세요."


def open_t2i(page: Page):
    def tag_file(route: Route):
        route.fulfill(status=200, headers=CORS, content_type="application/json", body="{}")

    def checkpoints(route: Route):
        route.fulfill(status=200, headers=CORS, content_type="application/json",
                      body=json.dumps({"checkpoints": CKPTS}))

    def loras(route: Route):
        route.fulfill(status=200, headers=CORS, content_type="application/json",
                      body=json.dumps({"loras": ["lora1.safetensors"]}))

    page.route("**/api/system/tags/*", tag_file)
    page.route("**/api/sd/checkpoints", checkpoints)
    page.route("**/api/sd/loras", loras)
    page.goto(BASE)
    expect(page.locator(".app-header")).to_be_visible()
    page.get_by_role("button", name="T2I", exact=True).click()
    expect(search(page)).to_be_visible()


def fake_queue_ok(page: Page):
    """생성 요청에 성공 응답을 돌려준다(서버 큐에 실제로 넣지 않음)."""
    def handler(route: Route):
        if route.request.method == "OPTIONS":
            route.fulfill(status=204, headers=CORS)
            return
        route.fulfill(status=200, headers=CORS, content_type="application/json",
                      body=json.dumps({"id": "test-id"}))

    page.route("**/api/sd/queue/t2i", handler)


def search(page):       return page.get_by_placeholder("🔍 전체 태그 검색...")
def generate_btn(page): return page.get_by_role("button", name=re.compile("이미지 생성"))
def ckpt_select(page):  return page.locator("label:text-is('체크포인트') + select")
def lora_select(page):  return page.locator("select").filter(has=page.locator("option", has_text="LoRA 없음"))
def strength(page):     return page.locator("label:has-text('Strength:') + input[type=range]")


def add_tags(page, text):
    search(page).fill(text)
    search(page).press("Enter")


def is_queue_post(r):
    return r.method == "POST" and r.url.endswith("/api/sd/queue/t2i")


def queue_len(page):
    return len(page.request.get(f"{API}/api/sd/queue").json()["items"])


# GN-01 객체의 영문명을 표시 순서대로 ", " 로 연결해 전송
def test_gn01_prompt_is_objects_joined_in_order(page: Page):
    open_t2i(page)
    fake_queue_ok(page)
    add_tags(page, "alpha, beta, gamma")
    with page.expect_request(is_queue_post) as info:
        generate_btn(page).click()
    assert info.value.post_data_json["prompt"] == "alpha, beta, gamma"


# GN-02 객체 0개: 빈 문자열로 전송되고 요청이 등록된다
def test_gn02_empty_prompt_is_sent(page: Page):
    open_t2i(page)
    fake_queue_ok(page)
    with page.expect_request(is_queue_post) as info:
        generate_btn(page).click()
    assert info.value.post_data_json["prompt"] == ""


# GN-06 체크포인트, LoRA, strength 가 선택값 그대로 전송
def test_gn06_selected_values_are_sent(page: Page):
    open_t2i(page)
    fake_queue_ok(page)
    ckpt_select(page).select_option("modelB.safetensors")
    lora_select(page).select_option("lora1.safetensors")
    strength(page).fill("0.35")
    with page.expect_request(is_queue_post) as info:
        generate_btn(page).click()
    body = info.value.post_data_json
    assert (body["checkpoint"], body["lora_name"], body["lora_strength"]) == (
        "modelB.safetensors", "lora1.safetensors", 0.35)


# GN-08 요청이 서버에 닿지 못함: 알럿만 표시, 새로고침 없음, 큐 개수 변화 없음
def test_gn08_network_failure_shows_alert_only(page: Page):
    open_t2i(page)
    page.route("**/api/sd/queue/t2i", lambda route: route.abort("failed"))
    page.evaluate("window.__alive = true")               # 새로고침되면 사라진다
    before = queue_len(page)
    add_tags(page, "alpha")
    with page.expect_event("dialog") as info:
        generate_btn(page).click()
    dialog = info.value
    message = dialog.message
    dialog.accept()
    assert message == NETWORK_ALERT
    assert page.evaluate("window.__alive") is True, "페이지가 새로고침됨"
    assert queue_len(page) == before, "큐에 항목이 추가됨"


# GN-09 응답이 30초를 넘김: 알럿만 표시, 새로고침 없음 (약 30초 소요)
def test_gn09_timeout_shows_alert_only(page: Page):
    open_t2i(page)

    def hold(route: Route):          # 응답하지 않고 붙잡아 둔다
        pass

    page.route("**/api/sd/queue/t2i", hold)
    page.evaluate("window.__alive = true")
    add_tags(page, "alpha")
    with page.expect_event("dialog", timeout=45000) as info:
        generate_btn(page).click()
    dialog = info.value
    message = dialog.message
    dialog.accept()
    assert message == TIMEOUT_ALERT
    assert page.evaluate("window.__alive") is True, "페이지가 새로고침됨"