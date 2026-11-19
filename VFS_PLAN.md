# VFS scraping plan

Written 2026-11-19 from a read-only walk through the live Indonesia → Netherlands portal
(`visa.vfsglobal.com/idn/en/nld`) in a normal Chrome window with a person logged in.
Nothing was booked or submitted. The Pakistan route uses the same application, so the same
structure is expected there; only the option texts differ.

## What the live site does

### Flow
1. `/login`: email + password on one page, with a Cloudflare Turnstile box that passes on its
   own in a normal browser.
2. Same URL, second step: a one-time password sent by email.
3. `/dashboard`: "Start New Booking". The button exists twice in the page; one copy is hidden.
4. `/application-detail`: three dropdowns, then the slot message.

### The booking page
| Dropdown | Angular control | Options seen (Indonesia) |
|---|---|---|
| Choose your Application Centre | `mat-select[formcontrolname=centerCode]` | Netherlands Bali `BZI`, Netherlands Jakarta `CGK`, Netherlands Surabaya `SUB`, plus three "Jakarta for Ambon / Makassar / Medan" entries |
| Choose your appointment category | second `mat-select` | CARRIBEAN VISA `9`, Schengen `07052024` |
| Choose your sub-category | `mat-select[formcontrolname=visaCategoryCode]` | Schengen Short Stay `07052024sss` |

- Each `mat-option` has an `id` equal to the code in the table. Selecting by id is exact;
  selecting by text is not ("Jakarta" matches four centres).
- The accessible labels of the category and sub-category dropdowns are swapped in the page,
  so find them by position or control name, never by label.
- When a sub-category list has one entry the page selects it by itself.
- Changing the centre keeps the category if the new centre offers it (Jakarta → Surabaya) and
  clears it if not (→ Bali).
- A full-page loader overlay (`.ngx-overlay`) covers the form while a request is running.
- Result: `div.alert.form-info`, text such as
  `Earliest available slot for 1,2,3,4,5 Applicants is : 20-11-2026`. Seen today:
  Jakarta 20-11-2026, Surabaya 23-11-2026. Pakistan/Tourism showed a no-slot message.

### Requests behind it (host `lift-api.vfsglobal.com`)
- pick centre → `GET /master/visacategory/nld/idn/<centre>/en-US`
- pick category → `GET /master/subvisacategory/nld/idn/<centre>/<category>/en-US`
- sub-category set → `POST /appointment/CheckIsSlotAvailable`

The scraper should read the page, not call these itself.

### Session
- The login lives inside the one tab. A fresh page load of `/dashboard` in another tab of the
  same browser went straight to `/login`, while the original tab kept working.
- So **any reload or direct URL load logs the scraper out**, and every login costs a person a
  password entry, a Cloudflare check and an emailed code.
- Re-picking the centre in the open page fires a fresh `CheckIsSlotAvailable`. A new check
  needs no reload.
- Session lifetime is not known yet. It has to be measured.

### Which browsers VFS accepts
| Setup | Result |
|---|---|
| Normal Chrome, person at the keyboard | works (Indonesia and Pakistan) |
| Playwright with its bundled Chromium | Pakistan: `{"code": "403201"}`. Indonesia: page shell loads, login form never appears |
| Playwright starting the installed Chrome (`BROWSER_CHANNEL=chrome`) | Indonesia: same as above, no login form |
| Script attached to a Chrome that a person started | not tested |

VFS recognises a browser that is started by an automation tool and withholds the login form.
`BROWSER_CHANNEL=chrome` does not help.

## What is wrong with the current scraper for VFS
- `check()` loads `start_url` on every cycle. On VFS that is a logout every cycle.
- Steps pick options by visible text.
- Nothing waits for the loader overlay.
- It launches the browser through Playwright, which VFS refuses.

## Plan

1. **A person logs in. Always.** Email, password, Cloudflare and the emailed code are done by
   hand. The script never types credentials on VFS and never touches the check or the code.
2. **One tab, kept open, never reloaded.** After login the script clicks "Start New Booking"
   once and stays on `/application-detail`.
3. **A check is a re-pick.** Each cycle: open the centre dropdown, pick the centre by id, pick
   the category by id if it was cleared, let the sub-category auto-select or pick it by id,
   wait for the loader to go away, read `div.alert.form-info`.
4. **Slow and bounded.** One check per route every 15 to 30 minutes. One account, one tab.
   Several centres share that budget in rotation; they do not multiply it.
5. **Stop on the first bad sign.** Login page, session-expired page, 403, 429, "Too Many
   Requests", a Cloudflare page, or an unreadable result: stop checking, send the operator an
   alert, wait for a person. No automatic retry and no automatic re-login.
6. **Read only.** Never click Continue. Never open steps 2 to 5 of the booking wizard.
7. **Alerts.** Keep the existing confirm-twice logic. Alert when the earliest date appears or
   moves earlier.
8. **Measure the session.** Log login time and the time of the first logged-out page, so the
   operator knows how often a re-login is needed.

## Open decision: how the script reaches the page

VFS withholds the page from automation-started browsers, so steps 2 to 5 need a browser VFS
treats as a normal one. The only technical route is to attach the script to a Chrome window
that a person started and logged in to. That is a deliberate step around VFS's automation
check, it is against VFS's terms of use, and it is untested. It is the owner's decision.

The alternative with no such step: a person keeps the tab open and re-picks the centre by
hand, and this tool handles only parsing a pasted result, history and alerts.

## Limits of this plan
No design can promise the account stays unbanned. VFS forbids automated access and can change
its checks at any time. The plan lowers the risk by making the script behave like one slow
person in one tab and by stopping at the first warning.
