"""BLS International / "Intiana" — Spain PK (appointment.thespainvisa.com),
Spain UAE (uae.blsspainglobal.com), Italy PK (intianaitalyvisa.com), Italy Abu Dhabi.

Flow (from public info, verify on first --inspect run):
  login (email + password + image CAPTCHA, OTP) → New Appointment
  → Location → Visa Type → Category → Submit
  → either "Currently no slots are available" or a calendar of open dates, then time slots.
Traps:
  - Different BLS domains have slightly different layouts → one config entry per domain.
  - Spain UAE added "self-booking verification" (Jul 2026).
  - Calendar dates are read via config `extract.dates` / `extract.times` selectors.
Notes: 2026-11-18 first version, patterns not yet verified against a live page.
"""
import re

from .base import DATE, SlotResult, parse

PROVIDER = "bls"

AVAILABLE_PATTERNS = [
    re.compile(rf"(?:earliest|next)\s+available\s+(?:date|slot|appointment).*?({DATE})", re.I | re.S),
    re.compile(rf"available\s+(?:dates?|slots?)\s*:?\s*({DATE})", re.I),
]
NONE_PATTERNS = [
    re.compile(r"currently\s*,?\s*no\s+(?:appointment\s+)?slots?\s+(?:are\s+)?available", re.I),
    re.compile(r"no\s+(?:appointment\s+)?slots?\s+(?:are\s+)?available", re.I),
    re.compile(r"appointment\s+dates?\s+(?:are\s+)?not\s+available", re.I),
]


def parse_page(text: str, dates: list[str] | None = None, times: list[str] | None = None) -> SlotResult:
    return parse(text, AVAILABLE_PATTERNS, NONE_PATTERNS, dates, times)
