"""생성 탭 태그(피드백) 패널 (TC FB-01~12).

대기열(GET /api/sd/queue)에 완료된 T2I 항목을 두고, 카드를 눌러 결과를 연다. 히스토리 조회·태그 가중치·이미지는
가짜 응답이고, 피드백 저장(POST /api/history/feedback)은 가로채 본문을 확인한다.
첫 로드 때 이미 끝나 있던 항목은 자동으로 열리지 않으므로 항상 카드를 눌러 연다.
결함: DEF-015(마음에 들지 않음인데 태그·점수 저장). FB-05 는 수정 전에는 실패한다.
"""
import json
import os
import re
import time

import pytest
from playwright.sync_api import Page, Route, expect

BASE = os.environ.get("AISYSTEM_URL", "http://localhost:5173")
CORS = {"access-control-allow-origin": "*", "access-control-allow-headers": "*",
        "access-control-allow-methods": "*"}
PNG_1X1 = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cf000001010100185dd9340000000049454e44ae426082")
TAGS = [{"tag": "1girl", "category": "quality"}, {"tag": "smile", "category": "emotion"},
        {"tag": "red_hair", "category": "hair_color"}]
ITEM_A, ITEM_B = "qa", "qb"
GEN = {ITEM_A: 11, ITEM_B: 12}
STANDARD = ["문제 없음", "그림체", "인체 디테일", "마음에 들지 않음"]


def json_reply(route: Route, body, status=200):
    route.fulfill(status=status, headers=CORS, content_type="application/json", body=json.dumps(body))


def done_item(item_id):
    return {"id": item_id, "kind": "t2i", "status": "done", "progress": 1.0, "error": None,
            "summary": {"mode": "t2i", "checkpoint": "modelA.safetensors", "prompt": "1girl, smile",
                        "negative": "", "lora": None},
            "result": {"gen_id": GEN[item_id], "image_path": f"C:\\fake\\{item_id}.png"},
            "created_at": time.time()}


def mock_all(page: Page, ids=(ITEM_A,)):
    page.route("**/api/system/tags/*", lambda r: json_reply(r, {}))
    page.route("**/api/sd/checkpoints", lambda r: json_reply(r, {"checkpoints": ["modelA.safetensors"]}))
    page.route("**/api/sd/loras", lambda r: json_reply(r, {"loras": []}))
    page.route("**/api/system/image**", lambda r: r.fulfill(
        status=200, headers=CORS, content_type="image/png", body=PNG_1X1))
    page.route("**/api/history/all-tag-weights", lambda r: json_reply(r, {}))
    page.route("**/api/history/tag-weights", lambda r: json_reply(r, {}))
    page.route("**/api/history/generations/*", lambda r: json_reply(
        r, {"prompt": "1girl, smile, red_hair", "tags": TAGS}))

    def queue(route: Route):
        if route.request.method != "GET":
            route.continue_()
            return
        json_reply(route, {"items": [done_item(i) for i in ids],
                           "shutdown": {"armed": False, "remaining": 0, "extracting": False}})
    page.route("**/api/sd/queue", queue)


def feedback_reply(page: Page, status=200):
    def handler(route: Route):
        if route.request.method == "OPTIONS":
            route.fulfill(status=204, headers=CORS)
            return
        json_reply(route, {"ok": True}, status)
    page.route("**/api/history/feedback", handler)


def is_feedback_post(r):
    return r.method == "POST" and r.url.endswith("/api/history/feedback")


def open_result(page: Page, ids=(ITEM_A,), item=ITEM_A):
    mock_all(page, ids)
    feedback_reply(page)
    page.goto(BASE)
    expect(page.locator(".app-header")).to_be_visible()
    page.get_by_test_id(f"queue-card-{item}").click()
    expect(page.get_by_test_id("fb-gen-id")).to_have_text(f"#{GEN[item]}")


def tag_btn(page, kind, tag): return page.get_by_test_id(f"fb-tag-{kind}-{tag}")
def pass_btn(page, p):        return page.get_by_test_id(f"fb-pass-{p}")
def reason(page, key):        return page.get_by_test_id(f"fb-reason-{key}")


def save_and_capture(page):
    with page.expect_request(is_feedback_post) as info:
        page.get_by_test_id("fb-save").click()
    return info.value.post_data_json


# FB-01 완료된 T2I 카드를 누르면 태그 패널이 열리고 생성 번호·태그별 버튼 3개·기본 유형/점수가 보임
def test_fb01_opens_with_tags(page: Page):
    open_result(page)
    expect(page.get_by_test_id("fb-panel")).to_be_visible()
    for t in TAGS:
        for kind in ("like", "dislike", "pass"):
            expect(tag_btn(page, kind, t["tag"])).to_be_visible()
    expect(page.get_by_test_id("fb-score-label")).to_have_text("Score: 5")
    expect(page.get_by_test_id("fb-reasons")).to_have_count(0)


# FB-02 한 태그는 좋아요/싫어요/패스 중 하나만 선택, 같은 버튼을 다시 누르면 해제
def test_fb02_tag_choice_is_exclusive(page: Page):
    open_result(page)
    like, dislike = tag_btn(page, "like", "smile"), tag_btn(page, "dislike", "smile")
    like.click()
    expect(like).to_have_class(re.compile(r"\bliked\b"))
    dislike.click()
    expect(like).not_to_have_class(re.compile(r"\bliked\b"))
    expect(dislike).to_have_class(re.compile(r"\bdisliked\b"))
    dislike.click()
    expect(dislike).not_to_have_class(re.compile(r"\bdisliked\b"))


# FB-03 문제 없음 저장: 선택한 태그·점수가 그대로 전송, pass_type 없음, 사유 빈 목록
def test_fb03_save_normal(page: Page):
    open_result(page)
    tag_btn(page, "like", "1girl").click()
    tag_btn(page, "dislike", "smile").click()
    tag_btn(page, "pass", "red_hair").click()
    page.get_by_test_id("fb-score").fill("8")
    assert save_and_capture(page) == {
        "generation_id": 11, "score": 8, "liked_tags": ["1girl"], "disliked_tags": ["smile"],
        "false_tags": ["red_hair"], "pass_type": None, "pass_reasons": []}


# FB-04 그림체=style, 인체 디테일=quality 로 전송
@pytest.mark.parametrize("label,value", [("그림체", "style"), ("인체 디테일", "quality")])
def test_fb04_pass_type_mapping(page: Page, label, value):
    open_result(page)
    pass_btn(page, label).click()
    body = save_and_capture(page)
    assert body["pass_type"] == value and body["pass_reasons"] == [] and body["score"] == 5


# FB-05 마음에 들지 않음: 앞서 고른 태그·점수를 보내지 않고 사유만 전송 (DEF-015)
def test_fb05_dislike_sends_reasons_only(page: Page):
    open_result(page)
    tag_btn(page, "like", "1girl").click()
    tag_btn(page, "dislike", "smile").click()
    tag_btn(page, "pass", "red_hair").click()
    page.get_by_test_id("fb-score").fill("9")
    pass_btn(page, "마음에 들지 않음").click()
    reason(page, "hand").click()
    reason(page, "eye").click()
    assert save_and_capture(page) == {
        "generation_id": 11, "score": None, "liked_tags": [], "disliked_tags": [], "false_tags": [],
        "pass_type": "dislike", "pass_reasons": ["hand", "eye"]}


# FB-06 마음에 들지 않음을 고르면 태그 목록·점수가 숨고 사유 15개가 보임, 다른 유형이면 다시 숨음
def test_fb06_dislike_layout(page: Page):
    open_result(page)
    pass_btn(page, "마음에 들지 않음").click()
    expect(page.get_by_test_id("fb-reasons")).to_be_visible()
    expect(page.locator("[data-testid^='fb-reason-']")).to_have_count(15)
    expect(tag_btn(page, "like", "smile")).to_have_count(0)
    expect(page.get_by_test_id("fb-score")).to_have_count(0)
    pass_btn(page, "문제 없음").click()
    expect(page.get_by_test_id("fb-reasons")).to_have_count(0)
    expect(tag_btn(page, "like", "smile")).to_be_visible()
    expect(page.get_by_test_id("fb-score")).to_be_visible()


# FB-07 사유는 복수 선택, 다시 누르면 해제 (aria-pressed)
def test_fb07_reasons_toggle(page: Page):
    open_result(page)
    pass_btn(page, "마음에 들지 않음").click()
    hand, bg = reason(page, "hand"), reason(page, "background")
    expect(hand).to_have_attribute("aria-pressed", "false")
    hand.click(); bg.click()
    expect(hand).to_have_attribute("aria-pressed", "true")
    expect(bg).to_have_attribute("aria-pressed", "true")
    hand.click()
    expect(hand).to_have_attribute("aria-pressed", "false")
    body = save_and_capture(page)
    assert body["pass_reasons"] == ["background"]


# FB-08 사유 없이 마음에 들지 않음만 저장 가능 (사유 빈 목록)
def test_fb08_dislike_without_reason(page: Page):
    open_result(page)
    pass_btn(page, "마음에 들지 않음").click()
    body = save_and_capture(page)
    assert body["pass_type"] == "dislike" and body["pass_reasons"] == [] and body["score"] is None


# FB-09 마음에 들지 않음에서 고른 사유는 다른 유형으로 바꿔 저장하면 전송되지 않음
def test_fb09_reasons_dropped_for_other_types(page: Page):
    open_result(page)
    pass_btn(page, "마음에 들지 않음").click()
    reason(page, "hand").click()
    pass_btn(page, "그림체").click()
    body = save_and_capture(page)
    assert body["pass_type"] == "style" and body["pass_reasons"] == []


# FB-10 저장 후 화면: 결과가 비워지고 태그 패널이 사라짐(현재 동작 유지), 카드를 다시 누르면 다시 볼 수 있음
def test_fb10_view_cleared_after_save(page: Page):
    open_result(page)
    save_and_capture(page)
    expect(page.get_by_test_id("fb-panel")).to_have_count(0)
    expect(page.get_by_text("생성된 결과가 여기에 표시됩니다")).to_be_visible()
    page.get_by_test_id(f"queue-card-{ITEM_A}").click()
    expect(page.get_by_test_id("fb-gen-id")).to_have_text("#11")


# FB-11 다른 완료 카드를 열면 선택(태그·유형·사유·점수)이 초기화되고 그 항목의 번호로 전송
def test_fb11_selection_reset_on_other_item(page: Page):
    open_result(page, ids=(ITEM_A, ITEM_B))
    tag_btn(page, "like", "smile").click()
    pass_btn(page, "마음에 들지 않음").click()
    reason(page, "eye").click()
    page.get_by_test_id(f"queue-card-{ITEM_B}").click()
    expect(page.get_by_test_id("fb-gen-id")).to_have_text("#12")
    expect(page.get_by_test_id("fb-reasons")).to_have_count(0)
    body = save_and_capture(page)
    assert body == {"generation_id": 12, "score": 5, "liked_tags": [], "disliked_tags": [],
                    "false_tags": [], "pass_type": None, "pass_reasons": []}


# FB-12 패널 토글 버튼으로 접고 펼침 (접으면 패널이 보이지 않음)
def test_fb12_panel_toggle(page: Page):
    open_result(page)
    toggle = page.get_by_test_id("fb-toggle")
    toggle.click()
    expect(page.get_by_test_id("fb-panel")).to_be_hidden()
    toggle.click()
    expect(page.get_by_test_id("fb-panel")).to_be_visible()
