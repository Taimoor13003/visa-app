# Visa Appointment Portal Compatibility Sheet — UAE & Pakistan
_Research date: 17 Nov 2026. Providers change often — every row must be re-verified on the live portal before build._

**Legend — Monitoring:** ✅ portal exists, monitorable with an applicant/operator account · ⚠️ possible but limited (waitlist / per-applicant account / service disrupted) · ❌ no portal to monitor (email lottery, no mission)
**Protection** (from public sources/user reports): VFS = account + email OTP + CAPTCHA + Cloudflare bot protection; BLS = account + OTP + CAPTCHA; RK = image CAPTCHA + waitlist; eK = e-Konsulat image CAPTCHA.

## Scraper engines needed (8)
| # | Engine | Covers (configs) |
|---|---|---|
| 1 | VFS Global (`visa.vfsglobal.com/{pak|are}/en/{iso3}/`) | UK, Canada, Australia, NZ + ~20 Schengen countries — ~46 configs |
| 2 | BLS / "Intiana" Global platform | Spain PK + UAE, Italy PK, Italy Abu Dhabi — 4 configs |
| 3 | US — usvisascheduling.com | USA from Pakistan |
| 4 | US — ais.usvisa-info.com/en-ae | USA from UAE |
| 5 | TLScontact | France from Pakistan (launched 16 Nov 2026) |
| 6 | GVCW (pk-gr.gvcworld.eu) | Greece from Pakistan |
| 7 | German RK-Termin (service2.diplo.de/rktermin) | Germany, Latvia, Slovenia from Pakistan (waitlist) |
| 8 | Polish e-Konsulat (secure.e-konsulat.gov.pl) | Poland from Pakistan + UAE |
| + | travel.state.gov Global Visa Wait Times (public page) | US "next available" per post — the only public, no-login source |

## Non-Schengen
| Destination | From | Cities | Provider | Portal | Monitoring | Notes |
|---|---|---|---|---|---|---|
| USA | PK | Islamabad, Karachi | US CGI system | usvisascheduling.com | ⚠️ | Slots visible only after DS-160 + paid MRV, per-applicant login; 48–72h lockouts for frequent logins; service disrupted Mar–Jul 2026 |
| USA | UAE | Abu Dhabi, Dubai | AIS (since May 2025) | ais.usvisa-info.com/en-ae/niv | ⚠️ | Same per-applicant account; routine visas reported unavailable Jul 2026 |
| UK | PK | Islamabad, Karachi, Lahore, Mirpur | VFS | visa.vfsglobal.com/pak/en/gbr/ | ⚠️ | Needs GOV.UK application + fee first (GWF ref) |
| UK | UAE | Dubai, Abu Dhabi | VFS (TLS→VFS 2024/25) | visa.vfsglobal.com/are/en/gbr/ | ⚠️ | Same as above |
| Canada | PK | Islamabad, Lahore, Karachi | VFS | visa.vfsglobal.com/pak/en/can/ | ⚠️ | Needs Biometric Instruction Letter |
| Canada | UAE | Dubai, Abu Dhabi | VFS | visa.vfsglobal.com/are/en/can/ | ⚠️ | Needs BIL |
| Australia | PK | Islamabad, Karachi, Lahore | VFS (ABCC) | visa.vfsglobal.com/pak/en/aus/ | ⚠️ | Needs biometrics request letter |
| Australia | UAE | Dubai, Abu Dhabi | VFS (ABCC) | visa.vfsglobal.com/are/en/aus/ | ⚠️ | Needs request letter |
| New Zealand | PK | Karachi | VFS | visa.vfsglobal.com/pak/en/nzl/ | ⚠️ | Most NZ visas online; VAC visit only if required |
| New Zealand | UAE | Dubai | VFS | visa.vfsglobal.com/are/en/nzl/ | ⚠️ | Same |

## Schengen
| Country | From | Cities | Provider | Portal | Monitoring | Notes |
|---|---|---|---|---|---|---|
| Austria | PK | ISB, LHE, KHI | VFS/Gerry's | vfs pak/aut | ✅ | |
| Austria | UAE | Dubai, Abu Dhabi | VFS | vfs are/aut | ✅ | Waitlist reported full Apr 2026 |
| Belgium | PK | ISB, LHE, KHI | VFS/Gerry's | vfs pak/bel | ✅ | Also handles Luxembourg |
| Belgium | UAE | Dubai, Abu Dhabi | VFS | vfs are/bel | ✅ | |
| Bulgaria | PK | ISB | Embassy (email) | — | ❌ | Low confidence |
| Bulgaria | UAE | Dubai, Abu Dhabi | VFS | vfs are/bgr | ✅ | |
| Croatia | PK | — | None (apply in Tehran) | — | ❌ | Islamabad facility announced, not confirmed |
| Croatia | UAE | Dubai | VFS | vfs are/hrv | ✅ | |
| Czech Rep. | PK | ISB | Embassy email lottery (last working day monthly) | — | ❌ | Random draw — nothing to monitor |
| Czech Rep. | UAE | Dubai, Abu Dhabi | VFS | vfs are/cze | ✅ | |
| Denmark | PK | ISB, LHE, KHI | VFS/Gerry's | vfs pak/dnk | ✅ | Also handles Iceland |
| Denmark | UAE | Dubai, Abu Dhabi | VFS | vfs are/dnk | ✅ | |
| Estonia | PK | via Hungary | VFS/Gerry's | vfs pak/hun | ✅ | Same portal as Hungary |
| Estonia | UAE | Dubai, Abu Dhabi | VFS | vfs are/est | ✅ | |
| Finland | PK | via Netherlands | VFS | vfs pak/nld | ✅ | Embassy closed Jun 2026 |
| Finland | UAE | Dubai, Abu Dhabi | VFS | vfs are/fin | ✅ | |
| France | PK | ISB | TLScontact | visas-fr.tlscontact.com (verify) | ✅ | Online booking started 16 Nov 2026 |
| France | UAE | Abu Dhabi | VFS (some say TLS) | vfs are/fra | ✅ | Verify provider |
| Germany | PK | ISB, KHI | RK-Termin waitlist | service2.diplo.de/rktermin | ⚠️ | Waitlist, not direct booking; also Latvia, Slovenia |
| Germany | UAE | Dubai, Abu Dhabi | VFS + waitlist | vfs are/deu | ⚠️ | Slot email valid 24h |
| Greece | PK | ISB, LHE | GVCW | pk-gr.gvcworld.eu | ✅ | New provider Jun 2026 |
| Greece | UAE | Dubai, Abu Dhabi | VFS | vfs are/grc | ✅ | |
| Hungary | PK | ISB, LHE, KHI | VFS/Gerry's | vfs pak/hun | ✅ | Also Estonia, Lithuania |
| Hungary | UAE | Dubai, Abu Dhabi | VFS | vfs are/hun | ✅ | |
| Iceland | PK | via Denmark | VFS/Gerry's | vfs pak/dnk | ✅ | |
| Iceland | UAE | via Denmark | VFS | vfs are/isl | ✅ | |
| Italy | PK | ISB, LHE, KHI, Quetta | BLS-Intiana | intianaitalyvisa.com | ✅ | Waitlist; Multan/Faisalabad closed Sep 2026 |
| Italy | UAE | Dubai / Abu Dhabi | VFS (Dubai) / BLS (Abu Dhabi) | vfs are/ita ; blsitalyvisa.com/abudhabi | ✅ | Two providers by emirate |
| Latvia | PK | via Germany | RK-Termin | service2.diplo.de/rktermin | ⚠️ | |
| Latvia | UAE | Dubai, Abu Dhabi | VFS | vfs are/lva | ✅ | |
| Liechtenstein | PK | via Switzerland | VFS/Gerry's | vfs pak/che | ✅ | |
| Liechtenstein | UAE | via Switzerland | VFS | vfs are/che | ✅ | |
| Lithuania | PK | via Hungary | VFS/Gerry's | vfs pak/hun | ⚠️ | Possibly suspended |
| Lithuania | UAE | Dubai, Abu Dhabi | VFS | vfs are/ltu | ✅ | |
| Luxembourg | PK | via Belgium | VFS/Gerry's | vfs pak/bel | ✅ | |
| Luxembourg | UAE | Dubai, Abu Dhabi | VFS | vfs are/lux | ✅ | |
| Malta | PK | — | None | — | ❌ | Apply abroad |
| Malta | UAE | Dubai, Abu Dhabi | VFS | vfs are/mlt | ✅ | |
| Netherlands | PK | ISB, KHI, LHE | VFS | vfs pak/nld | ✅ | Also Finland |
| Netherlands | UAE | Dubai, Abu Dhabi | VFS | vfs are/nld | ✅ | Paused Mar–Apr 2026 |
| Norway | PK | ISB, LHE, KHI | VFS/Gerry's | vfs pak/nor | ✅ | Resumed Mar 2026 |
| Norway | UAE | Dubai, Abu Dhabi | VFS | vfs are/nor | ✅ | Reduced capacity |
| Poland | PK | ISB | e-Konsulat | secure.e-konsulat.gov.pl | ✅ | |
| Poland | UAE | Abu Dhabi | e-Konsulat | secure.e-konsulat.gov.pl | ✅ | Order-of-registration |
| Portugal | PK | ISB (+LHE, KHI?) | VFS/Gerry's | vfs pak/prt | ✅ | |
| Portugal | UAE | Dubai, Abu Dhabi | VFS | vfs are/prt | ✅ | |
| Romania | PK | ISB | Embassy + evisa.mae.ro | evisa.mae.ro | ❌ | Low confidence |
| Romania | UAE | Dubai, Abu Dhabi | Consulate / maybe VFS | evisa.mae.ro | ❌ | Low confidence — verify |
| Slovakia | PK | via Czech | Czech email lottery | — | ❌ | |
| Slovakia | UAE | Dubai, Abu Dhabi | VFS | vfs are/svk | ✅ | |
| Slovenia | PK | via Germany | RK-Termin | service2.diplo.de/rktermin | ⚠️ | |
| Slovenia | UAE | Abu Dhabi | Embassy (email) | — | ❌ | |
| Spain | PK | ISB, LHE, KHI | BLS-Intiana | appointment.thespainvisa.com | ✅ | Slots released weekdays |
| Spain | UAE | Dubai, Abu Dhabi | BLS | uae.blsspainglobal.com | ✅ | "Self-book, no agents" verification since Jul 2026 |
| Sweden | PK | ISB | VFS | vfs pak/swe | ✅ | |
| Sweden | UAE | Dubai, Abu Dhabi | VFS | vfs are/swe | ✅ | |
| Switzerland | PK | ISB, KHI, LHE | VFS/Gerry's | vfs pak/che | ✅ | Also Liechtenstein |
| Switzerland | UAE | Dubai, Abu Dhabi | VFS | vfs are/che | ✅ | |

## Totals
- 68 destination × location combinations → **~58 monitorable**, **~10 not monitorable** (no mission / email lottery / email-only).
- Many share one portal page (represented countries), so **~45 unique portal endpoints**.
- **8 scraper engines** (+ optional public US wait-times feed).

## Key limitation
Almost every portal (VFS, BLS, US, RK-Termin, e-Konsulat) requires login and/or OTP and/or CAPTCHA. VFS terms prohibit bots and VFS publicly blocks them; US portals lock accounts for frequent logins. Fully unattended monitoring of these portals is **not possible without CAPTCHA/bot-protection bypass**, which the written spec excludes. Realistic legitimate modes: operator-assisted sessions at conservative check rates, and public data sources where they exist.
