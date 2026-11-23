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


def test_vfs_live_page_2026_11_19():
    """Text as shown on the live Pakistan → Netherlands page (Karachi, Family And Friends Visit)."""
    r = parse_page("vfs", "Choose your sub-category*\nFamily And Friends Visit\n"
                          "Earliest available slot for 1,2 Applicants is : 20-11-2026\n"
                          "Earliest available slot for 3 Applicants is : 24-11-2026\nContinue")
    assert r.status == AVAILABLE and r.earliest == "20-11-2026"


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


def test_bls_date_list():
    from scrapers import bls
    day = lambda d, t: {"DateText": d, "AppointmentDateType": t}  # noqa: E731
    r = bls.from_date_list([day("2026-11-28", 3), day("2026-11-25", 0), day("2026-11-24", 0), day("2026-12-08", 2)])
    assert r.status == AVAILABLE and r.earliest == "2026-11-24" and "2 open day(s)" in r.detail
    assert bls.from_date_list([day("2026-11-24", 1), day("2026-11-28", 3)]).status == NONE
    assert bls.from_date_list(None) is None and bls.from_date_list([]) is None
    assert bls.from_date_list([{"DateText": "2026-11-24"}]) is None  # unknown shape: fall back to the page text
