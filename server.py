import math
import os
import re
import sqlite3
from contextlib import contextmanager

from flask import Flask, jsonify, request

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # reject requests over 2 MB

DB = os.environ.get("DB_PATH", "messages.db")
MAX_TEXT = 200_000  # characters per note (a safety net so nobody can crash the server)
PAGE_SIZE = 1000  # notes returned per request
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


@contextmanager
def db():
    conn = sqlite3.connect(DB)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS notes ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "uid TEXT UNIQUE NOT NULL, "
            "text TEXT NOT NULL, "
            "x REAL NOT NULL, y REAL NOT NULL, "
            "rot REAL NOT NULL, color TEXT NOT NULL)"
        )
        yield conn
        conn.commit()
    finally:
        conn.close()


def num(value, default=0.0, limit=1e9):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(v):
        return default
    return max(-limit, min(limit, v))


@app.route("/")
def home():
    return "Sticky board server is running."


@app.route("/notes", methods=["GET"])
def get_notes():
    after = int(num(request.args.get("after"), 0, 1e15))
    with db() as conn:
        rows = conn.execute(
            "SELECT id, uid, text, x, y, rot, color FROM notes "
            "WHERE id > ? ORDER BY id LIMIT ?",
            (after, PAGE_SIZE),
        ).fetchall()
    keys = ("id", "uid", "text", "x", "y", "rot", "color")
    return jsonify([dict(zip(keys, r)) for r in rows])


@app.route("/notes", methods=["POST"])
def add_note():
    data = request.get_json(silent=True) or {}
    text = data.get("text")
    uid = str(data.get("uid", ""))[:64]
    if not isinstance(text, str) or not text.strip() or not uid:
        return jsonify(ok=False, error="text and uid are required"), 400

    color = data.get("color")
    if not (isinstance(color, str) and COLOR_RE.match(color)):
        color = "#fff176"

    with db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO notes (uid, text, x, y, rot, color) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                uid,
                text[:MAX_TEXT],
                num(data.get("x")),
                num(data.get("y")),
                num(data.get("rot"), 0.0, 30.0),
                color,
            ),
        )
    return jsonify(ok=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
