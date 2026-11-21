# Prompt for Saqib's Claude

Open Claude Code in the cloned repo and paste everything below the line.

---

I'm Saqib, in Pakistan, helping Taimoor run the first live test of a visa-appointment
slot monitor (repo: Taimoor13003/visa-app, cloned in this folder). Read README.md fully
before doing anything.

Goal for this session: get the two routes in config.yaml (VFS Netherlands and BLS Spain,
both from Islamabad) to return "available" or "none" instead of "unknown" when run from
this laptop, following the README section "Live test on a laptop in Pakistan".

Rules:
- Don't change the architecture (engine.py, the Monitor class, the parsers' conservative
  "unknown never alerts" behaviour). Only tune config.yaml steps and, if needed, the
  regex patterns in scrapers/vfs.py and scrapers/bls.py to match the real page text.
- Never commit .env, screenshots/, profiles/ or history.db. Never print the .env values.
- Do not add any CAPTCHA solving, proxy, VPN or stealth/anti-detection code. A person
  completes CAPTCHA/OTP in the browser window; that's by design and by the client's spec.
- Keep the laptop awake and the Chrome window open while testing.

Working method: run `python monitor.py --inspect VFS` (then BLS). When the result is
"unknown", read debug/page.txt and the latest screenshot, fix the button/dropdown names
in config.yaml steps (or the parser pattern), and re-run until it shows a date or "none".
Then start `python app.py --host 0.0.0.0` so Taimoor can open the dashboard over Tailscale.

At the end, report back: for each route, the final result line, the exact config.yaml
steps that worked, any parser pattern changed, and a screenshot of the dashboard card.
Commit only code/config changes with a clear message; ask before pushing.
