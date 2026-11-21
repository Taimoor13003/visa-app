"""Shared pieces for every site scraper: result type, statuses, generic text parser.

Each site module (vfs.py, bls.py, …) keeps its own constants + patterns and a pure
`parse_page()` built on `parse()` below — same layout as the LinkPricer scrapers
(constants, pure parse function separate from browser I/O, registry in __init__).

Patterns are conservative: "available" only when an availability message or real
dates are positively recognised. Anything unrecognised is UNKNOWN and goes to the
operator for review — never to clients as a slot alert (prevents fake notifications).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Pattern

AVAILABLE = "available"
NONE = "none"
LOGIN_REQUIRED = "login_required"
LOGIN_FAILED = "login_failed"   # the automatic login did not get in; `detail` says at which step and why
BLOCKED = "blocked"          # portal warned us (rate limit / access denied) → monitor pauses itself
UNKNOWN = "unknown"

BLOCK_PATTERNS = [
    re.compile(r"too\s+many\s+(?:requests|attempts|login)", re.I),
    re.compile(r"\b(?:error\s*)?429\b", re.I),
    re.compile(r"access\s+(?:is\s+)?denied|403\s+forbidden", re.I),
    re.compile(r"(?:account|access)\s+(?:has\s+been\s+)?(?:temporarily\s+)?(?:blocked|locked|suspended)", re.I),
    re.compile(r"unusual\s+(?:activity|traffic)|suspicious\s+activity", re.I),
    re.compile(r"rate\s*limit", re.I),
]

DATE = r"\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}"
TIME_RE = re.compile(r"\b(?:[01]?\d|2[0-3]):[0-5]\d(?:\s*[AaPp][Mm])?\b")


@dataclass
class SlotResult:
    status: str
    earliest: str | None = None
    times: list[str] = field(default_factory=list)
    detail: str = ""

    def key(self) -> str:
        """Identity used to avoid sending the same alert twice."""
        return f"{self.status}|{self.earliest}|{','.join(self.times[:3])}"


def parse(text: str, available: list[Pattern], none: list[Pattern],
          dates: list[str] | None = None, times: list[str] | None = None) -> SlotResult:
    """`available` patterns must capture the date in group 1.
    `dates` / `times` come from the optional `extract` selectors in config.yaml."""
    clean_dates = [d.strip() for d in (dates or []) if d and d.strip()]
    clean_times = [t.strip() for t in (times or []) if t and TIME_RE.search(t)]

    for rx in none:
        m = rx.search(text)
        if m and not clean_dates:
            return SlotResult(NONE, detail=m.group(0))

    for rx in available:
        m = rx.search(text)
        if m:
            return SlotResult(AVAILABLE, earliest=m.group(1).strip(),
                              times=clean_times or TIME_RE.findall(text[m.end():m.end() + 400])[:5],
                              detail=m.group(0)[:200])

    if clean_dates:
        return SlotResult(AVAILABLE, earliest=clean_dates[0], times=clean_times,
                          detail=f"{len(clean_dates)} open date(s) on calendar")

    return SlotResult(UNKNOWN, detail=text[:300])
