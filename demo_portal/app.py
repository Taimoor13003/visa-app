"""Local stand-in for the VFS and BLS portals, for demos from anywhere.

The real portals only answer from Pakistan (BLS shows "Access Denied … outside the permitted
country"). This small site copies the parts of their flow the monitor relies on:

  BLS-style:  /bls/account/login  →  /bls/appointment/newappointment
              (Location / Visa Type / Category dropdowns + Submit)  →  slot message
  VFS-style:  /vfs/login  →  /vfs/dashboard ("Start New Booking")  →  /vfs/booking
              (Centre / Category / Sub-category dropdowns)  →  slot message

The monitor itself is unchanged: it types the login from .env, runs the config steps, and parses
the page text exactly as it would on the live portals (same scrapers/*.py patterns).

Operator panel at /admin: flip a route between "no slots" and "slot available on <date>" while the
dashboard is running, or log everyone out to show the "Login needed" handling.

Run on its own:   python demo_portal/app.py          (port 8010)
Or together:      python app.py --demo               (starts this + the dashboard with config.demo.yaml)
"""
from __future__ import annotations

import os
import secrets
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, redirect, render_template_string, request, session, url_for

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

PORT = int(os.getenv("DEMO_PORTAL_PORT", "8010"))
DEMO_EMAIL = os.getenv("DEMO_EMAIL", "demo@example.com")
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "demo1234")

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# ------------------------------------------------------------------ demo state (operator-controlled)
DEFAULT_DATE = (date.today() + timedelta(days=14)).strftime("%d-%m-%Y")
STATE = {
    "bls": {"available": False, "date": DEFAULT_DATE, "times": "09:00 AM, 09:30 AM, 11:15 AM"},
    "vfs": {"available": False, "date": DEFAULT_DATE, "times": ""},
}
LOGIN_EPOCH = 0  # bump to invalidate every session ("log everyone out")

BLS_CITIES = ["Islamabad", "Karachi", "Lahore"]
BLS_VISA_TYPES = ["Schengen", "National"]
BLS_CATEGORIES = ["Tourist", "Business", "Family", "Student"]
VFS_CENTRES = ["Islamabad", "Karachi", "Lahore"]
VFS_CATEGORIES = ["Short Stay", "Long Stay"]
VFS_SUBCATEGORIES = ["Tourism", "Business", "Family visit"]


def logged_in(portal: str) -> bool:
    return session.get(f"{portal}_user") is not None and session.get("epoch") == LOGIN_EPOCH


def do_login(portal: str, after: str):
    error = ""
    if request.method == "POST":
        email, pw = request.form.get("email", "").strip(), request.form.get("password", "")
        if email.lower() == DEMO_EMAIL.lower() and pw == DEMO_PASSWORD:
            session[f"{portal}_user"], session["epoch"] = email, LOGIN_EPOCH
            return redirect(after)
        error = "Invalid email or password."
    return render_template_string(LOGIN_HTML, portal=portal, error=error,
                                  brand="BLS International — Spain visa (demo)" if portal == "bls"
                                  else "VFS Global — Netherlands visa (demo)")


# ------------------------------------------------------------------ BLS-style portal
@app.route("/bls/account/login", methods=["GET", "POST"])
def bls_login():
    return do_login("bls", url_for("bls_new"))


@app.route("/bls/appointment/newappointment", methods=["GET", "POST"])
def bls_new():
    if not logged_in("bls"):
        return redirect(url_for("bls_login"))
    result = None
    if request.method == "POST":
        st = STATE["bls"]
        result = ({"available": True, "date": st["date"],
                   "times": [t.strip() for t in st["times"].split(",") if t.strip()]}
                  if st["available"] else {"available": False})
    return render_template_string(BLS_HTML, cities=BLS_CITIES, types=BLS_VISA_TYPES,
                                  cats=BLS_CATEGORIES, form=request.form, result=result)


@app.get("/bls/account/logout")
def bls_logout():
    session.pop("bls_user", None)
    return redirect(url_for("bls_login"))


# ------------------------------------------------------------------ VFS-style portal
@app.route("/vfs/login", methods=["GET", "POST"])
def vfs_login():
    return do_login("vfs", url_for("vfs_dashboard"))


@app.get("/vfs/dashboard")
def vfs_dashboard():
    if not logged_in("vfs"):
        return redirect(url_for("vfs_login"))
    return render_template_string(VFS_DASH_HTML)


@app.get("/vfs/booking")
def vfs_booking():
    if not logged_in("vfs"):
        return redirect(url_for("vfs_login"))
    sel = {k: request.args.get(k, "") for k in ("centre", "category", "sub")}
    result = None
    if all(sel.values()):
        st = STATE["vfs"]
        result = {"available": st["available"], "date": st["date"], "category": sel["sub"]}
    return render_template_string(VFS_BOOK_HTML, centres=VFS_CENTRES, cats=VFS_CATEGORIES,
                                  subs=VFS_SUBCATEGORIES, sel=sel, result=result)


@app.get("/vfs/logout")
def vfs_logout():
    session.pop("vfs_user", None)
    return redirect(url_for("vfs_login"))


# ------------------------------------------------------------------ operator panel
@app.route("/admin", methods=["GET", "POST"])
def admin():
    global LOGIN_EPOCH
    msg = ""
    if request.method == "POST":
        if request.form.get("action") == "logout_all":
            LOGIN_EPOCH += 1
            msg = "All portal sessions invalidated — the next check will report 'login required'."
        else:
            for portal in ("bls", "vfs"):
                st = STATE[portal]
                st["available"] = request.form.get(f"{portal}_mode") == "available"
                st["date"] = request.form.get(f"{portal}_date", st["date"]).strip() or st["date"]
                if portal == "bls":
                    st["times"] = request.form.get("bls_times", st["times"])
            msg = "Saved. The monitor will see this on its next check (press 'Check now' on the dashboard)."
    return render_template_string(ADMIN_HTML, state=STATE, msg=msg, email=DEMO_EMAIL)


@app.get("/")
def index():
    return redirect(url_for("admin"))


# ------------------------------------------------------------------ templates
BASE_CSS = """
<style>
body{margin:0;font:15px/1.5 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;background:#f1f3f6;color:#222}
.top{background:#0b3d91;color:#fff;padding:14px 28px;font-weight:700;font-size:18px;display:flex;justify-content:space-between}
.top a{color:#cfe0ff;font-weight:400;font-size:13px}
.wrap{max-width:720px;margin:36px auto;background:#fff;padding:28px 32px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,.08)}
h1{font-size:22px;margin:0 0 18px}
label{display:block;font-weight:600;margin:14px 0 6px}
input,select{width:100%;padding:9px 10px;border:1px solid #c6ccd6;border-radius:4px;font:inherit;background:#fff}
button{margin-top:20px;background:#0b3d91;color:#fff;border:0;padding:11px 22px;border-radius:4px;font:inherit;font-weight:600;cursor:pointer}
.err{color:#b00020;margin-top:10px}
.msg{margin-top:24px;padding:16px;border-radius:6px;font-size:16px}
.ok{background:#e6f6ea;border:1px solid #7bc88f;color:#115c2b}
.none{background:#fff4e5;border:1px solid #f3c27a;color:#7a4b00}
.small{color:#666;font-size:13px}
</style>
"""

LOGIN_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>{{ brand }} – Login</title>""" + BASE_CSS + """</head>
<body><div class="top"><span>{{ brand }}</span></div>
<div class="wrap"><h1>Sign in to your account</h1>
<form method="post">
<label for="email">Email address</label><input id="email" name="email" type="email" required>
<label for="password">Password</label><input id="password" name="password" type="password" required>
<button type="submit">Sign in</button>
{% if error %}<div class="err alert-danger">{{ error }}</div>{% endif %}
</form>
<p class="small">Demo portal — there is no real account behind this page.</p>
</div></body></html>"""

BLS_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Book an appointment</title>""" + BASE_CSS + """</head>
<body><div class="top"><span>BLS International — Spain visa (demo)</span><a href="/bls/account/logout">Logout</a></div>
<div class="wrap"><h1>New appointment</h1>
<form method="post">
<label for="location">Location</label>
<select id="location" name="location"><option value="">-- select --</option>
{% for c in cities %}<option {% if form.get('location')==c %}selected{% endif %}>{{ c }}</option>{% endfor %}</select>
<label for="visatype">Visa Type</label>
<select id="visatype" name="visatype"><option value="">-- select --</option>
{% for t in types %}<option {% if form.get('visatype')==t %}selected{% endif %}>{{ t }}</option>{% endfor %}</select>
<label for="category">Category</label>
<select id="category" name="category"><option value="">-- select --</option>
{% for t in cats %}<option {% if form.get('category')==t %}selected{% endif %}>{{ t }}</option>{% endfor %}</select>
<button type="submit">Submit</button>
</form>
{% if result %}
  {% if result.available %}
  <div class="msg ok">Earliest available slot: {{ result.date }}<br>
  <span class="small">Available times: {{ result.times|join(', ') }}</span></div>
  {% else %}
  <div class="msg none">Currently, no slots are available for the selected category. Please try again later.</div>
  {% endif %}
{% endif %}
</div></body></html>"""

VFS_DASH_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Dashboard</title>""" + BASE_CSS + """</head>
<body><div class="top"><span>VFS Global — Netherlands visa (demo)</span><a href="/vfs/logout">Logout</a></div>
<div class="wrap"><h1>Welcome back</h1>
<p>You have no upcoming appointments.</p>
<a href="/vfs/booking"><button type="button">Start New Booking</button></a>
</div></body></html>"""

VFS_BOOK_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Book an appointment</title>""" + BASE_CSS + """</head>
<body><div class="top"><span>VFS Global — Netherlands visa (demo)</span><a href="/vfs/logout">Logout</a></div>
<div class="wrap"><h1>Your appointment details</h1>
<form method="get" id="f">
<label for="centre">Application Centre</label>
<select id="centre" name="centre" onchange="f.submit()"><option value="">-- select --</option>
{% for c in centres %}<option {% if sel.centre==c %}selected{% endif %}>{{ c }}</option>{% endfor %}</select>
<label for="category">Appointment category</label>
<select id="category" name="category" onchange="f.submit()"><option value="">-- select --</option>
{% for c in cats %}<option {% if sel.category==c %}selected{% endif %}>{{ c }}</option>{% endfor %}</select>
<label for="sub">Sub-category</label>
<select id="sub" name="sub" onchange="f.submit()"><option value="">-- select --</option>
{% for c in subs %}<option {% if sel.sub==c %}selected{% endif %}>{{ c }}</option>{% endfor %}</select>
</form>
{% if result %}
  {% if result.available %}
  <div class="msg ok">Earliest available slot for {{ result.category }} is : {{ result.date }}</div>
  {% else %}
  <div class="msg none">No appointment slots are currently available. Please try again later.</div>
  {% endif %}
{% endif %}
</div></body></html>"""

ADMIN_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Demo portal – operator panel</title>""" + BASE_CSS + """
<style>.top{background:#333}.grid{display:grid;grid-template-columns:1fr 1fr;gap:24px}fieldset{border:1px solid #ddd;border-radius:6px;padding:12px 16px}
legend{font-weight:700}.radio{display:flex;gap:8px;align-items:center;margin:8px 0;font-weight:400}.radio input{width:auto}</style></head>
<body><div class="top"><span>Demo portal — operator panel</span></div>
<div class="wrap">
<h1>Control what the portals show</h1>
<p class="small">Login for both portals: <b>{{ email }}</b> (password is DEMO_PASSWORD in .env).
Portals: <a href="/bls/account/login" target="_blank">BLS-style</a> · <a href="/vfs/login" target="_blank">VFS-style</a></p>
{% if msg %}<div class="msg ok">{{ msg }}</div>{% endif %}
<form method="post"><div class="grid">
<fieldset><legend>BLS – Spain (Islamabad)</legend>
<label class="radio"><input type="radio" name="bls_mode" value="none" {% if not state.bls.available %}checked{% endif %}> No slots available</label>
<label class="radio"><input type="radio" name="bls_mode" value="available" {% if state.bls.available %}checked{% endif %}> Slot available</label>
<label for="bls_date">Date (DD-MM-YYYY)</label><input id="bls_date" name="bls_date" value="{{ state.bls.date }}">
<label for="bls_times">Times (comma-separated)</label><input id="bls_times" name="bls_times" value="{{ state.bls.times }}">
</fieldset>
<fieldset><legend>VFS – Netherlands (Islamabad)</legend>
<label class="radio"><input type="radio" name="vfs_mode" value="none" {% if not state.vfs.available %}checked{% endif %}> No slots available</label>
<label class="radio"><input type="radio" name="vfs_mode" value="available" {% if state.vfs.available %}checked{% endif %}> Slot available</label>
<label for="vfs_date">Date (DD-MM-YYYY)</label><input id="vfs_date" name="vfs_date" value="{{ state.vfs.date }}">
</fieldset>
</div>
<button type="submit" name="action" value="save">Save</button>
<button type="submit" name="action" value="logout_all" style="background:#8a1c1c;margin-left:10px">Log everyone out (simulate session expiry)</button>
</form>
</div></body></html>"""


if __name__ == "__main__":
    print(f"Demo portal on http://127.0.0.1:{PORT}/admin  (login: {DEMO_EMAIL})")
    app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)
