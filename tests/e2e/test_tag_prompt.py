"""T2I 옵션 패널 - 태그 검색(TS), 최종 프롬프트(FP) e2e 테스트.

태그 파일(/api/system/tags/*.json), 체크포인트, LoRA 응답은 가짜로 대체한다(결과를 고정하기 위해).
그 외 API는 실제 서버(8000)를 쓴다.
백로그 TC(TS-09, TS-13, TS-14, FP-11)와 칩 TC(TS-16)는 이 파일에서 다루지 않는다.
"""
import json
import os
import re

import pytest
from playwright.sync_api import Page, Route, expect

BASE = os.environ.get("AISYSTEM_URL", "http://localhost:5173")
CORS = {"access-control-allow-origin": "*"}

# 태그 파일 구조: {대분류: {소분류: {영문: {"ko": 한글}}}} (CATEGORY_CONFIG의 key 경로와 같아야 한다)
TAGS = {
    "people.json": {"people": {"number_of_people": {
        "1girl": {"ko": "여자 1명"}, "2girls": {"ko": "여자 2명"}}}},
    "character.json": {"character": {
        "race": {"elf": {"ko": "엘프"}, "human": {"ko": "인간"}},   # 단일 선택 (multi: false)
        "state": {"smile": {"ko": "미소"}}}},                        # 복수 선택 (multi: true)
}
BULK = {"composition.json": {"composition": {"border_layout": {
    f"frame{i:02d}": {"ko": f"프레임{i:02d}"} for i in range(1, 41)}}}}  # 일치 결과가 30개를 넘는 상황 (TS-02)


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    # 복사 버튼(navigator.clipboard) 검증용
    return {**browser_context_args, "permissions": ["clipboard-read", "clipboard-write"]}


def open_t2i(page: Page, bulk=False):
    files = {**TAGS, **(BULK if bulk else {})}

    def tag_file(route: Route):
        name = route.request.url.rsplit("/", 1)[-1]
        route.fulfill(status=200, headers=CORS, content_type="application/json",
                      body=json.dumps(files.get(name, {})))

    def checkpoints(route: Route):
        route.fulfill(status=200, headers=CORS, content_type="application/json",
                      body=json.dumps({"checkpoints": ["modelA.safetensors"]}))

    def loras(route: Route):
        route.fulfill(status=200, headers=CORS, content_type="application/json",
                      body=json.dumps({"loras": []}))

    page.route("**/api/system/tags/*", tag_file)
    page.route("**/api/sd/checkpoints", checkpoints)
    page.route("**/api/sd/loras", loras)
    page.goto(BASE)
    expect(page.locator(".app-header")).to_be_visible()
    page.get_by_role("button", name="T2I", exact=True).click()
    expect(search(page)).to_be_visible()


def search(page):   return page.get_by_placeholder("🔍 전체 태그 검색...")
def reset_btn(page): return page.locator("button", has_text=re.compile("🗑.*초기화"))
def copy_btn(page):  return preview(page).locator("button", has_text="📋")  # 다른 영역에도 복사 버튼이 있어 범위를 좁힘
def preview(page):  return reset_btn(page).locator("xpath=../..")           # 최종 프롬프트 영역
def tags(page):     return preview(page).locator("div[style*='inline-flex']")  # 등록된 객체
def result_rows(page):  # 검색 결과 행: 왼쪽 "분류 / 소분류" 글자로 찾는다
    return page.locator("span", has_text=re.compile(r"^\w+ / ")).locator("xpath=..")


def tag_names(page):
    return [re.sub(r"\s+", " ", t).replace("×", "").strip() for t in tags(page).all_inner_texts()]


def css_color(page, var):
    return page.evaluate(
        """v => { const d = document.createElement('div'); d.style.color = `var(${v})`;
                  document.body.appendChild(d); const c = getComputedStyle(d).color; d.remove(); return c }""",
        var)


def type_and_enter(page, text):
    search(page).fill(text)
    search(page).press("Enter")


# ── 태그 검색 ─────────────────────────────────────────────

def test_ts01_text_is_typed(page: Page):
    open_t2i(page)
    text = "한글 abc 123 !@#"
    search(page).fill(text)
    expect(search(page)).to_have_value(text)


def test_ts02_results_limited_to_30(page: Page):
    open_t2i(page, bulk=True)
    search(page).fill("frame")
    expect(result_rows(page)).to_have_count(30)   # 일치 40개 중 30개만


def test_ts03_enter_registers_listed_tag_with_category(page: Page):
    open_t2i(page)
    type_and_enter(page, "elf")
    expect(tags(page)).to_have_count(1)
    assert tag_names(page) == ["[종족] 엘프(elf)"]
    # 목록에서 등록된 객체와 직접 입력 객체는 색이 다르다 (CSS 변수 --accent)
    expect(tags(page).first).to_have_css("color", css_color(page, "--accent"))


def test_ts04_enter_registers_manual_tag(page: Page):
    open_t2i(page)
    type_and_enter(page, "my tag, another one")
    assert tag_names(page) == ["my_tag", "another_one"]   # 공백은 _, 쉼표로 나눠 각각 등록
    expect(tags(page).first).to_have_css("color", css_color(page, "--success"))


def test_ts05_click_result_registers_tag(page: Page):
    open_t2i(page)
    search(page).fill("elf")
    page.get_by_text("엘프 (elf)", exact=True).click()
    assert tag_names(page) == ["[종족] 엘프(elf)"]
    expect(search(page)).to_have_value("")


def test_ts06_surrounding_spaces_trimmed(page: Page):
    open_t2i(page)
    type_and_enter(page, "   spaced   ")
    assert tag_names(page) == ["spaced"]


def test_ts07_blank_input_adds_nothing_and_keeps_value(page: Page):
    open_t2i(page)
    type_and_enter(page, "   ")
    expect(tags(page)).to_have_count(0)
    expect(search(page)).to_have_value("   ")


def test_ts08_already_registered_is_ignored_and_input_kept(page: Page):
    open_t2i(page)
    type_and_enter(page, "elf")
    expect(tags(page)).to_have_count(1)

    search(page).fill("elf")
    expect(result_rows(page).first).to_be_visible()
    search(page).press("ArrowDown")
    search(page).press("Enter")                       # 키보드로 선택한 이미 등록된 태그
    expect(tags(page)).to_have_count(1)               # 추가도 해제도 안 됨
    expect(search(page)).to_have_value("elf")         # 입력창 유지
    expect(result_rows(page).first).to_be_visible()   # 목록 유지

    page.get_by_text("엘프 (elf)", exact=True).click()   # 목록 클릭도 같다
    expect(tags(page)).to_have_count(1)
    expect(search(page)).to_have_value("elf")
    expect(result_rows(page).first).to_be_visible()


def test_ts10_no_result_shows_nothing_and_enter_adds_manual(page: Page):
    open_t2i(page)
    search(page).fill("zzzzqq")
    page.wait_for_timeout(400)                        # 검색 지연(150ms)보다 길게
    expect(result_rows(page)).to_have_count(0)
    search(page).press("Enter")
    assert tag_names(page) == ["zzzzqq"]


def _active_rows(page, rows):
    accent = css_color(page, "--accent")
    return [i for i in range(rows.count())
            if rows.nth(i).evaluate("e => getComputedStyle(e).backgroundColor") == accent]


def test_ts11_arrow_keys_move_cursor_one_step(page: Page):
    open_t2i(page, bulk=True)
    search(page).fill("frame")
    rows = result_rows(page)
    expect(rows).to_have_count(30)
    search(page).press("ArrowDown")
    assert _active_rows(page, rows) == [0]
    search(page).press("ArrowDown")
    assert _active_rows(page, rows) == [1]
    search(page).press("ArrowUp")
    assert _active_rows(page, rows) == [0]


def test_ts12_arrow_up_at_top_does_not_wrap(page: Page):
    open_t2i(page, bulk=True)
    search(page).fill("frame")
    rows = result_rows(page)
    expect(rows).to_have_count(30)
    search(page).press("ArrowDown")
    search(page).press("ArrowUp")
    assert _active_rows(page, rows) == [0]            # 맨 아래(29)로 가지 않음


def test_ts15_enter_registers_selected_item(page: Page):
    open_t2i(page)
    search(page).fill("elf")
    expect(result_rows(page).first).to_be_visible()
    search(page).press("ArrowDown")
    search(page).press("Enter")
    assert tag_names(page) == ["[종족] 엘프(elf)"]
    expect(search(page)).to_have_value("")


def test_ts17_duplicate_ignored_rest_registered(page: Page):
    open_t2i(page)
    type_and_enter(page, "elf")
    type_and_enter(page, "elf, smile")
    assert tag_names(page) == ["[종족] 엘프(elf)", "[상태] 미소(smile)"]
    expect(search(page)).to_have_value("")

def test_ts18_single_select_subcategory_replaces_existing(page: Page):
    open_t2i(page)
    type_and_enter(page, "elf")
    type_and_enter(page, "human")        # race는 단일 선택
    assert tag_names(page) == ["[종족] 인간(human)"]
    
# ── 최종 프롬프트 ─────────────────────────────────────────

def test_fp01_reset_disabled_when_empty(page: Page):
    open_t2i(page)
    expect(reset_btn(page)).to_be_disabled()


def test_fp02_reset_enabled_with_tags(page: Page):
    open_t2i(page)
    type_and_enter(page, "foo")
    expect(reset_btn(page)).to_be_enabled()


def test_fp03_reset_removes_all(page: Page):
    open_t2i(page)
    type_and_enter(page, "elf")
    type_and_enter(page, "foo")
    expect(tags(page)).to_have_count(2)
    reset_btn(page).click()
    expect(tags(page)).to_have_count(0)
    expect(reset_btn(page)).to_be_disabled()


def test_fp04_copy_puts_comma_separated_text_on_clipboard(page: Page):
    open_t2i(page)
    type_and_enter(page, "elf")
    type_and_enter(page, "foo bar")
    copy_btn(page).click()
    assert page.evaluate("navigator.clipboard.readText()") == "elf, foo_bar"


def test_fp05_copy_with_no_tags_gives_empty_clipboard(page: Page):
    open_t2i(page)
    page.evaluate("navigator.clipboard.writeText('before')")   # 이전 값을 심어 두고 비워지는지 확인
    copy_btn(page).click()
    assert page.evaluate("navigator.clipboard.readText()") == ""


def _drag_over(page, src, dst):
    """src 객체를 dst 객체 위치까지 끌고 간다. 마우스는 놓지 않는다."""
    s, d = src.bounding_box(), dst.bounding_box()
    sx, sy = s["x"] + 4, s["y"] + s["height"] / 2      # × 버튼을 피해 왼쪽 가장자리를 잡는다
    page.mouse.move(sx, sy)
    page.mouse.down()
    page.mouse.move(sx + 10, sy, steps=5)               # 드래그 시작 거리(5px) 넘기기
    page.mouse.move(d["x"] + d["width"] / 2, d["y"] + d["height"] / 2, steps=15)


def test_fp06_dragged_tag_moves_while_dragging(page: Page):
    open_t2i(page)
    type_and_enter(page, "a, b, c")
    first = tags(page).nth(0)
    before = first.bounding_box()["x"]
    try:
        _drag_over(page, first, tags(page).nth(2))
        assert first.bounding_box()["x"] > before + 10
    finally:
        page.mouse.up()


def test_fp07_drop_moves_tag_between_neighbours(page: Page):
    open_t2i(page)
    type_and_enter(page, "a, b, c")
    _drag_over(page, tags(page).nth(0), tags(page).nth(2))
    page.mouse.up()
    expect(tags(page)).to_have_count(3)
    assert tag_names(page) == ["b", "c", "a"]


def test_fp08_dropped_tag_is_not_deleted(page: Page):
    open_t2i(page)
    type_and_enter(page, "a, b, c")
    _drag_over(page, tags(page).nth(0), tags(page).nth(2))
    page.mouse.up()
    page.wait_for_timeout(300)
    assert sorted(tag_names(page)) == ["a", "b", "c"]


def test_fp09_click_deletes_immediately_without_undo(page: Page):
    open_t2i(page)
    type_and_enter(page, "elf")
    type_and_enter(page, "foo")
    tags(page).filter(has_text="foo").click()
    assert tag_names(page) == ["[종족] 엘프(elf)"]
    tags(page).first.click()                            # 목록에서 등록된 객체도 같다
    expect(tags(page)).to_have_count(0)
    expect(page.get_by_text(re.compile("되돌리기|실행 취소|undo", re.I))).to_have_count(0)


def test_fp10_area_scrolls_to_reach_all_tags(page: Page):
    open_t2i(page)
    names = [f"tag{i:02d}" for i in range(1, 41)]
    type_and_enter(page, ", ".join(names))
    expect(tags(page)).to_have_count(40)
    box = tags(page).first.locator("xpath=..")
    assert box.evaluate("e => e.scrollHeight > e.clientHeight")     # 스크롤이 생김
    box.evaluate("e => { e.scrollTop = e.scrollHeight }")
    # 스크롤하면 마지막 객체가 영역 안으로 들어온다 (바깥 패널의 가림과 무관하게 영역 기준으로 비교)
    assert box.evaluate("""(e) => {
        const b = e.getBoundingClientRect(), t = e.lastElementChild.getBoundingClientRect()
        return t.top >= b.top - 1 && t.bottom <= b.bottom + 1 }""")

