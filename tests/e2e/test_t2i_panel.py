import json
import os
import re

import pytest
from playwright.sync_api import Page, Route, expect

BASE = os.environ.get("AISYSTEM_URL", "http://localhost:5173")
CKPTS = ["modelA.safetensors", "modelB.safetensors"]
CORS = {"access-control-allow-origin": "*"}  # 5173 → 8000 교차 출처 호출이라 필요
EMPTY_TEXT = "체크포인트가 없습니다. 설치 폴더/models/checkpoints 에 모델 파일을 옮긴 뒤 다시 시도하세요."
ERROR_TEXT = "체크포인트 목록을 불러오지 못했습니다."


def mock_api(page: Page, *responses, held=None):
    """체크포인트 API를 호출 순서대로 응답한다. 응답 = (상태코드, 목록, 지연ms 또는 "hold").
    "hold"면 요청을 붙잡아 held 리스트에 넣어 두고, 테스트가 나중에 route.fulfill로 응답한다.
    마지막 응답은 이후 호출에도 반복한다."""
    calls = []

    def reply(route: Route, status, items):
        route.fulfill(status=status, headers=CORS, content_type="application/json",
                      body=json.dumps({"checkpoints": items}))

    def checkpoints(route: Route):
        status, items, delay = responses[min(len(calls), len(responses) - 1)]
        calls.append(route.request.url)
        if delay == "hold":
            held.append((route, status, items))
            return
        if delay:
            page.wait_for_timeout(delay)
        reply(route, status, items)

    def loras(route: Route):
        route.fulfill(status=200, headers=CORS, content_type="application/json",
                      body=json.dumps({"loras": ["lora1.safetensors"]}))

    page.route("**/api/sd/checkpoints", checkpoints)
    page.route("**/api/sd/loras", loras)
    return calls


def open_app(page: Page, *responses, stored=None, held=None):
    calls = mock_api(page, *(responses or [(200, CKPTS, 0)]), held=held)
    if stored is not None:  # 저장된 체크포인트 값을 미리 심어 둔다
        page.add_init_script(
            f"localStorage.setItem('checkpoint', {json.dumps(json.dumps(stored))})")
    page.goto(BASE)
    expect(page.locator(".app-header")).to_be_visible()
    return calls


def toggle_open(page):  return page.get_by_role("button", name="옵션 ▶", exact=True)
def toggle_close(page): return page.get_by_role("button", name="◀ 접기", exact=True)
def img_tab(page):      return page.get_by_role("button", name=re.compile(r"^.{1,3}\s이미지$"))
def video_tab(page):    return page.get_by_role("button", name=re.compile(r"^.{1,3}\s영상$"))
def mode_btn(page, label): return page.get_by_role("button", name=label, exact=True)
def ckpt_select(page):  return page.locator("label:text-is('체크포인트') + select")
def ckpt_notice(page):  return ckpt_select(page).locator("xpath=following-sibling::div[1]")
def retry_btn(page):    return ckpt_notice(page).get_by_role("button")


# ── 패널 (스모크) ─────────────────────────────────────────

@pytest.mark.smoke
def test_pn01_open_button_opens_panel(page: Page):
    open_app(page)
    toggle_close(page).click()
    expect(img_tab(page)).to_be_hidden()
    toggle_open(page).click()
    expect(img_tab(page)).to_be_visible()


@pytest.mark.smoke
def test_pn02_close_button_closes_panel(page: Page):
    open_app(page)
    expect(img_tab(page)).to_be_visible()
    toggle_close(page).click()
    expect(img_tab(page)).to_be_hidden()


@pytest.mark.smoke
def test_pn03_image_button_shows_image_menu(page: Page):
    open_app(page)
    video_tab(page).click()
    expect(mode_btn(page, "T2I")).to_be_hidden()
    img_tab(page).click()
    expect(mode_btn(page, "T2I")).to_be_visible()
    expect(mode_btn(page, "I2I")).to_be_visible()


@pytest.mark.smoke
def test_pn04_t2i_button_shows_t2i_menu(page: Page):
    open_app(page)
    mode_btn(page, "I2I").click()
    mode_btn(page, "T2I").click()
    expect(page.get_by_placeholder("🔍 전체 태그 검색...")).to_be_visible()
    expect(page.get_by_text("❌ 부정 프롬프트")).to_be_visible()


@pytest.mark.smoke
def test_pn05_i2i_button_shows_i2i_menu(page: Page):
    open_app(page)
    mode_btn(page, "I2I").click()
    expect(page.get_by_text("이미지 슬롯")).to_be_visible()
    expect(page.get_by_text(re.compile("Denoise"))).to_be_visible()


@pytest.mark.smoke
def test_pn06_video_button_shows_video_menu(page: Page):
    open_app(page)
    video_tab(page).click()
    expect(page.get_by_text(re.compile("High Steps"))).to_be_visible()
    expect(ckpt_select(page)).to_have_count(0)  # 영상 모드는 체크포인트 선택이 없음


# ── 체크포인트 (UI) ───────────────────────────────────────

def test_ck01_dropdown_lists_registered_models(page: Page):
    open_app(page)
    expect(ckpt_select(page).locator("option")).to_have_text(CKPTS)


def test_ck02_selecting_model_changes_value(page: Page):
    open_app(page)
    ckpt_select(page).select_option("modelB.safetensors")
    expect(ckpt_select(page)).to_have_value("modelB.safetensors")


def test_ck03_empty_list_shows_notice_and_retry(page: Page):
    open_app(page, (200, [], 0))
    expect(ckpt_notice(page)).to_contain_text(EMPTY_TEXT)
    expect(retry_btn(page)).to_have_text("다시 시도")


def test_ck04_server_failure_shows_notice_and_retry(page: Page):
    open_app(page, (500, [], 0))
    # react-query 기본 재시도(3회, 1+2+4초) 후 오류 상태가 되므로 넉넉히 기다린다
    expect(ckpt_notice(page)).to_contain_text(ERROR_TEXT, timeout=15000)
    expect(retry_btn(page)).to_have_text("다시 시도")


@pytest.mark.parametrize("stored", [None, "gone.safetensors"], ids=["no-saved", "saved-but-missing"])
def test_ck05_first_model_selected(page: Page, stored):
    open_app(page, stored=stored)
    expect(ckpt_select(page)).to_have_value(CKPTS[0])


def test_ck06_retry_requests_again_without_reload(page: Page):
    held = []
    # 첫 호출은 빈 목록, 두 번째 호출은 테스트가 풀어 줄 때까지 붙잡아 둔다
    calls = open_app(page, (200, [], 0), (200, CKPTS, "hold"), held=held)
    expect(retry_btn(page)).to_be_enabled()
    page.evaluate("window.__marker = 1")

    retry_btn(page).click()
    for _ in range(50):                      # 요청이 서버에 도착할 때까지 최대 5초
        if held:
            break
        page.wait_for_timeout(100)
    assert len(held) == 1, "다시 시도를 눌러도 요청이 가지 않음"

    # 요청이 대기 중인 동안의 화면 (실패 시 이 출력이 원인 판단에 쓰임)
    print("대기 중 영역 텍스트:", repr(ckpt_select(page).locator("xpath=..").inner_text()))
    print("대기 중 안내 개수:", ckpt_notice(page).count())
    expect(retry_btn(page)).to_be_disabled()   # TC: 요청 중에는 버튼이 비활성

    try:
        expect(retry_btn(page)).to_be_disabled()   # TC: 요청 중에는 버튼이 비활성
    finally:
        route, status, items = held[0]             # 실패해도 붙잡아 둔 요청은 항상 풀어 준다
        route.fulfill(status=status, headers=CORS, content_type="application/json",
                      body=json.dumps({"checkpoints": items}))

    expect(ckpt_select(page).locator("option")).to_have_text(CKPTS)
    assert len(calls) == 2
    assert page.evaluate("window.__marker") == 1  # 페이지 새로고침 없음