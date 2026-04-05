#!/usr/bin/env python3
"""
Flask + SQLite: lobbies, geofence, spelkonfiguration, resultat per lobby, sparad status per spelare.
Kör: python3 server.py [--port 8080]

Miljö (valfritt, för den som driftsätter bakom proxy):
  PASKTIPSET_PUBLIC_ORIGIN  t.ex. https://example.com  — klienten får rätt länkar om servern ser annan host än användarna.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import secrets
import sqlite3
import time
import uuid
from typing import Any
from urllib.parse import urlparse

from flask import Flask, abort, jsonify, request, send_from_directory
from flask_cors import CORS

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "data", "pasktipset.db")

# Global nollställning av äldre resultatlista (utan lobby)
RESET_PASSWORD = os.environ.get("PASKTIPSET_RESET_PASSWORD", "arrangor2026")

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

app = Flask(__name__)
# Statisk frontend (t.ex. GitHub Pages) kan anropa API på annan domän
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": "*",
            "allow_headers": ["Content-Type", "X-Creator-Token"],
            "methods": ["GET", "POST", "OPTIONS"],
        }
    },
)


def _normalize_public_origin(raw: str) -> str | None:
    """Valfri publik bas-URL (t.ex. bakom omvänd proxy). Endast scheme + host."""
    u = (raw or "").strip()
    if not u:
        return None
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    p = urlparse(u)
    if not p.netloc:
        return None
    return f"{p.scheme}://{p.netloc}"


def normalize_password(s: str) -> str:
    return (s or "").strip().lower()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Avstånd i meter mellan två WGS84-punkter."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


def gen_lobby_code(conn: sqlite3.Connection) -> str:
    for _ in range(50):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        cur = conn.execute("SELECT 1 FROM lobbies WHERE code = ?", (code,))
        if cur.fetchone() is None:
            return code
    return secrets.token_hex(4).upper()[:6]


def init_db() -> None:
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lobbies (
                id TEXT PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                creator_token TEXT NOT NULL,
                center_lat REAL NOT NULL,
                center_lng REAL NOT NULL,
                radius_m REAL NOT NULL,
                config_json TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS player_states (
                lobby_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                state_json TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (lobby_id, user_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS submissions (
                id TEXT PRIMARY KEY,
                lobby_id TEXT,
                user_id TEXT,
                name TEXT NOT NULL,
                correct1to10 INTEGER NOT NULL,
                km_answer REAL,
                km_error REAL,
                submitted_at INTEGER NOT NULL
            )
            """
        )
        _migrate_submissions_columns(conn)
        conn.commit()


def _migrate_submissions_columns(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(submissions)")
    names = {r[1] for r in cur.fetchall()}
    if "lobby_id" not in names:
        conn.execute("ALTER TABLE submissions ADD COLUMN lobby_id TEXT")
    if "user_id" not in names:
        conn.execute("ALTER TABLE submissions ADD COLUMN user_id TEXT")


def _get_lobby_by_code(conn: sqlite3.Connection, code: str) -> sqlite3.Row | None:
    cur = conn.execute(
        "SELECT * FROM lobbies WHERE code = ?", (normalize_password(code).upper(),)
    )
    return cur.fetchone()


def _parse_config(row: sqlite3.Row) -> dict[str, Any]:
    return json.loads(row["config_json"])


def _config_for_client(cfg: dict[str, Any]) -> dict[str, Any]:
    """Skicka konfiguration till klient; joinSecret skickas aldrig (endast i QR-länk)."""
    out = dict(cfg)
    out.pop("joinSecret", None)
    return out


def _join_secret_ok(cfg: dict[str, Any], provided: str) -> bool:
    cfg_secret = str(cfg.get("joinSecret") or "").strip()
    p = (provided or "").strip()
    return bool(cfg_secret) and bool(p) and secrets.compare_digest(p, cfg_secret)


def sort_entries(entries: list[dict]) -> list[dict]:
    def err_key(e: dict) -> float:
        ke = e.get("kmError")
        if ke is None or (isinstance(ke, float) and math.isnan(ke)):
            return float("inf")
        return float(ke)

    return sorted(
        entries,
        key=lambda e: (
            -int(e.get("correct1to10") or 0),
            err_key(e),
        ),
    )


def row_to_submission(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"],
        "name": r["name"],
        "correct1to10": r["correct1to10"],
        "kmAnswer": r["km_answer"],
        "kmError": r["km_error"],
        "submittedAt": r["submitted_at"],
        "userId": r["user_id"],
    }


# --- Legacy global submissions (lobby_id IS NULL) ---


@app.route("/api/submissions", methods=["GET", "POST", "OPTIONS"])
def api_submissions_legacy():
    if request.method == "OPTIONS":
        return ("", 204)
    if request.method == "GET":
        with get_conn() as conn:
            cur = conn.execute(
                """
                SELECT id, name, correct1to10, km_answer, km_error, submitted_at, user_id, lobby_id
                FROM submissions WHERE lobby_id IS NULL
                """
            )
            rows = []
            for r in cur.fetchall():
                rows.append(
                    {
                        "id": r["id"],
                        "name": r["name"],
                        "correct1to10": r["correct1to10"],
                        "kmAnswer": r["km_answer"],
                        "kmError": r["km_error"],
                        "submittedAt": r["submitted_at"],
                    }
                )
        return jsonify(sort_entries(rows))
    data = request.get_json(force=True, silent=True) or {}
    sid = str(data.get("id") or uuid.uuid4())
    name = str(data.get("name") or "Anonym").strip()[:200] or "Anonym"
    try:
        correct = int(data.get("correct1to10", 0))
    except (TypeError, ValueError):
        correct = 0
    correct = max(0, min(200, correct))
    km_answer = data.get("kmAnswer")
    km_error = data.get("kmError")
    if km_answer is not None:
        try:
            km_answer = float(km_answer)
        except (TypeError, ValueError):
            km_answer = None
    if km_error is not None:
        try:
            km_error = float(km_error)
        except (TypeError, ValueError):
            km_error = None
    submitted_at = int(data.get("submittedAt") or time.time() * 1000)
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO submissions (id, lobby_id, user_id, name, correct1to10, km_answer, km_error, submitted_at)
            VALUES (?, NULL, NULL, ?, ?, ?, ?, ?)
            """,
            (sid, name, correct, km_answer, km_error, submitted_at),
        )
        conn.commit()
    return jsonify({"ok": True, "id": sid}), 201


@app.route("/api/submissions/reset", methods=["POST", "OPTIONS"])
def api_submissions_reset_legacy():
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True, silent=True) or {}
    pwd = normalize_password(str(data.get("password") or ""))
    if not pwd or normalize_password(RESET_PASSWORD) != pwd:
        return jsonify({"ok": False, "error": "Fel lösenord."}), 403
    with get_conn() as conn:
        conn.execute("DELETE FROM submissions WHERE lobby_id IS NULL")
        conn.commit()
    return jsonify({"ok": True})


# --- Lobbies ---


@app.route("/api/config", methods=["GET", "OPTIONS"])
def api_config():
    """Klienten kan läsa valfri publik origin (miljö PASKTIPSET_PUBLIC_ORIGIN)."""
    if request.method == "OPTIONS":
        return ("", 204)
    origin = _normalize_public_origin(os.environ.get("PASKTIPSET_PUBLIC_ORIGIN", ""))
    return jsonify({"publicOrigin": origin})


@app.route("/api/lobbies", methods=["POST", "OPTIONS"])
def api_lobbies_create():
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True, silent=True) or {}
    title = str(data.get("title") or "Ny bana").strip()[:200] or "Ny bana"
    try:
        center_lat = float(data.get("centerLat"))
        center_lng = float(data.get("centerLng"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Ogiltig position."}), 400
    try:
        radius_m = float(data.get("radiusM") or 500)
    except (TypeError, ValueError):
        radius_m = 500.0
    radius_m = max(50.0, min(500_000.0, radius_m))

    cfg = data.get("config")
    if not isinstance(cfg, dict):
        return jsonify({"ok": False, "error": "Saknar config."}), 400
    cfg_json = json.dumps(cfg, ensure_ascii=False)
    if len(cfg_json) > 1_500_000:
        return jsonify({"ok": False, "error": "Konfigurationen är för stor."}), 400

    lid = str(uuid.uuid4())
    creator_token = secrets.token_urlsafe(32)
    now = int(time.time() * 1000)

    with get_conn() as conn:
        code = gen_lobby_code(conn)
        conn.execute(
            """
            INSERT INTO lobbies (id, code, title, creator_token, center_lat, center_lng, radius_m, config_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lid,
                code,
                title,
                creator_token,
                center_lat,
                center_lng,
                radius_m,
                cfg_json,
                now,
            ),
        )
        conn.commit()

    return jsonify({"ok": True, "lobbyId": lid, "code": code, "creatorToken": creator_token}), 201


@app.route("/api/lobbies/<code>", methods=["GET", "OPTIONS"])
def api_lobby_public(code: str):
    if request.method == "OPTIONS":
        return ("", 204)
    code_u = normalize_password(code).upper()
    with get_conn() as conn:
        row = _get_lobby_by_code(conn, code_u)
        if row is None:
            return jsonify({"ok": False, "error": "Lobby hittades inte."}), 404
    return jsonify(
        {
            "ok": True,
            "title": row["title"],
            "centerLat": row["center_lat"],
            "centerLng": row["center_lng"],
            "radiusM": row["radius_m"],
            "code": row["code"],
        }
    )


def _geo_ok(row: sqlite3.Row, lat: float, lng: float) -> bool:
    d = haversine_m(lat, lng, row["center_lat"], row["center_lng"])
    return d <= float(row["radius_m"])


def _lat_lng_and_skip_geo(data: dict, row: sqlite3.Row) -> tuple[float, float, bool]:
    """
    Parsar lat/lng från JSON. Om skipLocation är True eller koordinater saknas:
    lobbycentrum + skip_geo=True (ingen områdeskontroll).
    Annars riktiga koordinater + skip_geo=False (geostängsel om inte värd/spårlösen).
    """
    if data.get("skipLocation") is True:
        return float(row["center_lat"]), float(row["center_lng"]), True
    raw_lat = data.get("lat")
    raw_lng = data.get("lng")
    if raw_lat is None or raw_lng is None:
        return float(row["center_lat"]), float(row["center_lng"]), True
    try:
        lat = float(raw_lat)
        lng = float(raw_lng)
    except (TypeError, ValueError):
        return float(row["center_lat"]), float(row["center_lng"]), True
    return lat, lng, False


@app.route("/api/lobbies/<code>/join", methods=["POST", "OPTIONS"])
def api_lobby_join(code: str):
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True, silent=True) or {}

    creator_token = str(data.get("creatorToken") or "").strip()
    join_secret_req = str(data.get("joinSecret") or "").strip()
    code_u = normalize_password(code).upper()
    cfg = None
    title = None
    code_val = None
    with get_conn() as conn:
        row = _get_lobby_by_code(conn, code_u)
        if row is None:
            return jsonify({"ok": False, "error": "Lobby hittades inte."}), 404
        lat, lng, skip_geo = _lat_lng_and_skip_geo(data, row)
        raw_cfg = _parse_config(row)
        is_host = bool(creator_token) and secrets.compare_digest(
            creator_token, row["creator_token"]
        )
        join_ok = _join_secret_ok(raw_cfg, join_secret_req)
        if not is_host and not join_ok and not skip_geo and not _geo_ok(row, lat, lng):
            return jsonify({"ok": False, "error": "Du är utanför spelområdet."}), 403
        cfg = _config_for_client(raw_cfg)
        title = row["title"]
        code_val = row["code"]

    uid = str(data.get("userId") or "").strip()
    if not uid:
        uid = str(uuid.uuid4())
    return jsonify(
        {
            "ok": True,
            "userId": uid,
            "config": cfg,
            "title": title,
            "lobbyCode": code_val,
        }
    )


@app.route("/api/lobbies/<code>/state", methods=["GET", "POST", "OPTIONS"])
def api_lobby_state(code: str):
    if request.method == "OPTIONS":
        return ("", 204)
    code_u = normalize_password(code).upper()
    with get_conn() as conn:
        row = _get_lobby_by_code(conn, code_u)
        if row is None:
            return jsonify({"ok": False, "error": "Lobby hittades inte."}), 404
        lid = row["id"]

    if request.method == "GET":
        uid = request.args.get("userId", "").strip()
        if not uid:
            return jsonify({"ok": False, "error": "userId saknas."}), 400
        with get_conn() as conn:
            cur = conn.execute(
                "SELECT state_json FROM player_states WHERE lobby_id = ? AND user_id = ?",
                (lid, uid),
            )
            r = cur.fetchone()
        if r is None:
            return jsonify({"ok": True, "state": None})
        return jsonify({"ok": True, "state": json.loads(r["state_json"])})

    data = request.get_json(force=True, silent=True) or {}
    uid = str(data.get("userId") or "").strip()
    if not uid:
        return jsonify({"ok": False, "error": "userId saknas."}), 400
    st = data.get("state")
    if st is None:
        return jsonify({"ok": False, "error": "state saknas."}), 400
    creator_token = str(data.get("creatorToken") or "").strip()
    join_secret_req = str(data.get("joinSecret") or "").strip()

    with get_conn() as conn:
        row = _get_lobby_by_code(conn, code_u)
        if row is None:
            return jsonify({"ok": False, "error": "Lobby hittades inte."}), 404
        lat, lng, skip_geo = _lat_lng_and_skip_geo(data, row)
        raw_cfg = _parse_config(row)
        is_host = bool(creator_token) and secrets.compare_digest(
            creator_token, row["creator_token"]
        )
        join_ok = _join_secret_ok(raw_cfg, join_secret_req)
        if not is_host and not join_ok and not skip_geo and not _geo_ok(row, lat, lng):
            return jsonify({"ok": False, "error": "Utanför spelområdet."}), 403
        conn.execute(
            """
            INSERT INTO player_states (lobby_id, user_id, state_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(lobby_id, user_id) DO UPDATE SET
              state_json = excluded.state_json,
              updated_at = excluded.updated_at
            """,
            (lid, uid, json.dumps(st, ensure_ascii=False), int(time.time() * 1000)),
        )
        conn.commit()
    return jsonify({"ok": True})


@app.route("/api/lobbies/<code>/submissions", methods=["GET", "POST", "OPTIONS"])
def api_lobby_submissions(code: str):
    if request.method == "OPTIONS":
        return ("", 204)
    code_u = normalize_password(code).upper()
    with get_conn() as conn:
        row = _get_lobby_by_code(conn, code_u)
        if row is None:
            return jsonify({"ok": False, "error": "Lobby hittades inte."}), 404
        lid = row["id"]

    if request.method == "GET":
        with get_conn() as conn:
            cur = conn.execute(
                """
                SELECT id, name, correct1to10, km_answer, km_error, submitted_at, user_id
                FROM submissions WHERE lobby_id = ?
                """,
                (lid,),
            )
            rows = [row_to_submission(r) for r in cur.fetchall()]
        return jsonify(sort_entries(rows))

    data = request.get_json(force=True, silent=True) or {}
    creator_token = str(data.get("creatorToken") or "").strip()
    join_secret_req = str(data.get("joinSecret") or "").strip()

    with get_conn() as conn:
        row = _get_lobby_by_code(conn, code_u)
        if row is None:
            return jsonify({"ok": False, "error": "Lobby hittades inte."}), 404
        lat, lng, skip_geo = _lat_lng_and_skip_geo(data, row)
        raw_cfg = _parse_config(row)
        is_host = bool(creator_token) and secrets.compare_digest(
            creator_token, row["creator_token"]
        )
        join_ok = _join_secret_ok(raw_cfg, join_secret_req)
        if not is_host and not join_ok and not skip_geo and not _geo_ok(row, lat, lng):
            return jsonify({"ok": False, "error": "Utanför spelområdet."}), 403

    sid = str(data.get("id") or uuid.uuid4())
    uid = str(data.get("userId") or "").strip() or None
    name = str(data.get("name") or "Anonym").strip()[:200] or "Anonym"
    try:
        correct = int(data.get("correct1to10", 0))
    except (TypeError, ValueError):
        correct = 0
    correct = max(0, min(200, correct))
    km_answer = data.get("kmAnswer")
    km_error = data.get("kmError")
    if km_answer is not None:
        try:
            km_answer = float(km_answer)
        except (TypeError, ValueError):
            km_answer = None
    if km_error is not None:
        try:
            km_error = float(km_error)
        except (TypeError, ValueError):
            km_error = None
    submitted_at = int(data.get("submittedAt") or time.time() * 1000)

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO submissions (id, lobby_id, user_id, name, correct1to10, km_answer, km_error, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (sid, lid, uid, name, correct, km_answer, km_error, submitted_at),
        )
        conn.commit()
    return jsonify({"ok": True, "id": sid}), 201


@app.route("/api/lobbies/<code>/admin/players", methods=["GET", "OPTIONS"])
def api_lobby_admin_players(code: str):
    if request.method == "OPTIONS":
        return ("", 204)
    token = request.headers.get("X-Creator-Token", "").strip()
    code_u = normalize_password(code).upper()
    with get_conn() as conn:
        row = _get_lobby_by_code(conn, code_u)
        if row is None:
            return jsonify({"ok": False, "error": "Lobby hittades inte."}), 404
        if not secrets.compare_digest(token, row["creator_token"]):
            return jsonify({"ok": False, "error": "Ogiltig behörighet."}), 403
        lid = row["id"]
        cur = conn.execute(
            "SELECT user_id, updated_at FROM player_states WHERE lobby_id = ? ORDER BY updated_at DESC",
            (lid,),
        )
        states = [{"userId": r["user_id"], "updatedAt": r["updated_at"]} for r in cur.fetchall()]
        cur = conn.execute(
            """
            SELECT user_id, name, submitted_at, id FROM submissions
            WHERE lobby_id = ? ORDER BY submitted_at DESC
            """,
            (lid,),
        )
        subs = [
            {
                "userId": r["user_id"],
                "name": r["name"],
                "submittedAt": r["submitted_at"],
                "submissionId": r["id"],
            }
            for r in cur.fetchall()
        ]
    return jsonify({"ok": True, "playerStates": states, "submissions": subs})


@app.route("/api/lobbies/<code>/admin/clear", methods=["POST", "OPTIONS"])
def api_lobby_admin_clear(code: str):
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True, silent=True) or {}
    token = str(data.get("creatorToken") or request.headers.get("X-Creator-Token", "")).strip()
    scope = str(data.get("scope") or "all")
    target_uid = str(data.get("userId") or "").strip()

    code_u = normalize_password(code).upper()
    with get_conn() as conn:
        row = _get_lobby_by_code(conn, code_u)
        if row is None:
            return jsonify({"ok": False, "error": "Lobby hittades inte."}), 404
        if not secrets.compare_digest(token, row["creator_token"]):
            return jsonify({"ok": False, "error": "Ogiltig behörighet."}), 403
        lid = row["id"]

        if scope == "user" and target_uid:
            conn.execute(
                "DELETE FROM player_states WHERE lobby_id = ? AND user_id = ?",
                (lid, target_uid),
            )
            conn.execute(
                "DELETE FROM submissions WHERE lobby_id = ? AND user_id = ?",
                (lid, target_uid),
            )
        elif scope == "submission":
            sub_id = str(data.get("submissionId") or "").strip()
            if sub_id:
                conn.execute(
                    "DELETE FROM submissions WHERE lobby_id = ? AND id = ?",
                    (lid, sub_id),
                )
        elif scope == "all":
            conn.execute("DELETE FROM player_states WHERE lobby_id = ?", (lid,))
            conn.execute("DELETE FROM submissions WHERE lobby_id = ?", (lid,))
        else:
            return jsonify({"ok": False, "error": "Ogiltig scope."}), 400
        conn.commit()
    return jsonify({"ok": True})


def _safe_static(filename: str) -> None:
    if ".." in filename or filename.startswith("/"):
        abort(404)
    parts = filename.replace("\\", "/").split("/")
    if parts[0] in ("data", "scripts", ".git"):
        abort(404)
    base = parts[-1] if parts else ""
    if base.endswith(".py") or base in ("requirements.txt", "ngrok.yml", ".env", ".gitignore"):
        abort(404)
    full = os.path.normpath(os.path.join(ROOT, filename))
    if not full.startswith(os.path.normpath(ROOT + os.sep)):
        abort(404)
    if not os.path.isfile(full):
        abort(404)


@app.route("/")
def index():
    return send_from_directory(ROOT, "index.html")


@app.route("/<path:filename>")
def static_files(filename: str):
    if filename.startswith("api/"):
        abort(404)
    _safe_static(filename)
    return send_from_directory(ROOT, filename)


def main() -> None:
    parser = argparse.ArgumentParser(description="Påsktips: lobbies + SQLite")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8080")),
    )
    parser.add_argument(
        "--host",
        default=os.environ.get(
            "HOST",
            "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1",
        ),
    )
    args = parser.parse_args()
    print(f"Server: http://{args.host}:{args.port}/  (databas: {DB_PATH})")
    app.run(host=args.host, port=args.port, threaded=True, use_reloader=False)


# Körs även vid gunicorn (då körs inte __main__) — SQLite skapas/uppdateras här.
init_db()

if __name__ == "__main__":
    main()
