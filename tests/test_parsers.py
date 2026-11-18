"""Run: python -m pytest tests  (or: python tests/test_parsers.py)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scrapers import SITES  # noqa: E402
from scrapers.base import AVAILABLE, NONE, UNKNOWN  # noqa: E402


def parse_page(provider, text, **kw):
    return SITES[provider].parse_page(text, **kw)


def test_vfs_earliest_slot():
    r = parse_page("vfs", "Earliest available slot for Short Stay is : 04-12-2026\nContinue")
    assert r.status == AVAILABLE and r.earliest == "04-12-2026"


def test_vfs_earliest_slot_with_time():
    r = parse_page("vfs", "Earliest available slot for Tourism is: 04-12-2026 09:30 AM")
    assert r.status == AVAILABLE and r.earliest.startswith("04-12-2026") and r.times


def test_vfs_none():
    r = parse_page("vfs", "No appointment slots are currently available. Please try again later.")
    assert r.status == NONE


def test_bls_none():
    assert parse_page("bls", "Currently, no slots are available for selected category").status == NONE


def test_bls_calendar_dates_and_times():
    r = parse_page("bls", "Select appointment date", dates=["21 Nov 2026", "24 Nov 2026"],
                   times=["09:00-09:15", "Select time", "10:30"])
    assert r.status == AVAILABLE and r.earliest == "21 Nov 2026" and r.times == ["09:00-09:15", "10:30"]


def test_unrecognised_page_is_unknown_not_available():
    assert parse_page("vfs", "Something went wrong. Error 403").status == UNKNOWN


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
