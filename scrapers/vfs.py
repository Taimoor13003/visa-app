"""VFS Global — visa.vfsglobal.com/{pak|are}/en/{iso3}/

Flow (from public info, verify on first --inspect run):
  login (email + password + CAPTCHA, then email OTP) → dashboard → "Start New Booking"
  → choose Application Centre → Appointment Category → Sub-category
  → page shows "Earliest available slot for <category> is : DD-MM-YYYY"
     or "No appointment slots are currently available".
Traps:
  - Cloudflare challenge page ("Just a moment...") before login — operator clears it by hand.
  - One VFS account per country route (pak/nld ≠ are/nld).
  - VFS locks accounts that refresh too often: keep interval ≥ 15 min.
  - UK / Canada / Australia routes need a real GWF / BIL / request-letter reference.
Notes: 2026-11-18 first version, patterns not yet verified against a live page.
"""
import re

from .base import DATE, SlotResult, parse

PROVIDER = "vfs"

AVAILABLE_PATTERNS = [
    re.compile(rf"earliest\s+available\s+(?:appointment\s+)?slot.*?(?:is|:)\s*:?\s*({DATE})", re.I | re.S),
]
NONE_PATTERNS = [
    re.compile(r"no\s+appointment\s+slots?\s+(?:are\s+)?(?:currently\s+)?available", re.I),
    re.compile(r"no\s+slots?\s+(?:are\s+)?(?:currently\s+)?available", re.I),
]


def parse_page(text: str, dates: list[str] | None = None, times: list[str] | None = None) -> SlotResult:
    return parse(text, AVAILABLE_PATTERNS, NONE_PATTERNS, dates, times)
