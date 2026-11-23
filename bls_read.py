"""Read the open days from a BLS "Appointment Details" page that a person opened.

A person starts Chrome (README, "VFS: attach to your own Chrome"), logs in to BLS, does both picture
CAPTCHAs and submits the booking form by hand. This script then attaches to that Chrome and reads the
day list the page carries (scrapers/bls.py). It types nothing, clicks nothing and submits nothing.

  python bls_read.py                 read the tab as it is
  python bls_read.py --reload        reload the tab once first, then read (is the list refreshed without a CAPTCHA?)
  python bls_read.py --cdp-port 9222 the Chrome's --remote-debugging-port (default 9222)

Why not automate the form: on 2026-11-23 BLS answered the script's form submit with its bot-check page.
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime

from playwright.sync_api import sync_playwright

import monitor
from scrapers import bls

DETAILS = "/blsappointment/manageappointment"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cdp-port", type=int, default=9222)
    ap.add_argument("--reload", action="store_true")
    args = ap.parse_args()
    os.environ["BROWSER_CDP_URL"] = f"http://127.0.0.1:{args.cdp_port}"
    with sync_playwright() as pw:
        try:
            ctx = monitor.attach_context(pw)
        except RuntimeError as e:
            raise SystemExit(str(e))
        tabs = [p for p in ctx.pages if DETAILS in p.url.lower()]
        if not tabs:
            raise SystemExit("No tab is on the BLS Appointment Details page. Open tabs: "
                             + (", ".join(p.url[:70] for p in ctx.pages) or "none"))
        page = tabs[-1]
        if args.reload:
            page.reload(wait_until="domcontentloaded", timeout=monitor.NAV_TIMEOUT_MS)
            page.wait_for_timeout(3000)
            why = monitor.block_reason(page)
            if why:
                raise SystemExit(f"After the reload the portal says: {why}")
            if DETAILS not in page.url.lower():
                raise SystemExit(f"After the reload the portal moved the tab to {page.url[:100]}: "
                                 f"this page cannot be refreshed without going through the CAPTCHA again.")
        days = page.evaluate(bls.DATE_LIST_JS)
        result = bls.from_date_list(days)
        if result is None:
            raise SystemExit("The page has no day list (availDates). Is the calendar page fully loaded?")
        print(f"{datetime.now():%d-%m %H:%M:%S}  {result.status}  earliest: {result.earliest or '-'}  ({result.detail})")
        if days:
            print("open days:", ", ".join(sorted(d["DateText"] for d in days if d["AppointmentDateType"] == bls.OPEN_DAY)) or "none")


if __name__ == "__main__":
    main()
