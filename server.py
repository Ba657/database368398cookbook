import os
from flask import Flask, request, jsonify
import sqlite3

app = Flask(__name__)
DB = "messages.db"

def get_conn():
    conn = sqlite3.connect(DB)
    conn.execute("CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY, text TEXT)")
    return conn

@app.route("/posts", methods=["GET"])
def get_posts():
    with get_conn() as conn:
        rows = conn.execute("SELECT text FROM posts ORDER BY id DESC").fetchall()
    return jsonify([r[0] for r in rows])

@app.route("/posts", methods=["POST"])
def add_post():
    text = (request.get_json(silent=True) or {}).get("text", "").strip()[:500]
    if text:
        with get_conn() as conn:
            conn.execute("INSERT INTO posts (text) VALUES (?)", (text,))
    return jsonify(ok=bool(text))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
