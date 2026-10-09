import os
import pytest
from playwright.sync_api import Page

BASE = os.environ.get("AISYSTEM_URL", "http://localhost:5173")
TABS = ["🖼️ 생성", "📋 히스토리", "🤖 LLM"]

pytestmark = pytest.mark.smoke


@pytest.fixture
def errors(page: Page):
    """콘솔 error와 처리되지 않은 예외를 수집"""
    found = []
    page.on("console", lambda m: found.append(f"console: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: found.append(f"pageerror: {e}"))
    return found


def _open(page: Page):
    page.goto(BASE)
    page.wait_for_selector(".app-header")
    page.wait_for_load_state("networkidle")


def test_page_loads_without_errors(page: Page, errors):
    _open(page)
    assert page.locator(".app-title").inner_text() == "AISystem"
    assert errors == []


@pytest.mark.parametrize("tab", TABS)
def test_tab_switch_without_errors(page: Page, errors, tab):
    _open(page)
    page.locator(".tab-btn", has_text=tab.split(" ", 1)[1]).click()
    page.wait_for_load_state("networkidle")
    assert page.locator(".tab-btn.active").inner_text() == tab
    assert errors == []