"""Check history in SQLite (later the dashboard reads from here)."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from scrapers.base import SlotResult

DB = Path(__file__).with_name("history.db")


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS checks (
        id INTEGER PRIMARY KEY, ts TEXT, monitor TEXT, status TEXT,
        earliest TEXT, times TEXT, detail TEXT, screenshot TEXT)""")
    return c


def recent(limit: int = 50) -> list[dict]:
    with _conn() as c:
        c.row_factory = sqlite3.Row
        rows = c.execute("SELECT ts, monitor, status, earliest, times, screenshot FROM checks "
                         "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [{**dict(r), "screenshot": Path(r["screenshot"]).name if r["screenshot"] else None} for r in rows]


def record(monitor: str, r: SlotResult, screenshot: Path | None) -> None:
    with _conn() as c:
        c.execute("INSERT INTO checks (ts, monitor, status, earliest, times, detail, screenshot) VALUES (?,?,?,?,?,?,?)",
                  (datetime.now().isoformat(timespec="seconds"), monitor, r.status, r.earliest,
                   ",".join(r.times), r.detail[:500], str(screenshot) if screenshot else None))
