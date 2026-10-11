"""Minimal Telegram notifier (HTML parse mode). Env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID."""

import json
import os
import urllib.request


def send_message(text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    payload = {
        "chat_id": os.environ["TELEGRAM_CHAT_ID"],
        "text": text[:4000],
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Telegram returned HTTP {resp.status}")
