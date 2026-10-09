import os
from playwright.sync_api import Page, expect

BASE = os.environ.get("AISYSTEM_URL", "http://localhost:5173")

def open_t2i(page: Page):
    page.goto(BASE)
    expect(page.locator(".app-header")).to_be_visible()
    page.get_by_role("button", name="T2I", exact=True).click()

def neg_box(page):   return page.locator("label:text-is('❌ 부정 프롬프트') + div")
def neg_text(page):  return neg_box(page).locator("textarea")
def neg_clear(page): return neg_box(page).get_by_title("초기화")

# NG-06
def test_ng06_negative_is_empty_on_open(page: Page):
    open_t2i(page)
    expect(neg_text(page)).to_have_text("")

# NG-05
def test_ng05_negative_clear_button_not_visible(page: Page):
    open_t2i(page)
    expect(neg_clear(page)).not_to_be_visible()

# NG-01
def test_ng01_negative_fill_text(page: Page):
    open_t2i(page)
    neg_text(page).fill("dummy_tag")
    expect(neg_text(page)).to_have_value("dummy_tag")

# NG-02
def test_ng02_negative_clear_button_visible(page: Page):
    open_t2i(page)
    neg_text(page).fill("dummy_tag")
    expect(neg_clear(page)).to_be_visible()
    expect(neg_clear(page)).to_be_enabled()

# NG-03
def test_ng03_negative_clear_button_work(page: Page):
    open_t2i(page)
    neg_text(page).fill("dummy_tag")
    neg_clear(page).click()
    expect(neg_text(page)).to_have_text("")
    
# NG-04
def test_ng04_negative_scrolls_when_text_overflows(page: Page):
    open_t2i(page)
    neg_text(page).fill("\n".join(f"line{i}" for i in range(1, 5)))   # 줄 수는 실측 후 정함
    assert neg_text(page).evaluate("e => e.scrollHeight > e.clientHeight"), "3줄인데 스크롤이 생기지 않음"
    neg_text(page).evaluate("e => { e.scrollTop = e.scrollHeight }")
    assert neg_text(page).evaluate("e => e.scrollTop + e.clientHeight >= e.scrollHeight - 1")  # 맨 아래까지 이동됨# NG-04

# NG-04 스크롤 비활성 테스트
def test_ng04_negative_scrolls_when_text_not_overflows(page: Page):
    open_t2i(page)
    neg_text(page).fill("\n".join(f"line{i}" for i in range(1, 4)))   # 줄 수는 실측 후 정함
    assert not neg_text(page).evaluate("e => e.scrollHeight > e.clientHeight"), "3줄인데 스크롤이 생김"
    neg_text(page).evaluate("e => { e.scrollTop = e.scrollHeight }")