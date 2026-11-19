"""Visa appointment slot monitor — demo (VFS + BLS).

Login: the browser window is visible. The script types the email + password from
.env and clicks Sign in; a staff member completes the CAPTCHA / OTP when the portal
asks (the script never solves CAPTCHAs). The persistent browser profile keeps the
session, so most checks need no login. After login it re-opens the booking form
every N minutes, reads the earliest slot, double-checks it, and sends Telegram/email alerts.

Usage:
  python monitor.py                 # run all monitors in config.yaml
  python monitor.py --inspect NAME  # one check with debug dump (for tuning config steps)
  python monitor.py --test-alert    # send a test Telegram/email
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import dotenv_values, load_dotenv
from playwright.sync_api import BrowserContext, Error as PWError, Page, TimeoutError as PWTimeout, sync_playwright

import notify
import store
from scrapers import SITES
from scrapers.base import AVAILABLE, BLOCKED, LOGIN_REQUIRED, NONE, UNKNOWN, SlotResult

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")    # before the settings below are read
SHOTS = ROOT / "screenshots"
DEBUG = ROOT / "debug"
MIN_INTERVAL_MIN = 5          # never check a portal more often than this
CONFIRM_DELAY_S = int(os.getenv("CONFIRM_DELAY_S", "60"))  # wait before the confirmation re-check
UNKNOWN_ALERT_AFTER = 3       # consecutive unrecognised pages before telling the operator


# ---------------------------------------------------------------- browser helpers
NOT_LOGGED_IN_URL_MARKERS = ("login", "page-not-found", "session-expired", "otp")  # VFS sends logged-out users to page-not-found
NAV_TIMEOUT_MS = 60_000       # VFS can take a long time to answer

# Login form helpers (same approach as LinkPricer: credentials from .env, typed by the script,
# CAPTCHA/OTP done by a person in the window, then the script clicks Sign in).
EMAIL_SEL = ("input[type=email], input[name*=email i], input[id*=email i], "
             "input[formcontrolname*=user i], input[name*=user i], input[id*=user i]")
PASSWORD_SEL = "input[type=password]"
CAPTCHA_TOKEN_SEL = ", ".join(f"[name='{n}']" for n in
                              ("cf-turnstile-response", "g-recaptcha-response", "h-captcha-response"))
CAPTCHA_WIDGET_SEL = ("iframe[src*=captcha i], iframe[title*=captcha i], img[src*=captcha i], "
                      "img[id*=captcha i], [id*=captcha i], [class*=captcha i]")
SUBMIT_RE = re.compile(r"^\s*(sign ?in|log ?in|login|submit|continue)\s*$", re.I)


def proxy_settings() -> dict | None:
    """Playwright proxy from .env — needed when the monitor runs outside Pakistan (cloud server).
    PROXY_SERVER=http://host:port or socks5://host:port, plus PROXY_USERNAME / PROXY_PASSWORD."""
    server = os.getenv("PROXY_SERVER", "").strip()
    if not server:
        return None
    proxy = {"server": server}
    if os.getenv("PROXY_USERNAME"):
        proxy["username"], proxy["password"] = os.getenv("PROXY_USERNAME"), os.getenv("PROXY_PASSWORD", "")
    return proxy


def launch_context(pw, profile: str, headless: bool = False) -> BrowserContext:
    """One persistent Chromium profile per portal (keeps the login), through the proxy if set.

    BROWSER_CHANNEL=chrome in .env uses the installed Google Chrome. VFS answered {"code": "403201"}
    to Playwright's bundled Chromium on 2026-11-19 while the same connection worked in normal Chrome.

    BROWSER_ENGINE=cloak in .env swaps Playwright's Chromium for CloakBrowser (stealth build that
    hides automation fingerprints — helps with Cloudflare / bot checks, NOT with country blocks).
    Needs `pip install cloakbrowser` and CLOAKBROWSER_LICENSE_KEY (free key from cloakbrowser.dev)."""
    opts = {"headless": headless, "proxy": proxy_settings()}
    channel = os.getenv("BROWSER_CHANNEL", "").strip().lower()
    if channel:  # "chrome" / "msedge": drive the browser installed on this machine, not Playwright's bundled Chromium
        opts["channel"] = channel
    if os.getenv("BROWSER_ENGINE", "").lower() == "cloak":
        from cloakbrowser import build_launch_options  # optional dependency
        opts = build_launch_options(**opts)                # adds executable_path, stealth args, env
    return pw.chromium.launch_persistent_context(
        str(ROOT / "profiles" / profile), viewport={"width": 1366, "height": 900}, **opts)


def goto(page: Page, url: str) -> bool:
    """Navigate without crashing on a slow portal. False = the page did not load in time."""
    for attempt in range(2):  # one retry: a dropped connection (ERR_NETWORK_CHANGED etc.) usually recovers
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            return True
        except PWError:
            if attempt == 0:
                page.wait_for_timeout(3000)
    return False


def is_login_page(page: Page) -> bool:
    url = page.url.lower()
    if url in ("", "about:blank"):  # nothing loaded yet
        return True
    return any(m in url for m in NOT_LOGGED_IN_URL_MARKERS) or page.locator("input[type=password]").count() > 0


def go_to_login(page: Page, mon: dict) -> None:
    """Open the portal's own login page so the operator can sign in."""
    if mon.get("inpage"):  # never navigate an in-page route's tab; the person handles it
        page.bring_to_front()
        return
    if mon.get("login_url") and goto(page, mon["login_url"]):
        page.wait_for_timeout(3000)
        wait_past_challenge(page)
    page.bring_to_front()


MANUAL_LOGIN = False  # --manual-login: the script types nothing; a person does the whole login


def credentials(mon: dict) -> tuple[str, str] | None:
    """Read <PREFIX>_EMAIL / <PREFIX>_PASSWORD from .env, where PREFIX is the route's `credentials` key."""
    prefix = mon.get("credentials")
    if not prefix or MANUAL_LOGIN or mon.get("inpage"):  # in-page routes: a person always logs in
        return None
    # re-read .env each time so a login saved while the dashboard runs is picked up without a restart
    env = {**os.environ, **{k: v for k, v in dotenv_values(ROOT / ".env").items() if v}}
    email, pw = env.get(f"{prefix}_EMAIL"), env.get(f"{prefix}_PASSWORD")
    return (email, pw) if email and pw else None


# BLS (appointment.thespainvisa.com/Global/account/login, seen 2026-11-19): step one renders ten
# <input class="form-control entry-disabled" type="text"> with random ids, all labelled "Email";
# random CSS classes hide nine, so the real field is the single *visible* one. The button is
# <button id="btnVerify">Verify</button>. Password + CAPTCHA come on the next page.
BLS_LOGIN_INPUT_SEL = "input.entry-disabled"
VERIFY_SEL = "#btnVerify"
VERIFY_RE = re.compile(r"^\s*verify\s*$", re.I)
TYPE_DELAY_MS = 60  # type key by key like a person; BLS flags instant form fills as bots
MAX_VERIFY_TRIES = 1  # per page; if the portal sends us back after Verify, a person must look
_verify_tries: dict[int, int] = {}


def _visible(page: Page, selector: str):
    loc = page.locator(selector).locator("visible=true")
    return loc.first if loc.count() else None


def _visible_email_box(page: Page):
    return _visible(page, f"{BLS_LOGIN_INPUT_SEL}:not([type=password])") or _visible(page, EMAIL_SEL)


def _type(box, text: str) -> None:
    box.click(timeout=5000)  # short: a loader overlay must not stall the login loop for 30 s
    box.press_sequentially(text, delay=TYPE_DELAY_MS, timeout=15000)


def dump_login_page(page: Page, tag: str) -> None:
    """Save the login page as HTML + text + screenshot in debug/ (for tuning selectors)."""
    try:
        DEBUG.mkdir(exist_ok=True)
        (DEBUG / f"login_{tag}.html").write_text(page.content(), encoding="utf-8")
        (DEBUG / f"login_{tag}.txt").write_text(f"URL: {page.url}\n\n{page.inner_text('body')}", encoding="utf-8")
        page.screenshot(path=str(DEBUG / f"login_{tag}.png"), full_page=True)
    except Exception:  # noqa: BLE001
        pass


VFS_DENIED_RE = re.compile(r'^\s*\{\s*"code"\s*:\s*"403\d*"')  # VFS answers a bare JSON body, e.g. {"code": "403201"}


def block_reason(page: Page) -> str:
    """Why the portal refused this connection, or "" if it did not.
    BLS: a "Too Many Requests … excessive requests from your IP" page. VFS: a bare 403 JSON body."""
    try:
        body = page.inner_text("body", timeout=1000)
    except Exception:  # noqa: BLE001
        return ""
    if "too many requests" in (page.title() + " " + body).lower():
        return "Too Many Requests — this IP is rate-limited. Try again in a few hours"
    if VFS_DENIED_RE.match(body) or "access denied" in body.lower()[:300]:
        return f"access denied ({' '.join(body.split())[:80]}). The portal refused this browser or connection"
    return ""


def rate_limited(page: Page) -> bool:
    return block_reason(page).startswith("Too Many Requests")


def fill_login(page: Page, mon: dict) -> bool:
    """Type the email + password into the portal's login form. False if there is no form or no credentials.

    Two-step logins (BLS): when only the email box is showing, type the email and click Verify,
    then return False; a later call types the password once that page appears. True = password typed."""
    creds = credentials(mon)
    if not creds:
        return False
    pw_box = _visible(page, PASSWORD_SEL)
    email_box = _visible_email_box(page)
    if pw_box is None:
        verify = _visible(page, VERIFY_SEL)
        if verify is None:
            btn = page.get_by_role("button", name=VERIFY_RE).locator("visible=true")
            verify = btn.first if btn.count() else None
        tries = _verify_tries.get(id(page), 0)
        if email_box is not None and verify is not None and not email_box.input_value():
            if tries:  # we already submitted the email and the portal sent us back
                err = login_error(page)
                if err or tries >= MAX_VERIFY_TRIES:  # rejected: re-submitting only feeds the rate limit
                    if tries < 99:
                        _verify_tries[id(page)] = 99  # say it once, then stay quiet
                        print(f"[{mon['name']}] the portal sent the login back after Verify"
                              f"{' — it says: ' + err if err else ''}. Not retrying; check "
                              f"{mon.get('credentials', '<PREFIX>')}_EMAIL in .env is a registered account.")
                    return False
            _verify_tries[id(page)] = tries + 1
            _type(email_box, creds[0])
            verify.click(timeout=5000)
            print(f"[{mon['name']}] email typed — clicked Verify, waiting for the password page")
        return False
    _verify_tries.pop(id(page), None)  # password page reached: a later re-login on this page starts fresh
    if email_box is not None and not email_box.input_value():
        _type(email_box, creds[0])
    if not pw_box.input_value():
        _type(pw_box, creds[1])
    return True


def captcha_state(page: Page) -> str:
    """'none' = no CAPTCHA on the form, 'done' = the person has completed it, 'pending' = still to do.
    The script only reads this; the CAPTCHA itself is always done by a person."""
    tokens = page.locator(CAPTCHA_TOKEN_SEL)
    if tokens.count():
        values = tokens.evaluate_all("els => els.map(e => e.value || '')")
        return "done" if any(len(v) > 10 for v in values) else "pending"
    return "pending" if page.locator(CAPTCHA_WIDGET_SEL).count() else "none"


def submit_login(page: Page) -> None:
    btn = page.get_by_role("button", name=SUBMIT_RE)
    if btn.count():
        btn.first.click()
    else:
        page.locator(PASSWORD_SEL).locator("visible=true").first.press("Enter")


def login_error(page: Page) -> str:
    try:
        return page.locator(".alert-danger, .invalid-feedback, .mat-error, mat-error, [class*=error i]") \
            .first.inner_text(timeout=1000).strip()[:200]
    except Exception:  # noqa: BLE001
        return ""


def wait_past_challenge(page: Page, timeout_s: int = 60) -> bool:
    """Wait for a Cloudflare "Just a moment..." page to clear on its own or by the operator's
    click. Nothing is solved automatically. Returns False if it is still there."""
    for _ in range(timeout_s // 2):
        if "just a moment" not in page.title().lower():
            return True
        page.wait_for_timeout(2000)
    return False


def open_start(page: Page, mon: dict) -> bool:
    """Open the route's start page. False if it didn't load or a challenge page is still showing."""
    if not goto(page, mon["start_url"]):
        return False
    page.wait_for_timeout(4000)
    return wait_past_challenge(page)


def wait_for_manual_login(page: Page, mon: dict) -> None:
    if not open_start(page, mon) or is_login_page(page):
        go_to_login(page, mon)
        filled, last_url, n = False, None, 0
        has_creds = credentials(mon) is not None
        for _ in range(90):  # two-step logins: email → Verify → password page (up to ~90 s)
            if page.url != last_url:  # new login page: keep its HTML for selector tuning
                page.wait_for_timeout(1500)
                last_url, n = page.url, n + 1
                dump_login_page(page, str(n))
                print(f"[{mon['name']}] login page {n}: {page.url}  (saved debug/login_{n}.*)")
                why = block_reason(page)
                if why:
                    # exit rather than fall through to the "press Enter" prompt: Enter reloads the portal
                    raise SystemExit(f"[{mon['name']}] the portal says: {why}. Stopped without retrying; "
                                     f"every load during a block can extend it.")
            if not has_creds:
                break
            try:
                filled = fill_login(page, mon)
            except PWError as e:  # page navigated mid-typing, or a field was not clickable
                print(f"[{mon['name']}] login step error: {str(e).splitlines()[0]}")
                dump_login_page(page, f"{n}_error")
                filled = False
            if filled or not is_login_page(page):
                break
            page.wait_for_timeout(1000)
        if filled:
            print(f"[{mon['name']}] email + password filled in")
            if captcha_state(page) == "none":
                submit_login(page)
                print(f"[{mon['name']}] no CAPTCHA on the form — clicked Sign in")
            else:
                print(f"[{mon['name']}] complete the CAPTCHA in the window and click Sign in")
        elif MANUAL_LOGIN:
            print(f"[{mon['name']}] manual login: type the email and password yourself in the window")
        elif not credentials(mon):
            print(f"[{mon['name']}] no {mon.get('credentials', '<PREFIX>')}_EMAIL/_PASSWORD in .env — type them in the window")
        input(f"\n>>> [{mon['name']}] Finish the login in the browser window (CAPTCHA / OTP if asked) "
              f"and wait until the dashboard shows.\n"
              f"    If the window is blank or still loading, open {mon.get('login_url', mon['start_url'])} yourself.\n"
              f"    Then press Enter here... ")


def run_steps(page: Page, steps: list[dict]) -> None:
    """Config-driven navigation: click buttons/links and pick dropdown options by visible text."""
    for step in steps:
        if "goto" in step:
            page.goto(step["goto"], wait_until="domcontentloaded")
        elif "click" in step:
            name = step["click"]
            page.get_by_role("button", name=name).or_(page.get_by_role("link", name=name)) \
                .or_(page.get_by_text(name)).first.click()
        elif "select" in step:
            s = step["select"]
            box = page.get_by_label(s["label"]).first if "label" in s \
                else page.get_by_role("combobox").nth(s.get("index", 0))
            if box.evaluate("e => e.tagName") == "SELECT":
                labels = box.locator("option").all_inner_texts()
                match = next((t for t in labels if s["option"].lower() in t.lower()), s["option"])
                box.select_option(label=match.strip())
            else:
                box.click()
                page.get_by_role("option", name=s["option"]).first.click()
        elif "wait" in step:
            page.wait_for_timeout(int(float(step["wait"]) * 1000))
        page.wait_for_timeout(int(step.get("pause", 1.5) * 1000))


def extract(page: Page, selector: str | None) -> list[str]:
    if not selector:
        return []
    try:
        return [t for t in page.locator(selector).all_inner_texts() if t.strip()]
    except Exception:  # noqa: BLE001
        return []


def screenshot(page: Page, mon: dict) -> Path:
    SHOTS.mkdir(exist_ok=True)
    safe = "".join(ch if ch.isalnum() else "_" for ch in mon["name"])[:60]
    path = SHOTS / f"{datetime.now():%Y%m%d_%H%M%S}_{safe}.png"
    page.screenshot(path=str(path), full_page=True)
    return path


def check(page: Page, mon: dict) -> tuple[SlotResult, Path | None]:
    if mon.get("inpage"):
        return check_inpage(page, mon)
    try:
        if not goto(page, mon["start_url"]):
            return SlotResult(UNKNOWN, detail=f"timeout: portal did not load in {NAV_TIMEOUT_MS // 1000}s"), None
        page.wait_for_timeout(4000)
        if not wait_past_challenge(page):
            return SlotResult(LOGIN_REQUIRED, detail="Cloudflare check page — operator must clear it"), None
        if is_login_page(page):
            return SlotResult(LOGIN_REQUIRED), None
        run_steps(page, mon.get("steps", []))
        page.wait_for_timeout(3000)
        if is_login_page(page):
            return SlotResult(LOGIN_REQUIRED), None
        ex = mon.get("extract") or {}
        result = SITES[mon["provider"]].parse_page(
            page.inner_text("body"), dates=extract(page, ex.get("dates")), times=extract(page, ex.get("times")))
        return result, screenshot(page, mon)
    except Exception as e:  # noqa: BLE001 — one broken monitor must not stop the others
        kind = "timeout" if isinstance(e, PWTimeout) else "error"
        shot = None
        try:  # keep what the page looked like, for fixing the config steps
            shot = screenshot(page, mon)
            DEBUG.mkdir(exist_ok=True)
            (DEBUG / "page.txt").write_text(f"URL: {page.url}\n\n{page.inner_text('body')}", encoding="utf-8")
            (DEBUG / "page.html").write_text(page.content(), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        return SlotResult(UNKNOWN, detail=f"{kind}: {str(e).splitlines()[0]} (on {page.url})"), shot


# ---------------------------------------------------------------- in-page routes (VFS)
# VFS keeps the login inside one tab: any page load or reload sends that tab back to /login, and
# every login needs a person (password, Cloudflare check, emailed one-time code). It also withholds
# the login form from browsers started by an automation tool. So for a route with an `inpage:` block:
#   - a person starts Chrome and logs in; the script attaches to that window (BROWSER_CDP_URL)
#   - the script never navigates, never reloads, never types credentials, never clicks Continue
#   - a check = re-pick the centre in the open booking form and read the slot message
#   - on any block or logged-out page it stops and tells the operator; it never retries by itself
# Details and the evidence behind each rule: VFS_PLAN.md.
INPAGE_MIN_INTERVAL_MIN = 15
CENTRE_SEL = "mat-select[formcontrolname=centerCode]"
SUBCAT_SEL = "mat-select[formcontrolname=visaCategoryCode]"
CATEGORY_SEL = "mat-select:not([formcontrolname=centerCode]):not([formcontrolname=visaCategoryCode])"
LOADER_SEL = ".ngx-overlay"
RESULT_SEL = "div.alert"


def cdp_url() -> str:
    return os.getenv("BROWSER_CDP_URL", "").strip()


def attach_context(pw) -> BrowserContext:
    """Attach to the Chrome window a person started with --remote-debugging-port. Local only."""
    url = cdp_url()
    if not re.match(r"^http://(127\.0\.0\.1|localhost):\d+/?$", url):
        raise RuntimeError(f"BROWSER_CDP_URL must be a local address like http://127.0.0.1:9222 (got {url!r})")
    try:
        return pw.chromium.connect_over_cdp(url).contexts[0]
    except PWError as e:
        raise RuntimeError(f"Could not attach to Chrome at {url}. Start Chrome with --remote-debugging-port "
                         f"first (see README, 'VFS: attach to your own Chrome').\n{str(e).splitlines()[0]}")


def route_base(mon: dict) -> str:
    """https://visa.vfsglobal.com/idn/en/nld/login → https://visa.vfsglobal.com/idn/en/nld/"""
    return mon["login_url"].rsplit("/", 1)[0] + "/"


def find_route_page(ctx: BrowserContext, mon: dict) -> Page | None:
    """The already-open tab for this route. Never opens or loads one: a load would log it out."""
    base = route_base(mon).lower()
    return next((p for p in ctx.pages if p.url.lower().startswith(base)), None)


def wait_for_attached_page(ctx: BrowserContext, mon: dict) -> Page:
    name = mon["name"]
    while True:
        page = find_route_page(ctx, mon)
        if page is None:
            input(f"\n>>> [{name}] No tab for this route in the attached Chrome.\n"
                  f"    Open {mon['login_url']} there yourself, log in (password, check, emailed code),\n"
                  f"    wait for the dashboard, then press Enter here... ")
            continue
        why = block_reason(page)
        if why:
            raise SystemExit(f"[{name}] the portal says: {why}. Stopped without retrying.")
        if is_login_page(page):
            input(f"\n>>> [{name}] The tab is on the login page. Log in yourself in that window\n"
                  f"    and wait for the dashboard, then press Enter here... ")
            continue
        print(f"[{name}] attached to the open tab: {page.url}")
        return page


def _settle(page: Page) -> None:
    """Wait until the portal's full-page loader has come and gone."""
    for _ in range(2):
        page.wait_for_timeout(900)
        try:
            page.locator(LOADER_SEL).first.wait_for(state="hidden", timeout=40_000)
        except PWError:
            pass


def _open_panel(page: Page, select_sel: str) -> None:
    page.locator(select_sel).first.click(timeout=10_000)
    page.locator("mat-option").first.wait_for(state="visible", timeout=10_000)


def _find_option(page: Page, want: str):
    """An option by its id (exact code such as CGK), else exact text, else a unique part of the text."""
    by_id = page.locator(f'mat-option[id="{want}"]')
    if by_id.count():
        return by_id.first
    texts = [t.strip() for t in page.locator("mat-option").all_inner_texts()]
    exact = [i for i, t in enumerate(texts) if t.lower() == want.lower()]
    part = [i for i, t in enumerate(texts) if want.lower() in t.lower()]
    hit = exact or (part if len(part) == 1 else [])
    if not hit:
        page.keyboard.press("Escape")
        raise LookupError(f"option {want!r} not found or not unique; the page offers: {texts}")
    return page.locator("mat-option").nth(hit[0])


def _pick(page: Page, select_sel: str, want: str, fresh: bool = False) -> None:
    """Choose `want` in a dropdown. `fresh`: if it is already chosen, move to another option first,
    because re-choosing the current option makes the portal do nothing."""
    _open_panel(page, select_sel)
    opt = _find_option(page, want)
    if opt.get_attribute("aria-selected") == "true":
        if not fresh:
            page.keyboard.press("Escape")
            return
        other = page.locator('mat-option:not([aria-selected="true"])')
        if not other.count():  # only one centre: nothing to move to, so the shown result is all there is
            page.keyboard.press("Escape")
            return
        other.first.click()
        _settle(page)
        _open_panel(page, select_sel)
        opt = _find_option(page, want)
    opt.click()
    _settle(page)


def check_inpage(page: Page, mon: dict, repick: bool = True) -> tuple[SlotResult, Path | None]:
    """One slot check inside the open booking form. No navigation, no reload, no Continue."""
    cfg = mon["inpage"]
    try:
        why = block_reason(page)
        if why:
            return SlotResult(BLOCKED, detail=why), None
        if is_login_page(page):
            return SlotResult(LOGIN_REQUIRED), None
        marker = cfg.get("url_marker", "application-detail")
        if marker not in page.url:
            start = page.get_by_role("button", name=cfg.get("open", "Start New Booking")).locator("visible=true")
            if not start.count():
                return SlotResult(UNKNOWN, detail=f"error: not on the booking form and no way to it (on {page.url})"), None
            start.first.click()
            page.wait_for_url(f"**/*{marker}*", timeout=30_000)
            _settle(page)
        if repick:
            _pick(page, CENTRE_SEL, str(cfg["centre"]), fresh=True)
            if cfg.get("category"):
                _pick(page, CATEGORY_SEL, str(cfg["category"]))
            if cfg.get("subcategory"):
                _pick(page, SUBCAT_SEL, str(cfg["subcategory"]))
            try:
                page.locator(RESULT_SEL).first.wait_for(state="visible", timeout=20_000)
            except PWError:
                pass
        why = block_reason(page)
        if why:
            return SlotResult(BLOCKED, detail=why), None
        if is_login_page(page):
            return SlotResult(LOGIN_REQUIRED), None
        alerts = [t.strip() for t in page.locator(RESULT_SEL).locator("visible=true").all_inner_texts() if t.strip()]
        text = "\n".join(alerts) or page.inner_text("body")
        result = SITES[mon["provider"]].parse_page(text)
        SHOTS.mkdir(exist_ok=True)
        safe = "".join(ch if ch.isalnum() else "_" for ch in mon["name"])[:60]
        shot = SHOTS / f"{datetime.now():%Y%m%d_%H%M%S}_{safe}.png"
        page.screenshot(path=str(shot))  # viewport only: a full-page capture would resize the person's tab
        return result, shot
    except Exception as e:  # noqa: BLE001
        try:
            page.keyboard.press("Escape")  # never leave a dropdown hanging open in the person's tab
        except Exception:  # noqa: BLE001
            pass
        kind = "timeout" if isinstance(e, PWTimeout) else "error"
        return SlotResult(UNKNOWN, detail=f"{kind}: {str(e).splitlines()[0]} (on {page.url})"), None


# ---------------------------------------------------------------- alerting logic
def slot_message(mon: dict, r: SlotResult) -> tuple[str, str]:
    when = r.earliest + (f" — times: {', '.join(r.times)}" if r.times else "")
    subject = f"✅ Slot available: {mon['name']}"
    body = (f"Country/route: {mon['name']}\n"
            f"Category: {mon.get('category', '-')}\n"
            f"Next available slot: {when}\n"
            f"Detected: {datetime.now():%d-%m-%Y %H:%M} (confirmed by a second check)\n"
            f"Book here: {mon.get('booking_url', mon['start_url'])}")
    return subject, body


class Monitor:
    """One route: runs a check, keeps the latest result, decides which alerts to send."""

    def __init__(self, mon: dict, page: Page | None, log=print):
        self.mon, self.page, self.log = mon, page, log
        floor = INPAGE_MIN_INTERVAL_MIN if mon.get("inpage") else MIN_INTERVAL_MIN
        self.interval = max(float(mon.get("interval_minutes", 15)), floor) * 60
        self.halted = False            # set on a block: no more checks until a person restarts the monitor
        self.next_run = 0.0
        self.last_alert_key: str | None = None
        self.login_alerted = False
        self.unknown_streak = 0
        self.last: SlotResult | None = None
        self.last_shot: Path | None = None
        self.last_ts: datetime | None = None
        self.last_alert_ts: datetime | None = None
        self.login_filled = False      # dashboard login state machine (engine.py)
        self.login_submitted = False
        self.captcha_logged = False
        self.submit_ts = 0.0
        self.error_logged = False

    def _check(self) -> SlotResult:
        r, shot = check(self.page, self.mon)
        store.record(self.mon["name"], r, shot)
        self.last, self.last_shot, self.last_ts = r, shot or self.last_shot, datetime.now()
        return r

    def _halt(self, subject: str, detail: str) -> None:
        self.halted = True
        self.log(f"[{self.mon['name']}] HALTED: {detail[:160]} — no more checks until restarted")
        notify.send(subject, f"{detail[:300]}\n\nThe monitor has stopped checking this route and will not "
                             f"retry by itself. Look at the browser window, then restart it.", operator_only=True)

    def tick(self) -> None:
        name = self.mon["name"]
        if self.halted:
            return
        r = self._check()
        extra = f" — {r.detail[:120]}" if r.status == UNKNOWN and r.detail.startswith(("error", "timeout")) else ""
        self.log(f"[{name}] {r.status} {r.earliest or ''} {' '.join(r.times)}".rstrip() + extra)

        if r.status == BLOCKED:
            self._halt(f"⛔ Portal blocked us: {name}", f"The portal says: {r.detail}")
            return

        if r.status == LOGIN_REQUIRED:
            if not self.login_alerted:
                notify.send(f"🔑 Login needed: {name}",
                            "Session expired. Log in again in the monitor's browser window.", operator_only=True)
                self.login_alerted = True
            return
        self.login_alerted = False

        if r.status == UNKNOWN:
            self.unknown_streak += 1
            if self.unknown_streak == UNKNOWN_ALERT_AFTER:
                notify.send(f"⚠️ Check failing: {name}",
                            f"Page not recognised {UNKNOWN_ALERT_AFTER} times in a row.\n{r.detail[:300]}",
                            self.last_shot, operator_only=True)
                if self.mon.get("inpage"):  # do not keep clicking in a page we no longer understand
                    self._halt(f"⛔ Stopped: {name}", f"Page not recognised {UNKNOWN_ALERT_AFTER} times: {r.detail}")
            return
        self.unknown_streak = 0

        if r.status == NONE:
            self.last_alert_key = None
            return

        # AVAILABLE: confirm with a second check before alerting (stops fake alerts)
        if r.key() == self.last_alert_key:
            return
        self.log(f"[{name}] slot seen ({r.earliest}) — re-checking in {CONFIRM_DELAY_S}s before alerting")
        time.sleep(CONFIRM_DELAY_S)
        if self.mon.get("inpage"):  # confirm by re-reading the message; a second re-pick would double the requests
            r2, _ = check_inpage(self.page, self.mon, repick=False)
        else:
            r2 = self._check()
        if r2.status != AVAILABLE:
            self.log(f"[{name}] not confirmed on re-check ({r2.status}); no alert sent")
            return
        subject, body = slot_message(self.mon, r2)
        notify.send(subject, body, self.last_shot)
        self.last_alert_key, self.last_alert_ts = r2.key(), datetime.now()
        self.log(f"[{name}] ALERT SENT: next slot {r2.earliest} {' '.join(r2.times)}".rstrip())


# ---------------------------------------------------------------- entry point
def open_pages(pw, monitors: list[dict]) -> dict[str, Page]:
    contexts: dict[str, BrowserContext] = {}
    pages: dict[str, Page] = {}
    for mon in monitors:
        if mon.get("inpage") and cdp_url():  # attach to the person's own Chrome; open and load nothing
            if "__attached__" not in contexts:
                try:
                    contexts["__attached__"] = attach_context(pw)
                except RuntimeError as e:
                    raise SystemExit(str(e))
            pages[mon["name"]] = wait_for_attached_page(contexts["__attached__"], mon)
            continue
        prof = mon.get("profile", mon["provider"])
        if prof not in contexts:
            contexts[prof] = launch_context(pw, prof)
        ctx = contexts[prof]
        pages[mon["name"]] = ctx.pages[0] if not pages and ctx.pages else ctx.new_page()
        wait_for_manual_login(pages[mon["name"]], mon)
    return pages


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):  # Windows consoles: never crash on ✅ / → in log lines
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--inspect", metavar="NAME")
    ap.add_argument("--test-alert", action="store_true")
    ap.add_argument("--manual-login", action="store_true",
                    help="type nothing into the login form; a person logs in, then the script reads the slots")
    args = ap.parse_args()
    global MANUAL_LOGIN
    MANUAL_LOGIN = args.manual_login

    if args.test_alert:
        notify.send("🔔 Test alert", "Visa monitor alerts are working.")
        return

    monitors = [m for m in yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))["monitors"] if m.get("enabled", True)]
    if args.inspect:  # exact name, or a unique part of it (e.g. --inspect VFS) — easier to type on Windows
        exact = [m for m in monitors if m["name"] == args.inspect]
        monitors = exact or [m for m in monitors if args.inspect.lower() in m["name"].lower()]
        if len(monitors) != 1:
            raise SystemExit(f"--inspect {args.inspect!r} matches {len(monitors)} routes; use one of: "
                             + ", ".join(repr(m["name"]) for m in yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))["monitors"]))

    with sync_playwright() as pw:
        pages = open_pages(pw, monitors)

        if args.inspect:
            mon, page = monitors[0], pages[monitors[0]["name"]]
            r, shot = check(page, mon)
            DEBUG.mkdir(exist_ok=True)
            (DEBUG / "page.txt").write_text(page.inner_text("body"), encoding="utf-8")
            (DEBUG / "page.html").write_text(page.content(), encoding="utf-8")
            print(f"\nResult: {r}\nScreenshot: {shot}\nPage text/HTML saved in {DEBUG}/")
            print(f"Dropdowns found: {page.get_by_role('combobox').count()}")
            if not (mon.get("inpage") and cdp_url()):  # attached: nothing of ours to close
                input("Press Enter to close...")
            return

        mons = [Monitor(m, pages[m["name"]]) for m in monitors]
        print(f"\nMonitoring {len(mons)} route(s). Ctrl+C to stop.\n")
        while True:
            now = time.time()
            for m in mons:
                if now >= m.next_run:
                    m.tick()
                    m.next_run = time.time() + m.interval
            time.sleep(5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
