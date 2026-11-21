"""Background engine the dashboard controls.

One worker thread owns Playwright (its sync API is single-threaded). The web app
talks to it through a command queue and reads a thread-safe snapshot.

Per-route states: stopped → starting → waiting_login → running ⇄ checking → stopped
"""
from __future__ import annotations

import os
import queue
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright

import monitor
from monitor import (Monitor, attach_context, captcha_state, cdp_url, credentials, fill_login, find_route_page,
                     go_to_login, is_login_page, launch_context, login_error, open_start, submit_login)

ROOT = Path(__file__).parent
HEADLESS = os.getenv("HEADLESS") == "1"  # default visible: login happens in this browser window


class Engine:
    def __init__(self, config_path: Path | None = None):
        config_path = Path(config_path or os.getenv("VISA_CONFIG", ROOT / "config.yaml"))
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        self.routes: list[dict] = [m for m in cfg["monitors"] if m.get("enabled", True)]
        self.status = {i: "stopped" for i in range(len(self.routes))}
        self.monitors: dict[int, Monitor] = {}
        self.logs: deque[dict] = deque(maxlen=400)
        self.lock = threading.Lock()
        self.cmds: queue.Queue = queue.Queue()
        threading.Thread(target=self._run, daemon=True, name="engine").start()

    # ------------------------------------------------------------ public (web thread)
    def command(self, action: str, idx: int) -> None:
        self.cmds.put((action, idx))

    def log(self, msg: str, level: str = "info") -> None:
        with self.lock:
            self.logs.append({"ts": datetime.now().strftime("%H:%M:%S"), "msg": msg, "level": level})

    def snapshot(self) -> dict:
        now = time.time()
        out = []
        with self.lock:
            for i, r in enumerate(self.routes):
                m = self.monitors.get(i)
                last = m.last if m else None
                out.append({
                    "id": i, "name": r["name"], "provider": r["provider"].upper(),
                    "category": r.get("category", ""), "booking_url": r.get("booking_url", r["start_url"]),
                    "interval_min": round((m.interval if m else 0) / 60, 1),
                    "status": self.status[i],
                    "result": last.status if last else None,
                    "earliest": last.earliest if last else None,
                    "times": last.times if last else [],
                    "detail": (last.detail[:160] if last else ""),
                    "auto_login": monitor.auto_login_on(r),
                    "active_hours": r.get("active_hours"),
                    "last_check": m.last_ts.strftime("%d-%m %H:%M:%S") if m and m.last_ts else None,
                    "next_in": max(0, int(m.next_run - now)) if m and self.status[i] == "running" else None,
                    "screenshot": m.last_shot.name if m and m.last_shot else None,
                    "last_alert": m.last_alert_ts.strftime("%d-%m %H:%M") if m and m.last_alert_ts else None,
                })
            logs = list(self.logs)[-120:]
        return {"routes": out, "logs": logs}

    # ------------------------------------------------------------ worker thread
    def _set(self, idx: int, status: str) -> None:
        with self.lock:
            self.status[idx] = status

    def _run(self) -> None:
        with sync_playwright() as pw:
            contexts = {}
            while True:
                self._drain(pw, contexts)
                for idx, m in list(self.monitors.items()):
                    st = self.status[idx]
                    try:
                        if st == "waiting_login":
                            self._advance_login(idx, m)
                            if time.time() - getattr(m, "live_ts", 0) > 5:  # what the browser window shows now
                                m.live_ts = time.time()
                                monitor.SHOTS.mkdir(exist_ok=True)
                                m.page.screenshot(path=str(monitor.SHOTS / f"live_{idx}.png"))
                                m.live_url = m.page.url
                        elif st == "running" and time.time() >= m.next_run:
                            if m.hold_for_quiet_hours():  # no new login outside the route's active hours
                                continue
                            self._set(idx, "checking")
                            m.tick()
                            m.manual = False
                            m.next_run = time.time() + m.next_delay()
                            if not m.halted and 0 < m.login_checks < m.checks_per_login:
                                self.log(f"[{m.mon['name']}] look {m.login_checks + 1} of {m.checks_per_login} on this "
                                         f"login in {(m.next_run - time.time()) / 60:.0f} min")
                            if m.halted:  # blocked or unreadable: stop this route until a person restarts it
                                self.monitors.pop(idx, None)
                                self._set(idx, "stopped")
                                continue
                            if monitor.auto_login_on(m.mon):  # it logs in by itself at the next check
                                self._set(idx, "running")
                            elif m.last and m.last.status == monitor.LOGIN_REQUIRED:
                                self.log(f"[{m.mon['name']}] session expired — opening the login page", "warn")
                                go_to_login(m.page, m.mon)
                                self._reset_login(m)
                                self._set(idx, "waiting_login")
                            elif self.status[idx] == "checking":
                                self._set(idx, "running")
                    except Exception as e:  # noqa: BLE001 — keep the engine alive
                        self.log(f"[{m.mon['name']}] error: {e}", "error")
                        self._set(idx, "running")
                        m.next_run = time.time() + m.interval
                time.sleep(1)

    def _drain(self, pw, contexts: dict) -> None:
        while True:
            try:
                action, idx = self.cmds.get_nowait()
            except queue.Empty:
                return
            route = self.routes[idx]
            try:
                if action == "start" and self.status[idx] == "stopped":
                    self._start(pw, contexts, idx, route)
                elif action == "stop" and idx in self.monitors:
                    m = self.monitors.pop(idx)
                    if not getattr(m, "attached", False):  # never close the person's own tab
                        m.page.close()
                    self._set(idx, "stopped")
                    self.log(f"[{route['name']}] stopped")
                elif action == "check" and idx in self.monitors and self.status[idx] == "running":
                    self.monitors[idx].next_run, self.monitors[idx].manual = 0, True
                    self.log(f"[{route['name']}] manual check requested")
            except Exception as e:  # noqa: BLE001
                self.log(f"[{route['name']}] {action} failed: {e}", "error")
                self._set(idx, "stopped")
                self.monitors.pop(idx, None)

    def _start(self, pw, contexts: dict, idx: int, route: dict) -> None:
        self._set(idx, "starting")
        self.log(f"[{route['name']}] starting — opening {route['start_url']}")
        if route.get("inpage") and cdp_url():  # attach to the person's own Chrome; open and load nothing
            if "__attached__" not in contexts:
                contexts["__attached__"] = attach_context(pw)
            page = find_route_page(contexts["__attached__"], route)
            if page is None and monitor.auto_login_on(route):  # it logs in by itself: give it a tab to do so
                page = contexts["__attached__"].new_page()
                self.log(f"[{route['name']}] no tab for this route in the attached Chrome — opened one")
            if page is None:
                self.log(f"[{route['name']}] no tab for this route in the attached Chrome — open "
                         f"{route['login_url']} there, log in, then press Start again", "warn")
                self._set(idx, "stopped")
                return
            m = Monitor(route, page, log=lambda msg: self.log(msg, _level(msg)))
            m.attached = True
            with self.lock:
                self.monitors[idx] = m
            if monitor.auto_login_on(route):
                self.log(f"[{route['name']}] attached — automatic login is on; first run starts now", "ok")
                self._set(idx, "running")
            elif is_login_page(page):
                self.log(f"[{route['name']}] the tab is on the login page — log in yourself in that window", "warn")
                self._set(idx, "waiting_login")
            else:
                self.log(f"[{route['name']}] attached to the open tab — monitoring started", "ok")
                self._set(idx, "running")
            return
        prof = route.get("profile", route["provider"])
        if prof not in contexts:
            contexts[prof] = launch_context(pw, prof, headless=HEADLESS)
        page = contexts[prof].new_page()
        m = Monitor(route, page, log=lambda msg: self.log(msg, _level(msg)))
        with self.lock:
            self.monitors[idx] = m
        if not open_start(page, route) or is_login_page(page):
            self.log(f"[{route['name']}] not logged in — opening the login page")
            go_to_login(page, route)
            if not credentials(route):
                self.log(f"[{route['name']}] no {route.get('credentials', '<PREFIX>')}_EMAIL/_PASSWORD in .env "
                         f"— type them in the browser window", "warn")
            self._set(idx, "waiting_login")
        else:
            self.log(f"[{route['name']}] session still active (saved profile) — monitoring started", "ok")
            self._set(idx, "running")

    # ------------------------------------------------------------ login (LinkPricer-style)
    @staticmethod
    def _reset_login(m: Monitor) -> None:
        m.login_filled = m.login_submitted = m.captcha_logged = False
        m.submit_ts, m.error_logged = 0.0, False

    def _advance_login(self, idx: int, m: Monitor) -> None:
        """Called every second while waiting for login: type the credentials, wait for the person
        to complete the CAPTCHA (if any), click Sign in, then wait for OTP / the dashboard."""
        page, name = m.page, m.mon["name"]
        if not is_login_page(page):
            self.log(f"[{name}] logged in — monitoring started", "ok")
            self._reset_login(m)
            m.next_run = 0
            self._set(idx, "running")
            return
        if not m.login_filled:
            if fill_login(page, m.mon):
                m.login_filled = True
                self.log(f"[{name}] email + password filled in")
            elif credentials(m.mon) and not getattr(m, "no_form_logged", False):
                m.no_form_logged = True
                self.log(f"[{name}] waiting for the login form to appear ({page.url})")
            return
        if m.login_submitted:
            if not m.error_logged and time.time() - m.submit_ts > 8:
                m.error_logged = True
                err = login_error(page)
                if err:
                    self.log(f"[{name}] portal says: {err}", "warn")
                else:
                    self.log(f"[{name}] enter the OTP in the browser window if the portal asks for it", "warn")
            return
        if captcha_state(page) == "pending":
            if not m.captcha_logged:
                m.captcha_logged = True
                press = "press Verify and complete the CAPTCHA" if page.locator(monitor.VERIFY_SEL).locator("visible=true").count() \
                    else "complete the CAPTCHA"
                self.log(f"[{name}] email and password are in — {press} in the browser window; "
                         f"the login is sent as soon as it is done", "warn")
            return
        submit_login(page)
        m.login_submitted, m.submit_ts = True, time.time()
        self.log(f"[{name}] signing in…")


def _level(msg: str) -> str:
    if "ALERT SENT" in msg or " available" in msg:
        return "ok"
    if "HALTED" in msg or "login_failed" in msg:
        return "error"
    if "unknown" in msg or "login_required" in msg or "not confirmed" in msg:
        return "warn"
    return "info"
