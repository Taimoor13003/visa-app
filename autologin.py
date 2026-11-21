"""Log in to a VFS route by itself in the attached Chrome: Sign in page → emailed code → dashboard.

Used by the monitor for routes with `auto_login: true` and by login_test.py. Everything happens in
the Chrome window a person started (BROWSER_CDP_URL), with the login from .env and the code read
from the mailbox (otp_mail.py). Rules it keeps:
  * one attempt per call, never a retry: a rejected login or code is reported, not repeated
  * the Cloudflare check is only waited for, never touched; without it nothing is filled or pressed
  * nothing is filled unless the mailbox for the code is set up, so no code is requested in vain
  * the code is never logged

Seen on the live page 2026-11-20: while the OneTrust cookie banner is showing, the page loads no
Cloudflare check at all and it only appears on the next page load. The code screen stays on /login,
shows one password-type box named "otp" and a greyed Sign In button. The red "*" beside mandatory
fields is span.c-brand-error, not an error message.
"""
from __future__ import annotations

import re
from datetime import datetime

from playwright.sync_api import Error as PWError, Page

import monitor
import otp_mail

CODE_SCREEN_RE = re.compile(r"one[ -]time password|\botp\b|verification code", re.I)
SIGN_IN_RE = re.compile(r"^\s*sign ?in\s*$", re.I)
EMAIL_BOX = "input[type=text]:visible, input[type=email]:visible"
PASSWORD_BOX = "input[type=password]:visible"
CODE_BOX = "input[formcontrolname=otp i], input[id=otp i], input[name=otp i]"
NECESSARY_ONLY_SEL = "#onetrust-reject-all-handler"  # the banner's "Accept Only Necessary" button
INACTIVE_RE = re.compile(r"account is (?:currently )?(?:inactive|not (?:yet )?activ\w*)", re.I)
REFUSED_RE = re.compile(r"invalid (?:credentials|e-?mail|user ?name|password)|incorrect (?:e-?mail|user ?name|password)"
                        r"|account (?:is|has been) (?:locked|blocked|disabled|suspended)", re.I)
HALTING = ("blocked", "rejected", "inactive", "code_rejected")   # the portal said no: a person must look before any retry
PRESSED: dict[int, datetime] = {}                    # page id → when Sign In was pressed (the code mail comes after)

# What the Sign in page shows, without reading any field's value.
STATE_JS = r"""() => {
  const vis = e => !!(e && e.offsetParent !== null);
  const btn = [...document.querySelectorAll('button')].find(b => vis(b) && /^\s*sign ?in\s*$/i.test(b.innerText));
  const token = document.querySelector("[name='cf-turnstile-response']");
  return {form: [...document.querySelectorAll('input[type=password]')].some(vis),
          token: token ? token.value.length : 0, button: !!btn, enabled: !!btn && !btn.disabled,
          text: document.body.innerText.replace(/\s+/g, ' ').slice(0, 600)};
}"""
BANNER_JS = r"""() => {
  const e = document.querySelector('#onetrust-banner-sdk');
  if (!e) return false;
  const r = e.getBoundingClientRect(), cs = getComputedStyle(e);
  return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
}"""
CHECK_LOADED_JS = "() => typeof window.turnstile !== 'undefined' || !!document.querySelector(\"[name='cf-turnstile-response']\")"


def wait_for_form(page: Page, say) -> bool:
    s = page.evaluate(STATE_JS)
    for _ in range(15):  # a freshly opened page needs a few seconds to draw the form
        if s["form"]:
            return True
        page.wait_for_timeout(2000)
        s = page.evaluate(STATE_JS)
    say(f"no Sign in form on the page. It shows: {s['text'][:200]}")
    return False


def sign_in(page: Page, email: str, password: str, say=print, wait_ready_s: int = 60, wait_result_s: int = 45) -> str:
    """Fill the Sign in form and press Sign In once. Returns what happened:
    code_screen | logged_in | blocked | no_form | no_check | not_ready | rejected | inactive | no_answer."""
    why = monitor.block_reason(page)
    if why:
        say(f"the portal says: {why}")
        return "blocked"
    if not wait_for_form(page, say):
        return "no_form"
    for _ in range(4):  # the banner slides in a moment after the form
        if page.evaluate(BANNER_JS) or page.evaluate(CHECK_LOADED_JS):
            break
        page.wait_for_timeout(2000)
    if page.evaluate(BANNER_JS):
        page.locator(NECESSARY_ONLY_SEL).click(timeout=5000)
        say('cookie banner closed with "Accept Only Necessary"')
        page.wait_for_timeout(1000)
    if not page.evaluate(CHECK_LOADED_JS):
        say("this page has no Cloudflare check loaded; reloading it once")
        page.reload(wait_until="domcontentloaded", timeout=monitor.NAV_TIMEOUT_MS)
        if not wait_for_form(page, say):
            return "no_form"
        for _ in range(10):
            if page.evaluate(CHECK_LOADED_JS):
                break
            page.wait_for_timeout(2000)
        else:
            say("still no Cloudflare check on the page after a reload. Nothing filled; a person has to look")
            return "no_check"
    page.locator(EMAIL_BOX).first.fill(email)
    page.locator(PASSWORD_BOX).first.fill(password)
    say("email and password filled; waiting for the Cloudflare check and the Sign In button")
    for _ in range(wait_ready_s // 2):
        s = page.evaluate(STATE_JS)
        if s["token"] and s["enabled"]:
            break
        page.wait_for_timeout(2000)
    if not s["token"]:
        say("the Cloudflare check did not pass on its own. Not touching it; a person has to look")
        return "no_check"
    if not s["enabled"]:
        say("the Sign In button stayed greyed out although the form is filled")
        return "not_ready"
    PRESSED[id(page)] = datetime.now()
    page.get_by_role("button", name=SIGN_IN_RE).locator("visible=true").first.click()
    say("pressed Sign In once")
    for _ in range(wait_result_s // 2):
        page.wait_for_timeout(2000)
        if not monitor.is_login_page(page):
            say(f"logged in without a code: {page.url}")
            return "logged_in"
        why = monitor.block_reason(page)
        if why:
            say(f"the portal says: {why}")
            return "blocked"
        s = page.evaluate(STATE_JS)
        if CODE_SCREEN_RE.search(s["text"]):
            say(f"code screen reached. It shows: {s['text'][:160]}")
            return "code_screen"
        if INACTIVE_RE.search(s["text"]):  # live 21-11-2026: plain text on the form, not an error element
            say("the portal says this account is inactive: open the activation link VFS emailed, then start again")
            return "inactive"
        err = monitor.login_error(page)
        said = REFUSED_RE.search(s["text"])
        if err or said:
            say(f"the portal rejected the login: {err or said.group(0)}")
            return "rejected"
    say(f"no code screen after {wait_result_s} s. The page shows: {s['text'][:200]}")
    return "no_answer"


def enter_code(page: Page, code: str, say=print, wait_ready_s: int = 30, wait_result_s: int = 45) -> str:
    """Fill the emailed code and press Sign In once. Returns:
    logged_in | no_code_box | not_ready | blocked | code_rejected | no_answer."""
    box = page.locator(CODE_BOX).locator("visible=true")
    if box.count() != 1:
        box = page.locator("input:visible")  # fallback: the code screen shows a single box
    if box.count() != 1:
        say(f"cannot tell which box takes the code ({box.count()} boxes showing); nothing entered")
        return "no_code_box"
    box.first.fill(code)
    for _ in range(wait_ready_s // 2):
        s = page.evaluate(STATE_JS)
        if s["enabled"]:
            break
        page.wait_for_timeout(2000)
    if not s["enabled"]:
        say("the Sign In button on the code screen stayed greyed out")
        return "not_ready"
    page.get_by_role("button", name=SIGN_IN_RE).locator("visible=true").first.click()
    say("code entered; pressed Sign In once")
    for _ in range(wait_result_s // 2):
        page.wait_for_timeout(2000)
        if not monitor.is_login_page(page):
            try:  # let the dashboard draw before anything looks at it
                page.wait_for_load_state("networkidle", timeout=15_000)
            except PWError:
                pass
            say(f"logged in: {page.url}")
            return "logged_in"
        why = monitor.block_reason(page)
        if why:
            say(f"the portal says: {why}")
            return "blocked"
        err = monitor.login_error(page)
        if err:
            say(f"the portal rejected the code: {err}")
            return "code_rejected"
    say(f"still on the code screen {wait_result_s} s after entering the code")
    return "no_answer"


def full_login(page: Page, mon: dict, say=print, get_code=None, fresh: bool = False) -> tuple[bool, str]:
    """Sign in, read the emailed code, enter it. Returns (True, how) or (False, "reason: detail");
    the reason is one of the words above, plus no_login / no_mailbox / no_code.
    fresh=True loads the Sign in page first (ends whatever session the tab still has)."""
    said: list[str] = []

    def tell(msg: str) -> None:
        said.append(msg)
        say(msg)

    def failed(reason: str) -> tuple[bool, str]:
        return False, f"{reason}: {said[-1] if said else ''}"[:300]

    prefix = mon.get("credentials")
    creds = monitor.credentials({"credentials": prefix})
    if not creds:
        tell(f"{prefix}_EMAIL / {prefix}_PASSWORD are not both set in .env")
        return failed("no_login")
    if get_code is None:
        if not otp_mail.settings(prefix):  # before anything is pressed: never request a code we cannot read
            tell("no mailbox set up for the emailed code (OTP_IMAP_PASSWORD in .env)")
            return failed("no_mailbox")
        get_code = lambda after: otp_mail.fetch_code(after, prefix, say=tell)  # noqa: E731
    try:
        if fresh or "/login" not in page.url.lower():
            tell(f"opening the Sign in page {mon['login_url']}")
            page.goto(mon["login_url"], wait_until="domcontentloaded", timeout=monitor.NAV_TIMEOUT_MS)
        started = datetime.now()
        r = sign_in(page, *creds, say=tell)
        if r == "logged_in":
            return True, "logged in without a code"
        if r != "code_screen":
            return failed(r)
        code = get_code(PRESSED.get(id(page), started))
        if not code:
            return failed("no_code")
        r = enter_code(page, code, say=tell)
        return (True, "logged in with the emailed code") if r == "logged_in" else failed(r)
    except Exception as e:  # noqa: BLE001 — a closed tab or a lost connection must not kill the monitor
        tell(f"login stopped by an error: {str(e).splitlines()[0][:160]}")
        return failed("error")
