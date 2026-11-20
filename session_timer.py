"""Measure how long a VFS login lasts, without sending anything to VFS.

Attaches to the Chrome window started with --remote-debugging-port (BROWSER_CDP_URL in .env) and
looks at the already-open tab every few seconds: its address and any visible session warning. It never clicks,
types, navigates or reloads, so the portal receives no request from it. It stops and reports when
the tab is back on a login / session-expired page, shows a session dialog, or Chrome is closed.

Usage:  python session_timer.py "Indonesia" --since "2026-11-20 12:34"
        (--since = when you logged in; default is now). Log: debug/session_timer.log
"""
from __future__ import annotations

import argparse
import re
import time
from datetime import datetime
from pathlib import Path

import yaml
from playwright.sync_api import Error as PWError, sync_playwright

import monitor

LOG = monitor.DEBUG / "session_timer.log"
# Any visible text that talks about the session ending, wherever it sits in the page (the portal's
# "5 minutes remaining" warning is not marked up as a dialog). Returns the text plus nearby buttons.
WARNING_JS = r"""() => {
  const re = /session|expire|remaining|time ?out|logged out|sign in again|log ?in again/i, out = [];
  for (const el of document.querySelectorAll('body *')) {
    const own = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(' ').trim();
    if (!own || !re.test(own) || /cookie|privacy/i.test(own)) continue;
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    if (!(r.width > 0 && r.height > 0) || cs.visibility === 'hidden' || cs.display === 'none') continue;
    let box = el; for (let i = 0; i < 5 && box.parentElement && !box.querySelector('button'); i++) box = box.parentElement;
    out.push(own.replace(/\s+/g, ' ').slice(0, 200) + '  [buttons: ' +
             [...box.querySelectorAll('button')].map(b => b.innerText.trim()).filter(Boolean).slice(0, 4).join(' | ') + ']');
  }
  return [...new Set(out)].slice(0, 4);
}"""


def say(msg: str) -> None:
    line = f"{datetime.now():%d-%m %H:%M:%S}  {msg}"
    print(line, flush=True)
    monitor.DEBUG.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("route", help="part of the route name in config.yaml")
    ap.add_argument("--since", help='login time, "YYYY-MM-DD HH:MM" (default: now)')
    ap.add_argument("--every", type=int, default=10, help="seconds between looks (default 10)")
    ap.add_argument("--max-hours", type=float, default=24)
    args = ap.parse_args()
    routes = [m for m in yaml.safe_load((monitor.ROOT / "config.yaml").read_text(encoding="utf-8"))["monitors"]
              if args.route.lower() in m["name"].lower()]
    if len(routes) != 1:
        raise SystemExit(f"{args.route!r} matches {len(routes)} routes")
    mon = routes[0]
    start = datetime.strptime(args.since, "%Y-%m-%d %H:%M") if args.since else datetime.now()
    age = lambda: str(datetime.now() - start).split(".")[0]  # noqa: E731

    with sync_playwright() as pw:
        ctx = monitor.attach_context(pw)
        page = monitor.find_route_page(ctx, mon)
        if page is None or monitor.is_login_page(page):
            raise SystemExit("No logged-in tab for this route in the attached Chrome.")
        say(f"watching {mon['name']} — logged in since {start:%d-%m %H:%M}, tab on {page.url}")
        last_url, looks, seen = page.url, 0, set()
        while (datetime.now() - start).total_seconds() < args.max_hours * 3600:
            time.sleep(args.every)
            looks += 1
            try:
                if page.is_closed():
                    say(f"ENDED after {age()}: the tab was closed")
                    return
                url = page.url
                warnings = page.evaluate(WARNING_JS)
            except PWError as e:
                say(f"ENDED after {age()}: lost the connection to Chrome ({str(e).splitlines()[0][:80]})")
                return
            if url != last_url:
                say(f"address changed after {age()}: {url}")
                last_url = url
            if monitor.is_login_page(page):
                say(f"LOGGED OUT after {age()}: tab is on {url}")
                return
            for w in warnings:  # log each new warning once and keep watching until the real logout
                if w not in seen:
                    seen.add(w)
                    say(f"SESSION WARNING after {age()}: {w}")
            if not warnings and seen:
                say(f"warning gone after {age()} (dismissed, or the session was extended)")
                seen.clear()
            if looks % max(1, 900 // args.every) == 0:
                say(f"still logged in after {age()}")
        say(f"stopped watching after {age()} (time limit); still logged in")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        say("stopped by hand")
