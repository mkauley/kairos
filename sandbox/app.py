"""Kairos sandbox — Flask front end for validating the parser + Calendar API.

Throwaway quality on purpose. Run locally:

    cd sandbox
    pip install -r requirements.txt
    python app.py           # http://127.0.0.1:5000

Routes:
    GET  /            the one-page UI
    POST /parse       {text} -> parsed preview (no calendar write)
    POST /create      {text} or {title,start,end} -> inserts the event
    GET  /auth        force the Google OAuth flow now
"""

from __future__ import annotations

from datetime import datetime

from flask import Flask, jsonify, render_template, request

import calendar_client
from parser import parse

app = Flask(__name__)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _preview(text: str) -> dict:
    r = parse(text)
    return {
        "title": r["title"],
        "start": _iso(r["start"]),
        "end": _iso(r["end"]),
        "start_pretty": r["start"].strftime("%a %b %-d, %Y %-I:%M %p"),
        "end_pretty": r["end"].strftime("%-I:%M %p"),
        "matched": r["matched"],
    }


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/parse")
def parse_route():
    text = (request.json or {}).get("text", "")
    if not text.strip():
        return jsonify(error="empty input"), 400
    return jsonify(_preview(text))


@app.post("/create")
def create_route():
    data = request.json or {}
    text = data.get("text", "")

    if data.get("title") and data.get("start") and data.get("end"):
        title = data["title"]
        start = datetime.fromisoformat(data["start"])
        end = datetime.fromisoformat(data["end"])
    elif text.strip():
        r = parse(text)
        title, start, end = r["title"], r["start"], r["end"]
    else:
        return jsonify(error="provide text, or title+start+end"), 400

    try:
        event = calendar_client.create_event(title, start, end)
    except FileNotFoundError as e:
        return jsonify(error=str(e)), 500
    except Exception as e:  # noqa: BLE001 - sandbox: surface whatever broke
        return jsonify(error=f"{type(e).__name__}: {e}"), 502
    return jsonify(ok=True, event=event)


@app.get("/auth")
def auth_route():
    try:
        calendar_client.check_auth()
    except Exception as e:  # noqa: BLE001
        return jsonify(error=f"{type(e).__name__}: {e}"), 500
    return jsonify(ok=True)


@app.get("/whoami")
def whoami_route():
    """Which Google account/calendar are writes going to, and what's on it."""
    try:
        return jsonify(calendar_client.whoami())
    except Exception as e:  # noqa: BLE001
        return jsonify(error=f"{type(e).__name__}: {e}"), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
