# core/system/notify.py
import json
import logging
import threading
import requests
from config.PATH import NOTIFY_CONFIG_PATH


def _load_config() -> dict:
    try:
        with open(NOTIFY_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _post(url: str, content: str):
    try:
        requests.post(url, json={"content": content}, timeout=10)
    except Exception as e:
        logging.warning(f"Discord 알림 전송 실패: {e}")


def notify(title: str, detail: str = "", elapsed_sec: float | None = None, ok: bool = True):
    """
    작업 완료/실패 알림 (Discord 웹훅).
    - 별도 스레드로 전송하므로 호출 측을 블로킹하지 않음
    - 웹훅 URL이 설정되어 있지 않으면 아무것도 하지 않음
    - ok=True일 때만 min_seconds 미만 작업을 건너뜀 (실패는 항상 알림)
    """
    cfg = _load_config()
    url = cfg.get("discord_webhook_url", "")
    if not url or url.startswith("여기에"):
        return

    if ok and elapsed_sec is not None and elapsed_sec < cfg.get("min_seconds", 0):
        return

    icon = "✅" if ok else "❌"
    lines = [f"{icon} **{title}**"]
    if detail:
        lines.append(detail)
    if elapsed_sec is not None:
        lines.append(f"소요시간: {elapsed_sec:.0f}초")

    content = "\n".join(lines)[:1900]  # Discord 메시지 길이 제한(2000자) 여유
    threading.Thread(target=_post, args=(url, content), daemon=True).start()