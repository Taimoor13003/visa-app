"""Can the tool log in to a VFS route by itself?

Attaches to the Chrome window started with --remote-debugging-port (BROWSER_CDP_URL in .env), uses a
tab that is on the route's Sign in page (opens one if there is none), fills the email and password
from .env, waits for the portal's Cloudflare check to pass on its own and presses Sign In once.

  default       stops at the emailed-code screen and reports it; you type the code yourself
  --with-code   also reads the code from the mailbox (otp_mail.py) and enters it: the full login

One attempt only: it never retries and never touches the Cloudflare box. See autologin.py.

Usage:  python login_test.py "Indonesia" [--credentials VFS] [--with-code]
        (--credentials = the <PREFIX> of <PREFIX>_EMAIL / <PREFIX>_PASSWORD in .env; default is
        the route's `credentials` key). Log: debug/login_test.log
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime

import yaml
from playwright.sync_api import sync_playwright

import autologin
import monitor

LOG = monitor.DEBUG / "login_test.log"


def say(msg: str) -> None:
    line = f"{datetime.now():%d-%m %H:%M:%S}  {msg}"
    print(line, flush=True)
    monitor.DEBUG.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("route", help="part of the route name in config.yaml")
    ap.add_argument("--credentials", help="<PREFIX> of <PREFIX>_EMAIL / <PREFIX>_PASSWORD in .env")
    ap.add_argument("--with-code", action="store_true", help="read the emailed code from the mailbox and enter it")
    ap.add_argument("--wait-code", type=int, default=5, help="minutes to keep watching for you to type the code")
    args = ap.parse_args()
    routes = [m for m in yaml.safe_load((monitor.ROOT / "config.yaml").read_text(encoding="utf-8"))["monitors"]
              if args.route.lower() in m["name"].lower()]
    if len(routes) != 1:
        raise SystemExit(f"{args.route!r} matches {len(routes)} routes")
    mon = {**routes[0], "credentials": args.credentials or routes[0].get("credentials")}
    creds = monitor.credentials({"credentials": mon["credentials"]})
    if not creds:
        raise SystemExit(f"{mon['credentials']}_EMAIL / {mon['credentials']}_PASSWORD are not both set in .env")

    with sync_playwright() as pw:
        try:
            ctx = monitor.attach_context(pw)
        except RuntimeError as e:
            raise SystemExit(str(e))
        tabs = [p for p in ctx.pages if p.url.lower().startswith(monitor.route_base(mon).lower())]
        if any(not monitor.is_login_page(p) for p in tabs):
            raise SystemExit("A tab for this route is already logged in. Nothing to test.")
        if tabs:
            page = tabs[-1]
            say(f"{mon['name']}: using the open Sign in tab")
        else:
            page = ctx.new_page()
            say(f"{mon['name']}: opening {mon['login_url']} in a new tab")
            page.goto(mon["login_url"], wait_until="domcontentloaded", timeout=monitor.NAV_TIMEOUT_MS)
        page.bring_to_front()
        if args.with_code:
            ok, how = autologin.full_login(page, mon, say=say)
            say(f"RESULT: {'LOGGED IN' if ok else 'FAILED'} — {how}")
            return
        result = autologin.sign_in(page, *creds, say=say)
        say(f"RESULT: {result}")
        if result != "code_screen":
            return
        say(f"type the emailed code in that tab yourself; watching for {args.wait_code} min")
        for _ in range(args.wait_code * 30):
            time.sleep(2)
            if page.is_closed():
                return
            if not monitor.is_login_page(page):
                say(f"LOGGED IN: {page.url}")
                return
        say("still on the code screen; stopped watching")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        say("stopped by hand")
