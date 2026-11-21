"""Telegram and email alerts. Settings come from .env (see .env.example)."""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

import requests


def _list(var: str) -> list[str]:
    return [x.strip() for x in os.getenv(var, "").split(",") if x.strip()]


def send(subject: str, body: str, screenshot: Path | None = None, operator_only: bool = False) -> int:
    """Send to Telegram and email. operator_only=True goes to the operator chat/emails only.
    Returns how many deliveries went out (0 = nobody was told)."""
    tg_chats = _list("TELEGRAM_OPERATOR_CHAT_IDS" if operator_only else "TELEGRAM_CHAT_IDS")
    emails = _list("OPERATOR_EMAILS" if operator_only else "ALERT_EMAILS")
    sent = sum(bool(_telegram(chat, f"*{subject}*\n{body}", screenshot)) for chat in tg_chats)
    if emails:
        sent += bool(_email(emails, subject, body, screenshot))
    if not tg_chats and not emails:
        print(f"[alert — no recipients configured] {subject}\n{body}")
    return sent


def _telegram(chat_id: str, text: str, screenshot: Path | None) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN missing; skipping Telegram")
        return False
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
        return r.ok
    except requests.RequestException as e:
        print(f"Telegram send failed: {e}")
        return False


def smtp_settings() -> tuple[str, int, str, str] | None:
    """(host, port, user, password) for outgoing mail, or None when incomplete. When SMTP_USER is the
    mailbox the emailed codes are read from (OTP_IMAP_USER) and SMTP_PASSWORD is empty, that mailbox's
    password (OTP_IMAP_PASSWORD) is used, so it is written in .env once."""
    host, user, pwd = os.getenv("SMTP_HOST"), os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD")
    if user and not pwd and user.strip().lower() == os.getenv("OTP_IMAP_USER", "").strip().lower():
        pwd = os.getenv("OTP_IMAP_PASSWORD")
    if not (host and user and pwd):
        return None
    return host.strip(), int(os.getenv("SMTP_PORT") or 587), user.strip(), pwd


def _email(to: list[str], subject: str, body: str, screenshot: Path | None) -> bool:
    cfg = smtp_settings()
    if not cfg:
        print("SMTP settings missing; skipping email")
        return False
    host, port, user, pwd = cfg
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, ", ".join(to)
    msg.set_content(body)
    if screenshot and screenshot.exists():
        msg.add_attachment(screenshot.read_bytes(), maintype="image", subtype="png", filename=screenshot.name)
    try:
        if port == 465:  # TLS from the first byte (Hostinger and others); 587 upgrades with STARTTLS
            with smtplib.SMTP_SSL(host, port, timeout=30) as s:
                s.login(user, pwd)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.starttls()
                s.login(user, pwd)
                s.send_message(msg)
        return True
    except Exception as e:  # noqa: BLE001 — alerting must never crash the monitor
        print(f"Email send failed: {e}")
        return False
