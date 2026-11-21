"""Read the portal's emailed one-time code from the mailbox it is sent to (IMAP, read-only).

The portal emails a short code after Sign In. This module opens the mailbox read-only, looks only
at recent mail whose sender matches OTP_MAIL_FROM, and returns the code from the newest one that
arrived after the Sign In press. It never marks, moves or deletes mail, and never prints the code.

Settings in .env:
  OTP_IMAP_PASSWORD   the mailbox password. Gmail: an App Password (Google Account → Security →
                      2-Step Verification → App passwords), never the normal password.
  OTP_IMAP_USER       the mailbox address. Default: the route's <PREFIX>_EMAIL.
  OTP_IMAP_HOST       default imap.gmail.com
  OTP_MAIL_FROM       part of the sender to look for. Default "vfs".
  OTP_MAIL_FOLDER     default INBOX

Check the setup against your real mailbox (shows sender, subject and time; the code stays masked):
  python otp_mail.py --check [--credentials VFS]
"""
from __future__ import annotations

import argparse
import email
import imaplib
import os
import re
import time
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.message import Message
from html import unescape
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).parent
CLOCK_SLACK_S = 30      # the mail server's clock and this machine's may differ a little
LOOK_AT_NEWEST = 5      # matching mails fetched per look
# "…One Time Password (OTP) … is 123456" first; a lone 6-digit number as the fallback
CODE_RES = [re.compile(r"(?:\bOTP\b|one[\s-]*time[\s-]*(?:password|passcode|code)|verification code)\D{0,160}?\b(\d{4,8})\b", re.I | re.S),
            re.compile(r"(?<![\d.,/:-])(\d{6})(?![\d.,/:-])")]


def settings(prefix: str | None = None) -> dict | None:
    """Mailbox settings from .env (re-read each time), or None when no mailbox password is set."""
    env = {**os.environ, **{k: v for k, v in dotenv_values(ROOT / ".env").items() if v}}
    user = env.get("OTP_IMAP_USER") or (env.get(f"{prefix}_EMAIL") if prefix else None)
    password = env.get("OTP_IMAP_PASSWORD")
    if not user or not password:
        return None
    host = env.get("OTP_IMAP_HOST", "imap.gmail.com").strip()
    if host.endswith(("gmail.com", "googlemail.com")):
        password = password.replace(" ", "")  # Google shows App Passwords in groups of four
    return {"host": host, "user": user.strip(), "password": password,
            "sender": env.get("OTP_MAIL_FROM", "vfs"), "folder": env.get("OTP_MAIL_FOLDER", "INBOX")}


def message_text(msg: Message) -> str:
    """The readable text of a mail: its plain part, else its HTML with the tags removed."""
    plain, html = [], []
    for part in msg.walk():
        if part.get_content_maintype() != "text" or part.get_filename():
            continue
        try:
            body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
        except Exception:  # noqa: BLE001
            continue
        (plain if part.get_content_subtype() == "plain" else html).append(body)
    if plain and any(p.strip() for p in plain):
        return "\n".join(plain)
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", "\n".join(html))
    return re.sub(r"[ \t\r\f\v]+", " ", unescape(re.sub(r"(?s)<[^>]+>", " ", text)))


def extract_code(text: str) -> str | None:
    for rx in CODE_RES:
        m = rx.search(text)
        if m:
            return m.group(1)
    return None


def _header(msg: Message, name: str) -> str:
    try:
        return str(make_header(decode_header(msg.get(name, ""))))
    except Exception:  # noqa: BLE001
        return msg.get(name, "")


def open_mailbox(cfg: dict) -> imaplib.IMAP4:
    conn = imaplib.IMAP4_SSL(cfg["host"], 993, timeout=20)
    conn.login(cfg["user"], cfg["password"])
    conn.select(cfg["folder"], readonly=True)  # read-only: nothing gets marked as read
    return conn


def newest_mails(conn, cfg: dict, since: datetime) -> list[dict]:
    """Newest first: {"when", "from", "subject", "code"} for recent mail from the portal's sender."""
    conn.noop()  # make the server tell us about mail that arrived since the last look
    day = (since - timedelta(days=1)).strftime("%d-%b-%Y")  # IMAP SINCE works on whole days
    typ, data = conn.uid("SEARCH", None, "SINCE", day, "FROM", '"%s"' % cfg["sender"].replace('"', ""))
    if typ != "OK" or not data or not data[0]:
        return []
    out = []
    for uid in reversed(data[0].split()[-LOOK_AT_NEWEST:]):
        typ, parts = conn.uid("FETCH", uid, "(INTERNALDATE BODY.PEEK[])")
        raw = next((p for p in parts or [] if isinstance(p, tuple)), None)
        if typ != "OK" or raw is None:
            continue
        stamp = imaplib.Internaldate2tuple(raw[0])
        msg = email.message_from_bytes(raw[1])
        out.append({"when": datetime.fromtimestamp(time.mktime(stamp)) if stamp else None,
                    "from": _header(msg, "From"), "subject": _header(msg, "Subject"),
                    "code": extract_code(_header(msg, "Subject") + "\n" + message_text(msg))})
    return sorted(out, key=lambda m: m["when"] or datetime.min, reverse=True)


def fetch_code(after: datetime, prefix: str | None = None, wait_s: int = 120, every_s: int = 5,
               say=lambda msg: None, opener=open_mailbox) -> str | None:
    """Wait for the code mail that arrived after `after` and return its code. None if none came."""
    cfg = settings(prefix)
    if not cfg:
        say("no mailbox set up for the code (OTP_IMAP_PASSWORD in .env)")
        return None
    try:
        conn = opener(cfg)
    except Exception as e:  # noqa: BLE001 — wrong app password, IMAP switched off, no network
        say(f"could not open the mailbox {cfg['user']}: {str(e)[:120]}")
        return None
    try:
        earliest = after - timedelta(seconds=CLOCK_SLACK_S)
        deadline = time.time() + wait_s
        while True:
            for m in newest_mails(conn, cfg, after):
                if m["when"] and m["when"] >= earliest and m["code"]:
                    say(f"code mail found (\"{m['subject'][:60]}\", received {m['when']:%H:%M:%S})")
                    return m["code"]
            if time.time() >= deadline:
                say(f"no code mail from \"{cfg['sender']}\" arrived in {cfg['user']} within {wait_s} s")
                return None
            time.sleep(every_s)
    except Exception as e:  # noqa: BLE001
        say(f"reading the mailbox failed: {str(e)[:120]}")
        return None
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass


def main() -> None:
    ap = argparse.ArgumentParser(description="Check that the code mailbox can be read.")
    ap.add_argument("--check", action="store_true", required=True)
    ap.add_argument("--credentials", default="VFS", help="<PREFIX> whose <PREFIX>_EMAIL is the mailbox (default VFS)")
    args = ap.parse_args()
    cfg = settings(args.credentials)
    if not cfg:
        raise SystemExit("Set OTP_IMAP_PASSWORD in .env first (Gmail: an App Password). "
                         f"The mailbox is OTP_IMAP_USER, or {args.credentials}_EMAIL when that is empty.")
    try:
        conn = open_mailbox(cfg)
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"Could not open {cfg['user']} on {cfg['host']}: {e}")
    mails = newest_mails(conn, cfg, datetime.now() - timedelta(days=2))
    conn.logout()
    print(f"Mailbox {cfg['user']} opened read-only. Recent mail with \"{cfg['sender']}\" in the sender: {len(mails)}")
    for m in mails:
        code = m["code"]
        masked = (code[:2] + "*" * (len(code) - 2)) if code else "NO CODE FOUND"
        print(f"  {m['when']:%d-%m %H:%M:%S}  from {m['from'][:50]!r}  subject {m['subject'][:60]!r}  code {masked}")
    if not mails:
        print("  None found. Log in once by hand so a code mail exists, check the Spam folder, "
              "or set OTP_MAIL_FROM to part of the real sender address.")


if __name__ == "__main__":
    main()
