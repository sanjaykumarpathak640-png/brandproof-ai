"""SQLite storage for Brand Memory, submissions, decisions, audit log and Proof Certificates."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import date, datetime, timezone

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "brandproof.db"))
_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS facts (
  id TEXT PRIMARY KEY, key TEXT, label TEXT, value TEXT, unit TEXT,
  valid_from TEXT, valid_to TEXT, source TEXT, status TEXT DEFAULT 'approved', added_in INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS rules (
  id TEXT PRIMARY KEY, category TEXT, severity TEXT, title TEXT, description TEXT, source TEXT, enabled INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS terms (id INTEGER PRIMARY KEY AUTOINCREMENT, avoid TEXT, prefer TEXT, note TEXT, status TEXT DEFAULT 'approved');
CREATE TABLE IF NOT EXISTS palette (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, hex TEXT);
CREATE TABLE IF NOT EXISTS brand_versions (version INTEGER PRIMARY KEY, note TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, payload TEXT, source TEXT, snippet TEXT, status TEXT DEFAULT 'pending', created_at TEXT);
CREATE TABLE IF NOT EXISTS submissions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, channel TEXT, creator TEXT, goal TEXT, ai_generated INTEGER,
  status TEXT, risk INTEGER, current_version INTEGER, demo INTEGER DEFAULT 0, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, submission_id INTEGER, version INTEGER, text TEXT, findings TEXT,
  risk INTEGER, note TEXT, brand_version INTEGER, image TEXT, image_info TEXT, ai_info TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, submission_id INTEGER, version INTEGER, finding_key TEXT, rule_id TEXT,
  action TEXT, by_role TEXT, by_name TEXT, reason TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, submission_id INTEGER, actor TEXT, role TEXT, action TEXT, detail TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS comments (
  id INTEGER PRIMARY KEY AUTOINCREMENT, submission_id INTEGER, author TEXT, role TEXT, text TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS certificates (
  id INTEGER PRIMARY KEY AUTOINCREMENT, submission_id INTEGER, version INTEGER, payload TEXT, content_hash TEXT,
  prev_hash TEXT, cert_hash TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, role TEXT, ease INTEGER, trust INTEGER, useful INTEGER,
  liked TEXT, improve TEXT, created_at TEXT);
"""


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today() -> str:
    return date.today().isoformat()


_conn = None


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
    return _conn


def q(sql, args=()):
    with _lock:
        return [dict(r) for r in conn().execute(sql, args).fetchall()]


def one(sql, args=()):
    r = q(sql, args)
    return r[0] if r else None


def ex(sql, args=()):
    with _lock:
        c = conn()
        cur = c.execute(sql, args)
        c.commit()
        return cur.lastrowid


def get_meta(key, default=None):
    r = one("SELECT value FROM meta WHERE key=?", (key,))
    return json.loads(r["value"]) if r else default


def set_meta(key, value):
    ex("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))


def brand_version() -> int:
    r = one("SELECT MAX(version) v FROM brand_versions")
    return (r and r["v"]) or 1


def bump_brand(note: str) -> int:
    v = brand_version() + 1
    ex("INSERT INTO brand_versions(version,note,created_at) VALUES(?,?,?)", (v, note, now()))
    return v


def brand_snapshot() -> dict:
    meta = {k: get_meta(k) for k in ("brand_name", "tone", "confidential_terms", "voice_profile", "brand_book")}
    return {
        "meta": meta,
        "version": brand_version(),
        "today": today(),
        "facts": q("SELECT * FROM facts ORDER BY id"),
        "rules": q("SELECT * FROM rules ORDER BY id"),
        "terms": q("SELECT * FROM terms ORDER BY id"),
        "palette": q("SELECT * FROM palette ORDER BY id"),
    }


def log(submission_id, actor, role, action, detail="", when=None):
    ex("INSERT INTO events(submission_id,actor,role,action,detail,created_at) VALUES(?,?,?,?,?,?)",
       (submission_id, actor, role, action, detail, when or now()))
