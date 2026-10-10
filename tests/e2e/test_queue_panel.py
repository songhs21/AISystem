"""생성 탭 대기열 패널 (TC QU-01~14).

대기열 API(GET/DELETE/POST /api/sd/queue...)를 가짜로 바꿔 항목 상태를 정해 두고, 화면 표시와 화면이 보내는
요청(항목 제거·전체 취소·PC 종료 예약·순서 변경)을 확인한다. 항목 상태는 테스트가 state 를 바꿔 진행시킨다.
처음 로드할 때 이미 끝나 있던 항목은 자동으로 열리지 않으므로 완료 결과는 카드를 눌러 연다.
"""
import json
import os
import re
import time
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Page, Route, expect

BASE = os.environ.get("AISYSTEM_URL", "http://localhost:5173")
CORS = {"access-control-allow-origin": "*", "access-control-allow-headers": "*",
        "access-control-allow-methods": "*"}
PNG_1X1 = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cf000001010100185dd9340000000049454e44ae426082")
GEN = {"qa": 11, "qb": 12, "qr": 13}
IDLE = {"armed": False, "remaining": 0, "extracting": False}
CONFIRM_CLEAR = "대기 중인 항목과 진행 중인 작업을 모두 취소할까요?"
CONFIRM_SHUTDOWN_HEAD = "대기열의 모든 작업이 끝나면 PC를 종료합니다."


def json_reply(route: Route, body, status=200):
    route.fulfill(status=status, headers=CORS, content_type="application/json", body=json.dumps(body))


def item(item_id, status, kind="t2i", progress=0.0, error=None):
    done = status == "done"
    return {"id": item_id, "kind": kind, "status": status, "progress": progress, "error": error,
            "summary": {"mode": kind, "checkpoint": "modelA.safetensors", "prompt": f"prompt {item_id}",
                        "negative": "", "lora": None},
            "result": {"gen_id": GEN.get(item_id, 99), "image_path": f"C:\\fake\\{item_id}.png"} if done else None,
            "created_at": time.time()}


class Queue:
    """가짜 대기열 서버. state 를 바꾸면 다음 GET 에 반영되고, 화면이 보낸 요청은 calls 에 쌓인다."""

    def __init__(self, items=(), shutdown=None):
        self.items = list(items)
        self.shutdown = shutdown or dict(IDLE)
        self.calls = []

    def handler(self, route: Route):
        req = route.request
        if req.method == "OPTIONS":
            route.fulfill(status=204, headers=CORS)
            return
        path = urlparse(req.url).path
        if req.method == "GET" and path == "/api/sd/queue":
            json_reply(route, {"items": self.items, "shutdown": self.shutdown})
            return
        body = req.post_data_json if req.post_data else None
        self.calls.append((req.method, path, body))
        json_reply(route, {"ok": True})

    def sent(self, method, path):
        return [c for c in self.calls if c[0] == method and c[1] == path]


def open_queue(page: Page, items=(), shutdown=None):
    qs = Queue(items, shutdown)
    page.route("**/api/system/tags/*", lambda r: json_reply(r, {}))
    page.route("**/api/sd/checkpoints", lambda r: json_reply(r, {"checkpoints": ["modelA.safetensors"]}))
    page.route("**/api/sd/loras", lambda r: json_reply(r, {"loras": []}))
    page.route("**/api/system/image**", lambda r: r.fulfill(
        status=200, headers=CORS, content_type="image/png", body=PNG_1X1))
    page.route("**/api/history/all-tag-weights", lambda r: json_reply(r, {}))
    page.route("**/api/history/tag-weights", lambda r: json_reply(r, {}))
    page.route("**/api/history/generations/*", lambda r: json_reply(
        r, {"prompt": "1girl", "tags": [{"tag": "1girl", "category": "quality"}]}))
    page.route(re.compile(r".*/api/sd/queue(/.*)?$"), qs.handler)
    page.goto(BASE)
    expect(page.locator(".app-header")).to_be_visible()
    return qs


def card(page, i):    return page.get_by_test_id(f"queue-card-{i}")
def status(page, i):  return page.get_by_test_id(f"queue-status-{i}")
def remove(page, i):  return page.get_by_test_id(f"queue-remove-{i}")


def take_dialog(page, action, accept=True):
    box = []

    def on_dialog(dialog):
        box.append(dialog.message)
        dialog.accept() if accept else dialog.dismiss()

    page.once("dialog", on_dialog)
    action()
    for _ in range(50):
        if box:
            return box[0]
        page.wait_for_timeout(100)
    raise AssertionError("확인창이 뜨지 않음")


def no_request_within(qs, method, path, page, ms=1500):
    page.wait_for_timeout(ms)
    return qs.sent(method, path) == []


# QU-01 비어 있으면 안내 문구와 "0개", 전체 취소·PC 종료 버튼은 없음
def test_qu01_empty(page: Page):
    open_queue(page)
    expect(page.get_by_test_id("queue-panel")).to_be_visible()
    expect(page.get_by_test_id("queue-empty")).to_have_text("생성 요청이 여기에 쌓입니다")
    expect(page.get_by_test_id("queue-count")).to_have_text("0개")
    expect(page.get_by_test_id("queue-clear")).to_have_count(0)
    expect(page.get_by_test_id("queue-shutdown-toggle")).to_have_count(0)
    expect(page.get_by_test_id("queue-toggle")).to_have_text("▲ 대기열")


# QU-02 상태별 카드: 대기 #번호(대기 항목끼리만 센다), 진행률 %, 실패 표시, 완료는 상태 글자 없음, 진행·대기 개수
def test_qu02_card_states(page: Page):
    open_queue(page, [item("qa", "done"), item("e1", "error", error="x"), item("r1", "running", progress=0.42),
                      item("w1", "waiting"), item("w2", "waiting")])
    expect(page.get_by_test_id("queue-count")).to_have_text("진행·대기 3개")
    expect(status(page, "r1")).to_have_text("42%")
    expect(status(page, "w1")).to_have_text("대기 #1")
    expect(status(page, "w2")).to_have_text("대기 #2")
    expect(status(page, "e1")).to_have_text("⚠ 실패")
    expect(status(page, "qa")).to_have_count(0)
    expect(page.get_by_test_id("queue-toggle")).to_have_text("▲ 대기열 3")


# QU-03 × 버튼: 상태별 안내 문구가 다르고 누르면 해당 항목 삭제 요청 (완료·실패는 목록에서 제거)
@pytest.mark.parametrize("st,title", [("waiting", "대기열에서 제거"), ("running", "중단"),
                                      ("done", "목록에서 제거"), ("error", "목록에서 제거")])
def test_qu03_remove_button(page: Page, st, title):
    qs = open_queue(page, [item("x1", st)])
    btn = remove(page, "x1")
    expect(btn).to_have_attribute("title", title)
    with page.expect_request(lambda r: r.method == "DELETE" and r.url.endswith("/api/sd/queue/x1")):
        btn.click()
    assert qs.sent("DELETE", "/api/sd/queue/x1") != []


# QU-04 전체 취소: 확인 후 DELETE /api/sd/queue, 취소하면 요청 없음, 진행·대기가 없으면 버튼 없음
def test_qu04_clear_all_confirmed(page: Page):
    qs = open_queue(page, [item("w1", "waiting"), item("r1", "running")])
    msg = take_dialog(page, page.get_by_test_id("queue-clear").click)
    assert msg == CONFIRM_CLEAR
    page.wait_for_timeout(500)
    assert len(qs.sent("DELETE", "/api/sd/queue")) == 1


def test_qu04_clear_all_dismissed(page: Page):
    qs = open_queue(page, [item("w1", "waiting")])
    take_dialog(page, page.get_by_test_id("queue-clear").click, accept=False)
    assert no_request_within(qs, "DELETE", "/api/sd/queue", page)


def test_qu04_clear_hidden_when_only_finished(page: Page):
    open_queue(page, [item("qa", "done"), item("e1", "error")])
    expect(page.get_by_test_id("queue-count")).to_have_text("2개")
    expect(page.get_by_test_id("queue-clear")).to_have_count(0)
    expect(page.get_by_test_id("queue-shutdown-toggle")).to_have_count(0)


# QU-05 완료 시 PC 종료: 꺼져 있으면 확인 후 켜기 요청, 취소하면 요청 없음, 켜져 있으면 확인 없이 끄기 요청 + "켜짐" 표시
def test_qu05_shutdown_arm_confirmed(page: Page):
    qs = open_queue(page, [item("w1", "waiting")])
    btn = page.get_by_test_id("queue-shutdown-toggle")
    expect(btn).to_have_text("⏻ 완료 시 PC 종료")
    msg = take_dialog(page, btn.click)
    assert msg.startswith(CONFIRM_SHUTDOWN_HEAD)
    page.wait_for_timeout(500)
    assert qs.sent("POST", "/api/sd/queue/shutdown") == [("POST", "/api/sd/queue/shutdown", {"enabled": True})]


def test_qu05_shutdown_arm_dismissed(page: Page):
    qs = open_queue(page, [item("w1", "waiting")])
    take_dialog(page, page.get_by_test_id("queue-shutdown-toggle").click, accept=False)
    assert no_request_within(qs, "POST", "/api/sd/queue/shutdown", page)


def test_qu05_shutdown_disarm_without_confirm(page: Page):
    qs = open_queue(page, [item("w1", "waiting")], {**IDLE, "armed": True})
    btn = page.get_by_test_id("queue-shutdown-toggle")
    expect(btn).to_have_text("⏻ 완료 시 PC 종료 켜짐")
    dialogs = []
    page.once("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    with page.expect_request(lambda r: r.method == "POST" and r.url.endswith("/api/sd/queue/shutdown")) as info:
        btn.click()
    assert info.value.post_data_json == {"enabled": False} and dialogs == []


# QU-06 종료 카운트다운과 종료 전 메모리 추출 안내, "종료 취소"는 abort 요청
def test_qu06_countdown_and_abort(page: Page):
    qs = open_queue(page, [], {**IDLE, "remaining": 42})
    expect(page.get_by_test_id("queue-shutdown-countdown")).to_contain_text("PC가 42초 후 종료됩니다")
    with page.expect_request(lambda r: r.method == "POST" and r.url.endswith("/api/sd/queue/shutdown/abort")):
        page.get_by_test_id("queue-abort-countdown").click()
    assert len(qs.sent("POST", "/api/sd/queue/shutdown/abort")) == 1


def test_qu06_extracting_and_abort(page: Page):
    qs = open_queue(page, [], {**IDLE, "extracting": True, "batches": 3, "max_batches": 10})
    expect(page.get_by_test_id("queue-shutdown-extracting")).to_contain_text("종료 전 LLM 메모리 추출 중 (3/10)")
    with page.expect_request(lambda r: r.method == "POST" and r.url.endswith("/api/sd/queue/shutdown/abort")):
        page.get_by_test_id("queue-abort-extract").click()
    assert len(qs.sent("POST", "/api/sd/queue/shutdown/abort")) == 1


# QU-07 접기/펴기: 접으면 패널이 사라지고 버튼은 ▼, 진행·대기 개수는 유지
def test_qu07_collapse_expand(page: Page):
    open_queue(page, [item("w1", "waiting"), item("w2", "waiting")])
    toggle = page.get_by_test_id("queue-toggle")
    expect(toggle).to_have_text("▲ 대기열 2")
    toggle.click()
    expect(page.get_by_test_id("queue-panel")).to_have_count(0)
    expect(toggle).to_have_text("▼ 대기열 2")
    toggle.click()
    expect(page.get_by_test_id("queue-panel")).to_be_visible()
    expect(toggle).to_have_text("▲ 대기열 2")


# QU-08 카드 크기: 기본 88, 아래 가장자리 드래그로 조절(56~220), 더블클릭하면 88
def card_width(page, i):
    return card(page, i).evaluate("e => e.style.width")


def test_qu08_card_size(page: Page):
    open_queue(page, [item("w1", "waiting")])
    assert card_width(page, "w1") == "88px"
    box = page.get_by_test_id("queue-resize").bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x, y + 40, steps=5)
    page.mouse.up()
    assert card_width(page, "w1") == "128px"
    page.get_by_test_id("queue-resize").dblclick()
    assert card_width(page, "w1") == "88px"


@pytest.mark.parametrize("dy,expected", [(-400, "56px"), (400, "220px")], ids=["min", "max"])
def test_qu08_card_size_limits(page: Page, dy, expected):
    open_queue(page, [item("w1", "waiting")])
    box = page.get_by_test_id("queue-resize").bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x, y + dy, steps=8)
    page.mouse.up()
    assert card_width(page, "w1") == expected


# QU-09 대기 카드를 끌어 순서 변경: 바뀐 대기 id 순서로 reorder 요청
def test_qu09_reorder_by_drag(page: Page):
    qs = open_queue(page, [item("w1", "waiting"), item("w2", "waiting"), item("w3", "waiting")])
    a, c = card(page, "w1").bounding_box(), card(page, "w3").bounding_box()
    page.mouse.move(a["x"] + a["width"] / 2, a["y"] + a["height"] / 2)
    page.mouse.down()
    page.mouse.move(a["x"] + a["width"] / 2 + 10, a["y"] + a["height"] / 2, steps=3)
    page.mouse.move(c["x"] + c["width"] / 2, c["y"] + c["height"] / 2, steps=10)
    with page.expect_request(lambda r: r.method == "POST" and r.url.endswith("/api/sd/queue/reorder")) as info:
        page.mouse.up()
    assert info.value.post_data_json == {"ids": ["w2", "w3", "w1"]}


# QU-10 카드 클릭: 완료=결과 열기, 대기·진행=열려 있던 결과를 닫고 대기 화면, 실패=아무 일 없음
def test_qu10_click_cards(page: Page):
    open_queue(page, [item("qa", "done"), item("e1", "error"), item("w1", "waiting")])
    card(page, "e1").click()
    expect(page.get_by_test_id("fb-panel")).to_have_count(0)
    card(page, "qa").click()
    expect(page.get_by_test_id("fb-gen-id")).to_have_text("#11")
    card(page, "w1").click()
    expect(page.get_by_test_id("fb-panel")).to_have_count(0)


# QU-11 처음 로드 때 이미 끝나 있던 항목은 자동으로 열리지 않음
def test_qu11_existing_done_not_auto_opened(page: Page):
    open_queue(page, [item("qa", "done")])
    page.wait_for_timeout(2500)
    expect(page.get_by_test_id("fb-panel")).to_have_count(0)


# QU-12 진행 중이던 항목이 끝나면 자동으로 결과를 엶(약 1초 간격 확인)
def test_qu12_auto_open_when_finished(page: Page):
    qs = open_queue(page, [item("qr", "running", progress=0.5)])
    expect(status(page, "qr")).to_have_text("50%")
    qs.items = [item("qr", "done")]
    expect(page.get_by_test_id("fb-gen-id")).to_have_text("#13", timeout=10000)


# QU-13 자동 열기는 "가장 최근 완료 항목"을 보고 있을 때만 따라감, 예전 항목을 보는 중이면 그대로 유지
@pytest.mark.parametrize("watching,expected", [("qb", "#13"), ("qa", "#11")], ids=["latest-follows", "older-stays"])
def test_qu13_follow_only_when_watching_latest(page: Page, watching, expected):
    qs = open_queue(page, [item("qa", "done"), item("qb", "done"), item("qr", "running", progress=0.3)])
    card(page, watching).click()
    expect(page.get_by_test_id("fb-gen-id")).to_have_text(f"#{GEN[watching]}")
    qs.items = [item("qa", "done"), item("qb", "done"), item("qr", "done")]
    if expected == "#13":
        expect(page.get_by_test_id("fb-gen-id")).to_have_text("#13", timeout=10000)
    else:
        page.wait_for_timeout(3500)
        expect(page.get_by_test_id("fb-gen-id")).to_have_text("#11")


# QU-14 서버에서 사라진 항목은 목록에서도 사라짐 (완료 항목 제거 현재 동작 유지)
def test_qu14_removed_item_disappears(page: Page):
    qs = open_queue(page, [item("qa", "done"), item("w1", "waiting")])
    expect(card(page, "qa")).to_be_visible()
    qs.items = [item("w1", "waiting")]
    expect(card(page, "qa")).to_have_count(0, timeout=10000)
    expect(status(page, "w1")).to_have_text("대기 #1")
