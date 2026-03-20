#!/usr/bin/env python3
"""
PIVOT GUI — Flask-based web interface
Run with:  python gui.py
Then open: http://localhost:5000
"""

import argparse
import io
import json
import queue
import sys
import threading
import webbrowser
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

from modules.config import load as _load_config
from modules import reporter as _reporter

_load_config()

# ── stdout capture ────────────────────────────────────────────────────────────

_output_queue: queue.Queue = queue.Queue()
_run_lock = threading.Lock()


class _QueueWriter(io.TextIOBase):
    """Redirect plain-text output into the SSE queue."""
    def write(self, text: str) -> int:
        if text and text.strip():
            # Strip ANSI escape codes for clean display
            import re
            clean = re.sub(r"\x1b\[[0-9;]*[mK]", "", text)
            if clean.strip():
                _output_queue.put(clean.rstrip())
        return len(text)

    def flush(self):
        pass


# ── Flask app ─────────────────────────────────────────────────────────────────

app = Flask(__name__, template_folder="gui/templates")
app.config["SECRET_KEY"] = "pivot-osint-gui"

MODULES_META = {
    "person":    {"label": "Person",        "icon": "👤", "fields": [
        {"id": "name",  "label": "Namn",        "type": "text",    "placeholder": "Anna Svensson", "required": True},
        {"id": "city",  "label": "Stad",         "type": "text",    "placeholder": "Stockholm"},
        {"id": "pnr",   "label": "Personnummer", "type": "text",    "placeholder": "ÅÅMMDD-XXXX"},
    ]},
    "folkbok":   {"label": "Folkbokföring", "icon": "🏛️", "fields": [
        {"id": "name",  "label": "Namn",        "type": "text",    "placeholder": "Anna Svensson", "required": True},
        {"id": "city",  "label": "Stad",         "type": "text",    "placeholder": "Stockholm"},
        {"id": "pnr",   "label": "Personnummer", "type": "text",    "placeholder": "ÅÅMMDD-XXXX"},
    ]},
    "company":   {"label": "Företag",       "icon": "🏢", "fields": [
        {"id": "name",  "label": "Företagsnamn", "type": "text",   "placeholder": "Volvo"},
        {"id": "orgnr", "label": "Org.nr",       "type": "text",   "placeholder": "556012-5790"},
    ]},
    "phone":     {"label": "Telefon",       "icon": "📞", "fields": [
        {"id": "phone", "label": "Telefonnummer", "type": "tel",   "placeholder": "070-123 45 67", "required": True},
    ]},
    "email":     {"label": "E-post",        "icon": "📧", "fields": [
        {"id": "email", "label": "E-postadress", "type": "email",  "placeholder": "user@example.se", "required": True},
    ]},
    "domain":    {"label": "Domän",         "icon": "🌐", "fields": [
        {"id": "domain","label": "Domännamn",     "type": "text",   "placeholder": "example.se", "required": True},
    ]},
    "social":    {"label": "Sociala medier","icon": "📱", "fields": [
        {"id": "username","label": "Användarnamn","type": "text",   "placeholder": "annasvens", "required": True},
        {"id": "threads", "label": "Trådar",      "type": "number", "placeholder": "10"},
    ]},
    "github":    {"label": "GitHub",        "icon": "🐙", "fields": [
        {"id": "username","label": "Användarnamn","type": "text",   "placeholder": "johndoe"},
        {"id": "email",   "label": "E-post",      "type": "email",  "placeholder": "user@example.se"},
        {"id": "name",    "label": "Namn",         "type": "text",   "placeholder": "John Doe"},
    ]},
    "wayback":   {"label": "Wayback",       "icon": "⏳", "fields": [
        {"id": "url",   "label": "URL / Domän",   "type": "text",   "placeholder": "example.se", "required": True},
        {"id": "limit", "label": "Max snapshots", "type": "number", "placeholder": "30"},
    ]},
    "harvest":   {"label": "E-post skörd",  "icon": "🌾", "fields": [
        {"id": "domain","label": "Domännamn",     "type": "text",   "placeholder": "volvo.com", "required": True},
        {"id": "deep",  "label": "Djup skanning", "type": "checkbox"},
    ]},
    "paste":     {"label": "Paste Search",  "icon": "📋", "fields": [
        {"id": "target","label": "E-post / Telefon","type": "text", "placeholder": "user@example.se", "required": True},
    ]},
    "vehicle":   {"label": "Fordon",        "icon": "🚗", "fields": [
        {"id": "plate", "label": "Registreringsnummer","type": "text","placeholder": "ABC123", "required": True},
    ]},
    "news":      {"label": "Nyheter",       "icon": "📰", "fields": [
        {"id": "query", "label": "Sökord",        "type": "text",   "placeholder": "Anna Svensson Stockholm", "required": True},
    ]},
    "geo":       {"label": "Geolokalisering","icon": "📍", "fields": [
        {"id": "address","label": "Adress",       "type": "text",   "placeholder": "Storgatan 1, Stockholm"},
        {"id": "lat",    "label": "Latitud",      "type": "text",   "placeholder": "59.3293"},
        {"id": "lon",    "label": "Longitud",     "type": "text",   "placeholder": "18.0686"},
    ]},
    "correlate": {"label": "Korrelera",     "icon": "🔗", "fields": [
        {"id": "target","label": "Telefon / E-post","type": "text", "placeholder": "070-123 45 67", "required": True},
    ]},
}


@app.route("/")
def index():
    return render_template("index.html", modules=MODULES_META)


@app.route("/modules")
def modules_list():
    return jsonify({k: {"label": v["label"], "icon": v["icon"], "fields": v["fields"]}
                    for k, v in MODULES_META.items()})


def _run_module_in_thread(module: str, form: dict):
    """Run a PIVOT module, capturing output and reporter findings."""
    _reporter.reset()
    _reporter.init(target=form.get("name") or form.get("target") or
                          form.get("email") or form.get("phone") or
                          form.get("domain") or module)

    ns = argparse.Namespace(
        module=module,
        no_disclaimer=True,
        output=None,
        graph=None,
        proxy="",
        # person / folkbok
        name=form.get("name", ""),
        city=form.get("city", ""),
        pnr=form.get("pnr", ""),
        # company
        orgnr=form.get("orgnr", ""),
        # phone
        phone=form.get("phone", ""),
        # email
        email=form.get("email", ""),
        # domain / harvest / wayback
        domain=form.get("domain", ""),
        deep="deep" in form,
        url=form.get("url", ""),
        limit=int(form.get("limit") or 30),
        # social / github
        username=form.get("username", ""),
        threads=int(form.get("threads") or 10),
        # paste / correlate
        target=form.get("target", ""),
        # news
        query=form.get("query", ""),
        # geo
        address=form.get("address", ""),
        lat=form.get("lat", ""),
        lon=form.get("lon", ""),
        # vehicle
        plate=form.get("plate", ""),
    )

    # Redirect stdout so we capture rich/print output
    old_stdout = sys.stdout
    sys.stdout = _QueueWriter()
    try:
        from main import run_module
        run_module(ns)
    except SystemExit:
        pass
    except Exception as exc:
        _output_queue.put(f"[ERROR] {exc}")
    finally:
        sys.stdout = old_stdout
        _output_queue.put("__DONE__")


@app.route("/run", methods=["POST"])
def run_scan():
    if not _run_lock.acquire(blocking=False):
        return jsonify({"error": "Scan already running — please wait."}), 429

    data = request.json or {}
    module = data.get("module", "")
    form = data.get("form", {})

    if module not in MODULES_META:
        _run_lock.release()
        return jsonify({"error": f"Unknown module: {module}"}), 400

    # Clear stale queue items
    while not _output_queue.empty():
        _output_queue.get_nowait()

    thread = threading.Thread(target=_run_module_in_thread, args=(module, form), daemon=True)
    thread.start()
    return jsonify({"status": "started"})


@app.route("/stream")
def stream():
    """SSE endpoint — streams output lines to the browser."""
    def generate():
        while True:
            try:
                line = _output_queue.get(timeout=60)
            except queue.Empty:
                yield "data: __TIMEOUT__\n\n"
                break
            if line == "__DONE__":
                # Send reporter findings as JSON then close
                findings = _reporter.get_all() if _reporter.active() else []
                payload = json.dumps(findings)
                yield f"data: __FINDINGS__{payload}\n\n"
                yield "data: __DONE__\n\n"
                _run_lock.release()
                break
            else:
                escaped = line.replace("\n", " ")
                yield f"data: {escaped}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})


@app.route("/save", methods=["POST"])
def save_report():
    data = request.json or {}
    fmt = data.get("format", "html")
    filename = data.get("filename", f"pivot_report.{fmt}")
    path = Path("C:/Users/Admin/Documents/sweden-osint") / filename
    if _reporter.active():
        _reporter.save(str(path))
        return jsonify({"ok": True, "path": str(path)})
    return jsonify({"error": "No active report data"}), 400


if __name__ == "__main__":
    url = "http://localhost:5000"
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"\n  PIVOT GUI  {url}\n  Ctrl+C to stop\n")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
