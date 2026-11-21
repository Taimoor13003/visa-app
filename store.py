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
    if "note" not in {row[1] for row in c.execute("PRAGMA table_info(checks)")}:  # added 2026-11-20
        c.execute("ALTER TABLE checks ADD COLUMN note TEXT")
    return c


def recent(limit: int = 50) -> list[dict]:
    with _conn() as c:
        c.row_factory = sqlite3.Row
        rows = c.execute("SELECT ts, monitor, status, earliest, times, detail, note, screenshot FROM checks "
                         "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [{**dict(r), "screenshot": Path(r["screenshot"]).name if r["screenshot"] else None} for r in rows]


def record(monitor: str, r: SlotResult, screenshot: Path | None, note: str = "") -> None:
    """One row per run. `note` says how the run got in, e.g. "logged in with the emailed code"."""
    with _conn() as c:
        c.execute("INSERT INTO checks (ts, monitor, status, earliest, times, detail, screenshot, note) VALUES (?,?,?,?,?,?,?,?)",
                  (datetime.now().isoformat(timespec="seconds"), monitor, r.status, r.earliest,
                   ",".join(r.times), r.detail[:500], str(screenshot) if screenshot else None, note[:200]))
