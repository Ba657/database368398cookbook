import math
import os
import re
import sqlite3
from contextlib import contextmanager

from flask import Flask, jsonify, request

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

DB = os.environ.get("DB_PATH", "messages.db")
ADMIN_KEY = os.environ.get("ADMIN_KEY", "bi_orange_admin_2026")
MAX_TEXT = 200_000
PAGE_SIZE = 1000
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
            "rot REAL NOT NULL, color TEXT NOT NULL, "
            "deleted INTEGER NOT NULL DEFAULT 0, "
            "rev INTEGER NOT NULL DEFAULT 0)"
        )
        cols = {r[1] for r in conn.execute("PRAGMA table_info(notes)").fetchall()}
        if "deleted" not in cols:
            conn.execute("ALTER TABLE notes ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0")
        if "rev" not in cols:
            conn.execute("ALTER TABLE notes ADD COLUMN rev INTEGER NOT NULL DEFAULT 0")
            conn.execute("UPDATE notes SET rev = id WHERE rev = 0")
        yield conn
        conn.commit()
    finally:
        conn.close()


def next_rev(conn):
    row = conn.execute("SELECT COALESCE(MAX(rev), 0) + 1 FROM notes").fetchone()
    return row[0]


def is_admin():
    return bool(ADMIN_KEY) and request.headers.get("X-Admin-Key") == ADMIN_KEY


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
            "SELECT id, uid, text, x, y, rot, color, deleted, rev FROM notes "
            "WHERE rev > ? ORDER BY rev LIMIT ?",
            (after, PAGE_SIZE),
        ).fetchall()
    keys = ("id", "uid", "text", "x", "y", "rot", "color", "deleted", "rev")
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
        rev = next_rev(conn)
        conn.execute(
            "INSERT OR IGNORE INTO notes (uid, text, x, y, rot, color, deleted, rev) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
            (
                uid,
                text[:MAX_TEXT],
                num(data.get("x")),
                num(data.get("y")),
                num(data.get("rot"), 0.0, 30.0),
                color,
                rev,
            ),
        )
    return jsonify(ok=True, rev=rev)


@app.route("/notes/<uid>", methods=["PATCH"])
def move_note(uid):
    if not is_admin():
        return jsonify(ok=False, error="unauthorized"), 403
    data = request.get_json(silent=True) or {}
    with db() as conn:
        rev = next_rev(conn)
        cur = conn.execute(
            "UPDATE notes SET x = ?, y = ?, rev = ? WHERE uid = ? AND deleted = 0",
            (num(data.get("x")), num(data.get("y")), rev, uid[:64]),
        )
        if cur.rowcount == 0:
            return jsonify(ok=False, error="not found"), 404
    return jsonify(ok=True, rev=rev)


@app.route("/notes/<uid>", methods=["DELETE"])
def delete_note(uid):
    if not is_admin():
        return jsonify(ok=False, error="unauthorized"), 403
    with db() as conn:
        rev = next_rev(conn)
        cur = conn.execute(
            "UPDATE notes SET deleted = 1, text = '', rev = ? WHERE uid = ?",
            (rev, uid[:64]),
        )
        if cur.rowcount == 0:
            return jsonify(ok=False, error="not found"), 404
    return jsonify(ok=True, rev=rev)


@app.route("/notes", methods=["DELETE"])
def clear_notes():
    if not is_admin():
        return jsonify(ok=False, error="unauthorized"), 403
    with db() as conn:
        rev = next_rev(conn)
        conn.execute("UPDATE notes SET deleted = 1, text = '', rev = ?", (rev,))
    return jsonify(ok=True, rev=rev)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
