"""T2I 옵션 패널 - 고급 옵션(AO) e2e 테스트.

태그 파일(/api/system/tags/*.json), 체크포인트, LoRA, 태그 가중치 응답은 가짜로 대체한다(결과를 고정하기 위해).
그 외 API는 실제 서버(8000)를 쓴다.
AO-21(5·6번째 동률 시 표시 기준)은 기준 미정이라 이 파일에서 다루지 않는다.
AO-13(동률)은 "같은 가중치끼리의 순서는 정하지 않는다"가 요구사항이라 순서가 아닌 포함 관계만 확인한다.
AO-20은 결함 후보다. 이 파일에서 실패하면 결함 리포트(DEF-003)를 쓴 뒤 수정한다.
"""
import json
import os
import re

import pytest
from playwright.sync_api import Page, Route, expect

BASE = os.environ.get("AISYSTEM_URL", "http://localhost:5173")
CORS = {"access-control-allow-origin": "*"}

# 태그 파일 구조: {대분류: {...경로...: {영문: {"ko": 한글}}}} (CATEGORY_CONFIG 의 key 경로와 같아야 한다)
FRAMES = {f"frame{i:02d}": {"ko": f"프레임{i:02d}"} for i in range(1, 9)}
TAGS = {
    "character.json": {"character": {"race": {          # 종족: 단일 선택
        "elf": {"ko": "엘프"}, "human": {"ko": "인간"}}}},
    "composition.json": {"composition": {"border_layout": FRAMES}},   # 테두리: 복수 선택
    "accessories.json": {"accessory": {"mask_costume": {"mask": {    # 마스크: 단일 선택, 화면에서 가장 아래 소분류
        "mask_a": {"ko": "마스크A"}, "mask_b": {"ko": "마스크B"}, "mask_c": {"ko": "마스크C"}}}}},
}


def open_t2i(page: Page, weights=None):
    def tag_file(route: Route):
        name = route.request.url.rsplit("/", 1)[-1]
        route.fulfill(status=200, headers=CORS, content_type="application/json",
                      body=json.dumps(TAGS.get(name, {})))

    def checkpoints(route: Route):
        route.fulfill(status=200, headers=CORS, content_type="application/json",
                      body=json.dumps({"checkpoints": ["modelA.safetensors"]}))

    def loras(route: Route):
        route.fulfill(status=200, headers=CORS, content_type="application/json",
                      body=json.dumps({"loras": []}))

    def tag_weights(route: Route):                       # {태그 영문명: 가중치}
        route.fulfill(status=200, headers=CORS, content_type="application/json",
                      body=json.dumps(weights or {}))

    page.route("**/api/system/tags/*", tag_file)
    page.route("**/api/sd/checkpoints", checkpoints)
    page.route("**/api/sd/loras", loras)
    page.route("**/api/history/all-tag-weights", tag_weights)
    page.goto(BASE)
    expect(page.locator(".app-header")).to_be_visible()
    page.get_by_role("button", name="T2I", exact=True).click()
    expect(page.get_by_placeholder("🔍 전체 태그 검색...")).to_be_visible()


# ── 접근자 ────────────────────────────────────────────────

def adv_toggle(page):    return page.get_by_role("button", name="고급 옵션")
def nav_btn(page, cat):  return page.get_by_role("button", name=cat, exact=True)

def cat_title(page, cat):  # 카테고리 제목 글자(div). 같은 글자의 네비게이션 버튼(button)과 구분된다
    return page.locator("div", has_text=re.compile(rf"^{cat}$"))
def cat_block(page, cat):  return cat_title(page, cat).locator("xpath=..")
def scroller(page):        return cat_block(page, "people").locator("xpath=..")   # 태그 목록 창(스크롤 영역)

def sub_header(page, label):   # 소분류 제목 글자. 단일 선택은 "종족단일▶" 처럼 끝에 ▶(닫힘)/▼(열림)
    return page.locator("span", has_text=re.compile(rf"^{label}(단일)?[▶▼]$"))
def sub_block(page, label):    return sub_header(page, label).locator("xpath=../..")
def list_btn(page, label, name):   # 소분류의 전체 태그 목록 버튼. 이름은 "한글(영문)"
    return sub_block(page, label).get_by_role("button", name=name, exact=True)
def chips(page, label):        # ★ 자주 사용하는 태그 버튼. 이름에 "(" 가 없다
    return sub_block(page, label).get_by_role("button").filter(has_not_text="(")

def expect_chip_count(page, label, n):
    try:
        expect(chips(page, label)).to_have_count(n, timeout=3000)
    except AssertionError:
        block = sub_block(page, label)
        pytest.fail(f"칩 개수가 {n} 이 아님. 버튼={block.get_by_role('button').all_inner_texts()} 본문={block.inner_text()!r}")

def wait_scroll_end(page):
    """스크롤 위치가 두 번 연속 같아질 때까지 기다린다(부드러운 스크롤이 끝나도록)."""
    last = None
    for _ in range(30):
        now = scroller(page).evaluate("e => e.scrollTop")
        if now == last:
            return now
        last = now
        page.wait_for_timeout(150)
    return last

def open_sub(page, label):
    sub_header(page, label).click()
    expect(sub_header(page, label)).to_contain_text("▼")

def reset_btn(page):  return page.locator("button", has_text=re.compile("🗑.*초기화"))
def preview(page):    return reset_btn(page).locator("xpath=../..")                 # 최종 프롬프트 영역
def tags(page):       return preview(page).locator("div[style*='inline-flex']")     # 등록된 객체
def tag_names(page):
    return [re.sub(r"\s+", " ", t).replace("×", "").strip() for t in tags(page).all_inner_texts()]

def chip_names(page, label):
    return [t.strip() for t in chips(page, label).all_inner_texts()]

def handle(page):     return scroller(page).locator("xpath=preceding-sibling::div[1]")   # 크기 조절 핸들(태그 목록 창 바로 위)
def split_box(page):  return handle(page).locator("xpath=..")                       # 상단 영역과 카테고리 영역을 담은 컨테이너
def top_pane(page):   return handle(page).locator("xpath=preceding-sibling::div[1]")

def top_ratio(page):  # 상단 영역 높이 / 컨테이너 높이
    return top_pane(page).bounding_box()["height"] / split_box(page).bounding_box()["height"]

def drag_handle_to(page, y):
    """크기 조절 핸들을 잡고 화면 y 좌표까지 끌었다 놓는다."""
    h = handle(page).bounding_box()
    x = h["x"] + h["width"] / 2
    page.mouse.move(x, h["y"] + h["height"] / 2)
    page.mouse.down()
    page.mouse.move(x, y, steps=15)
    page.mouse.up()


# ── 고급 옵션 열기·닫기 ───────────────────────────────────

# AO-01
def test_ao01_advanced_opens_and_shows_nav(page: Page):
    open_t2i(page)
    expect(nav_btn(page, "people")).not_to_be_visible()    # 사전조건: 닫힌 초기 상태
    adv_toggle(page).click()
    expect(nav_btn(page, "people")).to_be_visible()


# AO-02
def test_ao02_advanced_closes_and_hides_nav(page: Page):
    open_t2i(page)
    adv_toggle(page).click()
    expect(nav_btn(page, "people")).to_be_visible()        # 사전조건: 열림
    adv_toggle(page).click()
    expect(nav_btn(page, "people")).not_to_be_visible()


# ── 네비게이션 스크롤 ─────────────────────────────────────

# AO-03
def test_ao03_nav_scrolls_target_to_top_regardless_of_position(page: Page):
    open_t2i(page)
    adv_toggle(page).click()
    scroller(page).evaluate("e => { e.scrollTop = e.scrollHeight }")       # 기존 위치: 맨 아래
    wait_scroll_end(page)
    nav_btn(page, "Attire").click()
    st = wait_scroll_end(page)
    s_box, b_box = scroller(page).bounding_box(), cat_block(page, "Attire").bounding_box()
    offset = b_box["y"] - s_box["y"]
    content_top = offset + st                                               # 블록이 스크롤 내용 안에서 시작하는 위치
    assert abs(offset - 8) <= 3, f"Attire 가 스크롤 영역 맨 위 여백(8px) 위치에서 벗어남: {offset}px (scrollTop={st}, 블록 시작={content_top})"


# AO-10 : 이미 해당 드롭박스가 맨 위에 맞춰진 상태에서 같은 버튼을 다시 누르면 움직이지 않는다
def test_ao10_nav_keeps_position_when_already_at_top(page: Page):
    open_t2i(page)
    adv_toggle(page).click()
    nav_btn(page, "people").click()                                         # 사전조건 만들기: people 을 맨 위에 맞춘다
    first = wait_scroll_end(page)
    assert first == 0, f"처음 열린 상태에서 people 이 이미 맨 위인데 scrollTop={first} 로 이동함"
    nav_btn(page, "people").click()
    second = wait_scroll_end(page)
    assert second == first, f"이미 맨 위인데 {first} → {second} 로 움직임"


# AO-11
def test_ao11_closing_last_sub_shrinks_scroll_area_without_blank(page: Page):
    open_t2i(page)
    open_sub(page, "마스크")
    box = scroller(page)
    box.evaluate("e => { e.scrollTop = e.scrollHeight }")                   # 맨 아래까지
    before = box.evaluate("e => e.scrollHeight")
    sub_header(page, "마스크").click()                                       # 닫기
    expect(sub_header(page, "마스크")).to_contain_text("▶")
    after = box.evaluate("e => e.scrollHeight")
    assert after < before, "닫았는데 스크롤 영역이 줄어들지 않음"
    gap = box.bounding_box()["y"] + box.bounding_box()["height"] - (
        sub_block(page, "마스크").bounding_box()["y"] + sub_block(page, "마스크").bounding_box()["height"])
    assert 0 <= gap <= 24, f"마지막 소분류 아래에 빈 공간 {gap}px"


# ── 카테고리 패널 ─────────────────────────────────────────

# AO-04
def test_ao04_open_sub_shows_its_tags(page: Page):
    open_t2i(page)
    expect(list_btn(page, "종족", "엘프(elf)")).to_have_count(0)           # 사전조건: 닫힘
    open_sub(page, "종족")
    expect(list_btn(page, "종족", "엘프(elf)")).to_be_visible()
    expect(list_btn(page, "종족", "인간(human)")).to_be_visible()


# ── ★ 자주 사용하는 태그 ──────────────────────────────────

# AO-05 : frame03(9) > frame01(8) > frame07(7) > frame05(6) > frame02(5) > frame04(4) > frame06(3), frame08(0)
def test_ao05_top5_by_weight_descending(page: Page):
    weights = {"frame03": 9, "frame01": 8, "frame07": 7, "frame05": 6,
               "frame02": 5, "frame04": 4, "frame06": 3, "frame08": 0}
    open_t2i(page, weights)
    open_sub(page, "테두리")
    expect_chip_count(page, "테두리", 5)
    assert chip_names(page, "테두리") == ["프레임03", "프레임01", "프레임07", "프레임05", "프레임02"]


# AO-12
@pytest.mark.parametrize("n", [1, 3])
def test_ao12_fewer_than_5_shows_all_available(page: Page, n):
    weights = dict(list({"frame01": 5, "frame02": 3, "frame03": 1}.items())[:n])
    open_t2i(page, weights)
    open_sub(page, "테두리")
    expect_chip_count(page, "테두리", n)


# AO-13 : 같은 가중치끼리의 순서는 정하지 않으므로 "표시된 것 ≥ 표시 안 된 것"만 확인한다
def test_ao13_shown_weights_are_not_lower_than_hidden(page: Page):
    weights = {"frame08": 9, **{f"frame{i:02d}": 5 for i in range(1, 8)}}   # 5 가 7개 동률
    open_t2i(page, weights)
    open_sub(page, "테두리")
    expect_chip_count(page, "테두리", 5)
    by_ko = {f"프레임{i:02d}": weights[f"frame{i:02d}"] for i in range(1, 9)}
    shown = chip_names(page, "테두리")
    hidden = [w for ko, w in by_ko.items() if ko not in shown]
    assert min(by_ko[ko] for ko in shown) >= max(hidden), f"표시={shown}"


# AO-14
def test_ao14_zero_or_negative_weight_is_excluded(page: Page):
    open_t2i(page, {"frame01": 3, "frame02": 0, "frame03": -1})
    open_sub(page, "테두리")
    expect_chip_count(page, "테두리", 1)                          # 양수 1개만
    assert chip_names(page, "테두리") == ["프레임01"]


# AO-06
def test_ao06_no_feedback_shows_empty_notice(page: Page):
    open_t2i(page, {})
    open_sub(page, "테두리")
    block = sub_block(page, "테두리")
    expect(block.get_by_text(re.compile(r"^★ 자주 사용하는 태그$"))).to_be_visible()   # 안내문에도 같은 글자가 있어 제목만 정확히 찾는다
    expect(block.get_by_text("아직 피드백이 부족합니다.")).to_be_visible()
    expect_chip_count(page, "테두리", 0)


# ── 태그 선택 ─────────────────────────────────────────────

# AO-07
def test_ao07_clicked_tag_is_appended_to_end_of_prompt(page: Page):
    open_t2i(page)
    open_sub(page, "종족")
    list_btn(page, "종족", "엘프(elf)").click()
    open_sub(page, "테두리")
    list_btn(page, "테두리", "프레임01(frame01)").click()
    expect(tags(page)).to_have_count(2)
    assert tag_names(page) == ["[종족] 엘프(elf)", "[테두리] 프레임01(frame01)"]


# AO-15
def test_ao15_multi_select_click_again_deselects(page: Page):
    open_t2i(page)
    open_sub(page, "테두리")
    list_btn(page, "테두리", "프레임01(frame01)").click()
    expect(tags(page)).to_have_count(1)                                     # 사전조건: 선택됨
    list_btn(page, "테두리", "프레임01(frame01)").click()
    expect(tags(page)).to_have_count(0)


# AO-16
def test_ao16_single_select_click_same_tag_deselects(page: Page):
    open_t2i(page)
    open_sub(page, "종족")
    list_btn(page, "종족", "엘프(elf)").click()
    expect(tags(page)).to_have_count(1)
    list_btn(page, "종족", "엘프(elf)").click()
    expect(tags(page)).to_have_count(0)


# AO-17
def test_ao17_single_select_other_tag_replaces_existing(page: Page):
    open_t2i(page)
    open_sub(page, "종족")
    list_btn(page, "종족", "엘프(elf)").click()
    expect(tags(page)).to_have_count(1)
    list_btn(page, "종족", "인간(human)").click()
    expect(tags(page)).to_have_count(1)
    assert tag_names(page) == ["[종족] 인간(human)"]


# AO-08 : 랜덤을 켜면 목록이 사라지고 "고정: 영문" 이 표시된다
def test_ao08_random_hides_tags_and_shows_picked_value(page: Page):
    open_t2i(page)
    open_sub(page, "테두리")
    expect(list_btn(page, "테두리", "프레임01(frame01)")).to_be_visible()   # 사전조건: 목록이 보임
    sub_block(page, "테두리").get_by_role("checkbox").check()
    expect(list_btn(page, "테두리", "프레임01(frame01)")).to_have_count(0)
    fixed = sub_block(page, "테두리").get_by_text(re.compile(r"^고정:"))
    expect(fixed).to_be_visible()
    picked = fixed.inner_text().replace("고정:", "").strip()
    assert picked in FRAMES, f"카테고리 밖의 값: {picked}"                    # 값 자체는 검증할 수 없어 집합 소속만 확인


# ── 카테고리 영역 크기 조절 ───────────────────────────────

# AO-09
def test_ao09_drag_handle_changes_area_size(page: Page):
    open_t2i(page)
    before = top_ratio(page)
    assert abs(before - 0.4) < 0.03, f"기본 비율이 40% 가 아님: {before:.3f}"
    box = split_box(page).bounding_box()
    drag_handle_to(page, box["y"] + box["height"] * 0.55)
    after = top_ratio(page)
    assert after > before + 0.1, f"크기가 바뀌지 않음: {before:.3f} → {after:.3f}"


# AO-18
def test_ao18_drag_up_stops_at_15_percent(page: Page):
    open_t2i(page)
    drag_handle_to(page, 1)                                                 # 컨테이너 위쪽 한계 밖
    assert abs(top_ratio(page) - 0.15) < 0.02, f"{top_ratio(page):.3f}"


# AO-19
def test_ao19_drag_down_stops_at_85_percent(page: Page):
    open_t2i(page)
    drag_handle_to(page, page.viewport_size["height"] - 1)                  # 컨테이너 아래쪽 한계 밖
    assert abs(top_ratio(page) - 0.85) < 0.02, f"{top_ratio(page):.3f}"


# AO-20 (결함 후보): 핸들을 누른 채 끌 때 텍스트가 선택되거나 목록이 스크롤되면 안 된다
def test_ao20_drag_does_not_select_text_or_scroll_list(page: Page):
    open_t2i(page)
    before_scroll = scroller(page).evaluate("e => e.scrollTop")
    h = handle(page).bounding_box()
    x = h["x"] + h["width"] / 2
    try:
        page.mouse.move(x, h["y"] + h["height"] / 2)
        page.mouse.down()
        page.mouse.move(x - 60, h["y"] + 120, steps=15)                     # 아래 영역의 글자 위를 지나간다
        selected = page.evaluate("window.getSelection().toString()")
        scrolled = scroller(page).evaluate("e => e.scrollTop")
    finally:
        page.mouse.up()
    assert selected == "", f"드래그 중 텍스트가 선택됨: {selected[:40]!r}"
    assert scrolled == before_scroll, f"드래그 중 목록이 스크롤됨: {before_scroll} → {scrolled}"
