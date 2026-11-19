# Visa Slot Monitor — Demo

Watches one VFS route and one BLS route and sends a Telegram + email alert with the
**next available slot (date, and time when the portal shows it)**.

## How it works
1. A visible Chrome window opens on the portal's login page. The script **types the email and
   password from `.env`** and clicks Sign in. If the portal shows a CAPTCHA or asks for an OTP, a
   person completes it in that window (the script never solves CAPTCHAs). The browser profile
   keeps the session, so later checks usually skip the login entirely.
2. Every 15 min (minimum 5) it opens the booking form, picks the city/category from `config.yaml`,
   and reads the "earliest available slot" message or calendar.
3. If a slot is found it **re-checks after 60 s**; only if it's still there does it alert
   (prevents fake notifications). The same slot is not re-alerted.
4. If the session expires → operator gets "Login needed". If the page isn't recognised 3× →
   operator gets "Check failing" with a screenshot.
5. Every check is saved in `history.db`; screenshots in `screenshots/`.

**The real portals only open from Pakistan.** BLS shows "Access Denied … outside the permitted
country" to any foreign connection, and VFS refuses too. So the live run must happen on a laptop or
server that is physically in Pakistan (the client's office, or a Pakistan-hosted server).
From anywhere else, use the stand-in demo portal (below).

## Setup (once, ~15 min) — needs Python 3.11 or newer
Mac / Linux:
```bash
cd visa-app
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```
Windows (PowerShell):
```powershell
cd visa-app
py -3 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
copy .env.example .env
```
Then open `.env` and fill in:
- `VFS_EMAIL` / `VFS_PASSWORD` and `BLS_EMAIL` / `BLS_PASSWORD` — the portal logins the bot types in.
- `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_IDS` (and/or the SMTP lines) — where alerts go.
  Test them with `python monitor.py --test-alert`. With nothing filled in, alerts print to the terminal.

`.env` never leaves the machine (it is git-ignored). Don't paste it into chats.

## Live test on a laptop in Pakistan (first run, ~1 hour)
Do this before the client sees anything. Steps 2–4 are the ones that need a person at the keyboard
in Pakistan; everything else can be driven remotely through the dashboard.

1. Setup above, then start the dashboard so a remote person can open it too:
   ```bash
   python app.py --host 0.0.0.0
   ```
   Install **Tailscale** on this laptop and on the presenter's laptop (same account). The presenter
   then opens `http://<this laptop's Tailscale IP>:8000` in a browser — that is the live dashboard.
2. Press **Start** on the VFS card. A Chrome window opens on the real VFS login page; the bot types
   the login. If VFS shows a CAPTCHA tick-box, tick it; if it sends an OTP, type it in the window.
   The card goes from "Waiting for login" to "Monitoring" by itself.
3. The first check will most likely show **`unknown`** — the button/dropdown names in `config.yaml`
   `steps` are guesses until seen on the live page. Send the developer the latest screenshot
   (`screenshots/`, also shown on the card) and `debug/page.txt`. They fix the names; press
   **Check now** again. Repeat until the card shows a slot date or "No slots".
4. Same for the BLS card.
5. Once both show real results, the demo is just: Start → Check now → alert on the phone.

Without the dashboard, the same first run from a terminal:
```bash
python monitor.py --inspect VFS      # or: --inspect BLS   (any unique part of the route name)
python monitor.py --inspect VFS --manual-login   # you log in by hand; the script only reads the page after
```
It logs in, runs the steps once, prints the result and saves `debug/page.txt`, `debug/page.html`
and a screenshot for tuning.

## Run with the dashboard
```bash
python app.py        # then open http://127.0.0.1:8000   (--port 8001 to change)
```
- Each route in `config.yaml` is a card. **Start** opens the portal in a Chrome window and logs in;
  if a CAPTCHA/OTP is needed the card shows "Waiting for login" until a person completes it.
- The card shows the **next available slot**, last check, a live countdown to the next check,
  and the latest screenshot. **Check now** runs a check immediately; **Stop** closes it.
- **Live activity** streams every step; **Check history** lists every check with screenshots.

## Demo from outside Pakistan (local stand-in portal)
For a demo from anywhere, run the monitor against the local look-alike portal — the monitor code,
login typing, config steps, parsers and alerts are exactly the same, only the URLs differ:
```bash
python app.py --demo        # dashboard on :8000 + demo portal on :8010
```
- Dashboard: http://127.0.0.1:8000 — press **Start** on a route; it logs in by itself with
  `DEMO_EMAIL` / `DEMO_PASSWORD` from `.env` (already set in `.env.example`).
- Operator panel: http://127.0.0.1:8010/admin — flip a route to **Slot available** (date + times),
  then press **Check now** on the dashboard: the card goes green, the 60 s confirmation re-check
  runs, and the Telegram/email alert goes out. **Log everyone out** shows the "Login needed" path.
- Routes are in `config.demo.yaml`; the real ones stay in `config.yaml`.

## Running 24/7 later
Run it on a machine in Pakistan (or UAE for the UAE routes): the client's office PC, or a small
server hosted in Pakistan. Keep the machine awake and the Chrome window open; set
`TELEGRAM_OPERATOR_CHAT_IDS` so staff get "Login needed" when a session expires.

## VFS: attach to your own Chrome

VFS shows its login form only to a normally started browser, and keeps the login inside one tab
(a reload logs you out and asks for the emailed code again). So for VFS routes a person logs in
and the script works inside that open tab. Background and evidence: [VFS_PLAN.md](VFS_PLAN.md).

1. Close nothing you need, then start a separate Chrome window for the monitor:

   macOS
   ```bash
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222 --user-data-dir="$HOME/visa-chrome"
   ```
   Windows (Command Prompt)
   ```bat
   "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%USERPROFILE%\visa-chrome"
   ```
2. In that window open the VFS login page for your route and log in yourself: email, password,
   the Cloudflare check, the emailed code. Wait for the dashboard. Keep the tab open.
3. Put `BROWSER_CDP_URL=http://127.0.0.1:9222` in `.env`.
4. One single check first:
   ```bash
   python monitor.py --inspect "Indonesia"
   ```
   It clicks "Start New Booking", picks the centre, category and sub-category from `config.yaml`,
   prints the result and exits. Your Chrome stays open.
5. If that result is right, run the monitor: `python monitor.py` (or the dashboard).

What the script does and does not do on these routes:
- never types the email, password or code, and never touches the Cloudflare check
- never reloads or navigates the tab, and never clicks Continue
- one check per route every 15 minutes at the fastest (20 by default)
- on a login page it waits for you; on a block page, or a page it cannot read three times in a
  row, it stops that route, alerts the operator, and does not retry by itself

Do not use the tab yourself while the monitor runs, and do not reload it.
VFS forbids automated access. This setup lowers the risk of a blocked account; it cannot remove it.

## Run without the dashboard
```bash
python monitor.py
```
