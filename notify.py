"""Telegram and email alerts. Settings come from .env (see .env.example)."""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

import requests


def _list(var: str) -> list[str]:
    return [x.strip() for x in os.getenv(var, "").split(",") if x.strip()]


def send(subject: str, body: str, screenshot: Path | None = None, operator_only: bool = False) -> None:
    """Send to Telegram and email. operator_only=True goes to the operator chat/emails only."""
    tg_chats = _list("TELEGRAM_OPERATOR_CHAT_IDS" if operator_only else "TELEGRAM_CHAT_IDS")
    emails = _list("OPERATOR_EMAILS" if operator_only else "ALERT_EMAILS")
    for chat in tg_chats:
        _telegram(chat, f"*{subject}*\n{body}", screenshot)
    if emails:
        _email(emails, subject, body, screenshot)
    if not tg_chats and not emails:
        print(f"[alert — no recipients configured] {subject}\n{body}")


def _telegram(chat_id: str, text: str, screenshot: Path | None) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN missing; skipping Telegram")
        return
    base = f"https://api.telegram.org/bot{token}"
    try:
        if screenshot and screenshot.exists():
            with screenshot.open("rb") as f:
                r = requests.post(f"{base}/sendPhoto",
                                  data={"chat_id": chat_id, "caption": text[:1000], "parse_mode": "Markdown"},
                                  files={"photo": f}, timeout=30)
        else:
            r = requests.post(f"{base}/sendMessage",
                              data={"chat_id": chat_id, "text": text, "parse_mode": "Markdown",
                                    "disable_web_page_preview": "true"}, timeout=30)
        if not r.ok:
            print(f"Telegram error {r.status_code}: {r.text[:200]}")
    except requests.RequestException as e:
        print(f"Telegram send failed: {e}")


def _email(to: list[str], subject: str, body: str, screenshot: Path | None) -> None:
    host, user, pwd = os.getenv("SMTP_HOST"), os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD")
    if not (host and user and pwd):
        print("SMTP settings missing; skipping email")
        return
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, ", ".join(to)
    msg.set_content(body)
    if screenshot and screenshot.exists():
        msg.add_attachment(screenshot.read_bytes(), maintype="image", subtype="png", filename=screenshot.name)
    try:
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=30) as s:
            s.starttls()
            s.login(user, pwd)
            s.send_message(msg)
    except Exception as e:  # noqa: BLE001 — alerting must never crash the monitor
        print(f"Email send failed: {e}")
