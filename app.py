"""Dashboard web app.  Run:  python app.py   then open http://127.0.0.1:8000

  python app.py --demo            also starts the local stand-in portal (demo_portal/app.py, port 8010)
                                  and uses config.demo.yaml, so the demo works from any country.
  python app.py --host 0.0.0.0    lets another machine open the dashboard (e.g. over Tailscale) when
                                  the monitor runs on a laptop in Pakistan and the demo is presented
                                  from elsewhere.  --port 8001 changes the port.
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")  # before the imports below read their settings

_args = argparse.ArgumentParser()
_args.add_argument("--demo", action="store_true", help="run against the local demo portal")
_args.add_argument("--config", help="monitors config (default config.yaml, or config.demo.yaml with --demo)")
_args.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"), help="0.0.0.0 to allow other machines")
_args.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
_opts = _args.parse_args()
if hasattr(sys.stdout, "reconfigure"):  # Windows consoles: never crash on ✅ / → in log lines
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if _opts.config or _opts.demo:
    os.environ["VISA_CONFIG"] = _opts.config or str(Path(__file__).parent / "config.demo.yaml")
if _opts.demo:
    sys.path.insert(0, str(Path(__file__).parent / "demo_portal"))
    import app as demo_portal  # demo_portal/app.py  # noqa: E402
    threading.Thread(target=lambda: demo_portal.app.run(host="127.0.0.1", port=demo_portal.PORT,
                                                        debug=False, threaded=True, use_reloader=False),
                     daemon=True, name="demo-portal").start()
    print(f"Demo portal: http://127.0.0.1:{demo_portal.PORT}/admin   (login {demo_portal.DEMO_EMAIL})")

from flask import Flask, abort, jsonify, send_from_directory  # noqa: E402

import store  # noqa: E402
from engine import Engine

ROOT = Path(__file__).parent
app = Flask(__name__, static_folder=str(ROOT / "static"))
engine = Engine()


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/state")
def state():
    return jsonify({**engine.snapshot(), "history": store.recent(100)})


@app.post("/api/routes/<int:idx>/<action>")
def route_action(idx: int, action: str):
    if action not in {"start", "stop", "check"} or not 0 <= idx < len(engine.routes):
        abort(404)
    engine.command(action, idx)
    return jsonify(ok=True)


@app.get("/screenshots/<path:name>")
def screenshots(name: str):
    return send_from_directory(ROOT / "screenshots", name)


if __name__ == "__main__":
    print(f"Dashboard: http://{'127.0.0.1' if _opts.host == '0.0.0.0' else _opts.host}:{_opts.port}"
          + ("   (also reachable from other machines)" if _opts.host == "0.0.0.0" else ""))
    app.run(host=_opts.host, port=_opts.port, debug=False, threaded=True)
