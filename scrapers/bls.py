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

from .base import AVAILABLE, DATE, NONE, SlotResult, parse

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


# Seen live on BLS Indonesia, 2026-11-23: the "Appointment Details" page that follows the first form
# carries its whole calendar in a script variable,
#   var availDates = {"min": …, "max": …, "ad": [{"DateText": "2026-11-24", "AppointmentDateType": 0, …}, …]}
# and colours the date picker from it: 0 = appointment available, 1 = no slot, 2 = holiday, 3 = weekend.
# Reading that list needs no click and no extra request (the time slots of a day would cost one each).
DATE_LIST_JS = """() => (typeof availDates === 'object' && availDates && Array.isArray(availDates.ad))
    ? availDates.ad.map(d => ({DateText: d.DateText, AppointmentDateType: d.AppointmentDateType})) : null"""
OPEN_DAY = 0


def from_date_list(days: list[dict] | None) -> SlotResult | None:
    """Result from the page's own date list, or None when the page has no such list (use the text instead)."""
    if not days:
        return None
    known = [d for d in days if isinstance(d.get("DateText"), str) and isinstance(d.get("AppointmentDateType"), int)]
    if len(known) != len(days):  # a shape we have not seen: do not guess
        return None
    open_days = sorted(d["DateText"] for d in known if d["AppointmentDateType"] == OPEN_DAY)
    if not open_days:
        return SlotResult(NONE, detail=f"the portal's date list has {len(known)} day(s), none open")
    span = open_days[0] if len(open_days) == 1 else f"{open_days[0]} to {open_days[-1]}"
    return SlotResult(AVAILABLE, earliest=open_days[0], detail=f"{len(open_days)} open day(s): {span}")


def parse_page(text: str, dates: list[str] | None = None, times: list[str] | None = None) -> SlotResult:
    return parse(text, AVAILABLE_PATTERNS, NONE_PATTERNS, dates, times)
