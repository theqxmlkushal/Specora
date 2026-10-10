"""SQLite storage + tamper-evident (hash-chained) audit log."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import config


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path or config.DB_PATH)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS audit(
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            body TEXT NOT NULL,
            prev TEXT NOT NULL,
            hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS feedback(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            stars INTEGER NOT NULL,
            role TEXT,
            comment TEXT
        );
        CREATE TABLE IF NOT EXISTS time_study(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            actor TEXT,
            manual_min REAL,
            tool_min REAL,
            note TEXT
        );
        CREATE TABLE IF NOT EXISTS replies(
            vendor TEXT NOT NULL,
            req_id TEXT NOT NULL,
            answer TEXT NOT NULL,
            ts REAL NOT NULL,
            PRIMARY KEY (vendor, req_id)
        );
        """
    )
    conn.commit()


# --------------------------------------------------------------------- audit
def audit(conn: sqlite3.Connection, actor: str, action: str, payload: Dict[str, Any]) -> str:
    prev = conn.execute("SELECT hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
    prev_hash = prev[0] if prev else "GENESIS"
    body = json.dumps(
        {"t": time.time(), "actor": actor, "action": action, "payload": payload},
        sort_keys=True,
    )
    h = hashlib.sha256((prev_hash + body).encode()).hexdigest()
    conn.execute("INSERT INTO audit(body,prev,hash) VALUES (?,?,?)", (body, prev_hash, h))
    conn.commit()
    return h


def audit_rows(conn: sqlite3.Connection, limit: int = 15) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, body, prev, hash FROM audit ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    out = []
    for r in rows:
        body = json.loads(r["body"])
        out.append(
            {
                "id": r["id"],
                "t": body.get("t"),
                "actor": body.get("actor"),
                "action": body.get("action"),
                "payload": body.get("payload"),
                "hash": r["hash"],
                "prev": r["prev"],
                "body": r["body"],
            }
        )
    return out


def verify_chain(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Recompute every hash. Returns (ok, message)."""
    rows = conn.execute("SELECT id, body, prev, hash FROM audit ORDER BY id ASC").fetchall()
    prev_hash = "GENESIS"
    for r in rows:
        if r["prev"] != prev_hash:
            return False, f"Row {r['id']}: previous hash mismatch"
        h = hashlib.sha256((prev_hash + r["body"]).encode()).hexdigest()
        if h != r["hash"]:
            return False, f"Row {r['id']}: payload hash mismatch (chain broken)"
        prev_hash = r["hash"]
    if not rows:
        return True, "No audit rows yet"
    return True, f"Chain valid ✅  ({len(rows)} rows verified)"


def tamper_demo(conn: sqlite3.Connection) -> str:
    """Alter the oldest non-genesis row's payload and report the resulting failure."""
    row = conn.execute("SELECT id, body FROM audit ORDER BY id ASC LIMIT 1").fetchone()
    if not row:
        return "Nothing to tamper with yet — run an extraction first."
    payload = json.loads(row["body"])
    payload["payload"] = dict(payload.get("payload") or {}, tampered=True)
    conn.execute(
        "UPDATE audit SET body=? WHERE id=?",
        (json.dumps(payload, sort_keys=True), row["id"]),
    )
    conn.commit()
    ok, msg = verify_chain(conn)
    return msg if not ok else "Tamper not detected (unexpected)"


def reset_demo_tamper(conn: sqlite3.Connection) -> str:
    """Rebuild a clean chain is not possible after tampering; report state."""
    ok, msg = verify_chain(conn)
    return msg


# ------------------------------------------------------------------ feedback
def add_feedback(conn, stars: int, role: str, comment: str) -> None:
    conn.execute(
        "INSERT INTO feedback(ts,stars,role,comment) VALUES (?,?,?,?)",
        (time.time(), stars, role, comment),
    )
    conn.commit()


def get_feedback(conn) -> List[Dict[str, Any]]:
    rows = conn.execute("SELECT * FROM feedback ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------- time study
def add_time_study(conn, actor: str, manual_min: float, tool_min: float, note: str) -> None:
    conn.execute(
        "INSERT INTO time_study(ts,actor,manual_min,tool_min,note) VALUES (?,?,?,?,?)",
        (time.time(), actor, manual_min, tool_min, note),
    )
    conn.commit()


def get_time_study(conn) -> List[Dict[str, Any]]:
    rows = conn.execute("SELECT * FROM time_study ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------- vendor replies
def save_reply(conn, vendor: str, req_id: str, answer: str) -> None:
    conn.execute(
        "INSERT INTO replies(vendor,req_id,answer,ts) VALUES (?,?,?,?) "
        "ON CONFLICT(vendor,req_id) DO UPDATE SET answer=excluded.answer, ts=excluded.ts",
        (vendor, req_id, answer, time.time()),
    )
    conn.commit()


def get_replies(conn) -> Dict[tuple, str]:
    rows = conn.execute("SELECT vendor,req_id,answer FROM replies").fetchall()
    return {(r["vendor"], r["req_id"]): r["answer"] for r in rows}


def clear_replies(conn) -> None:
    conn.execute("DELETE FROM replies")
    conn.commit()
