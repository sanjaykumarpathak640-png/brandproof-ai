"""Storage layer for BrandProof AI.

Works with SQLite (local development, zero setup) and PostgreSQL (production,
persistent). Set DATABASE_URL=postgres://... to use Postgres; otherwise a SQLite
file at DB_PATH is used. Every business table carries an org_id so each
workspace's data is isolated.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from datetime import date, datetime, timezone

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "brandproof.db"))
IS_PG = DATABASE_URL.startswith(("postgres://", "postgresql://"))
_lock = threading.RLock()
_conn = None

PK = "SERIAL PRIMARY KEY" if IS_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS orgs (id {PK}, name TEXT NOT NULL, kind TEXT NOT NULL, created_at TEXT, last_active TEXT);
CREATE TABLE IF NOT EXISTS users (id {PK}, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL, pw_hash TEXT NOT NULL, created_at TEXT);
CREATE TABLE IF NOT EXISTS memberships (id {PK}, org_id INTEGER NOT NULL, user_id INTEGER NOT NULL, roles TEXT NOT NULL, created_at TEXT, UNIQUE(org_id, user_id));
CREATE TABLE IF NOT EXISTS invites (id {PK}, code TEXT UNIQUE NOT NULL, org_id INTEGER NOT NULL, roles TEXT NOT NULL, email TEXT, created_by INTEGER,
  used_by INTEGER, created_at TEXT, used_at TEXT);
CREATE TABLE IF NOT EXISTS sessions (id {PK}, token_hash TEXT UNIQUE NOT NULL, user_id INTEGER, org_id INTEGER NOT NULL, demo INTEGER DEFAULT 0,
  created_at TEXT, expires_at TEXT);
CREATE TABLE IF NOT EXISTS meta (id {PK}, org_id INTEGER NOT NULL, key TEXT NOT NULL, value TEXT, UNIQUE(org_id, key));
CREATE TABLE IF NOT EXISTS facts (pk {PK}, org_id INTEGER NOT NULL, id TEXT NOT NULL, key TEXT, label TEXT, value TEXT, unit TEXT,
  valid_from TEXT, valid_to TEXT, source TEXT, status TEXT DEFAULT 'approved', added_in INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS rules (pk {PK}, org_id INTEGER NOT NULL, id TEXT NOT NULL, category TEXT, severity TEXT, title TEXT, description TEXT,
  source TEXT, enabled INTEGER DEFAULT 1, UNIQUE(org_id, id));
CREATE TABLE IF NOT EXISTS terms (id {PK}, org_id INTEGER NOT NULL, avoid TEXT, prefer TEXT, note TEXT, status TEXT DEFAULT 'approved');
CREATE TABLE IF NOT EXISTS palette (id {PK}, org_id INTEGER NOT NULL, name TEXT, hex TEXT);
CREATE TABLE IF NOT EXISTS assets (id {PK}, org_id INTEGER NOT NULL, kind TEXT, name TEXT, data TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS brand_versions (id {PK}, org_id INTEGER NOT NULL, version INTEGER NOT NULL, note TEXT, created_at TEXT, UNIQUE(org_id, version));
CREATE TABLE IF NOT EXISTS candidates (id {PK}, org_id INTEGER NOT NULL, kind TEXT, payload TEXT, source TEXT, snippet TEXT, method TEXT,
  status TEXT DEFAULT 'pending', created_at TEXT);
CREATE TABLE IF NOT EXISTS submissions (id {PK}, org_id INTEGER NOT NULL, title TEXT, channel TEXT, creator TEXT, creator_user_id INTEGER, goal TEXT,
  ai_generated INTEGER, status TEXT, risk INTEGER, current_version INTEGER, demo INTEGER DEFAULT 0, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS versions (id {PK}, org_id INTEGER NOT NULL, submission_id INTEGER, version INTEGER, text TEXT, findings TEXT, risk INTEGER,
  note TEXT, brand_version INTEGER, image TEXT, image_info TEXT, ai_info TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS decisions (id {PK}, org_id INTEGER NOT NULL, submission_id INTEGER, version INTEGER, finding_key TEXT, rule_id TEXT,
  action TEXT, by_role TEXT, by_name TEXT, by_user_id INTEGER, reason TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS events (id {PK}, org_id INTEGER NOT NULL, submission_id INTEGER, actor TEXT, actor_user_id INTEGER, role TEXT, action TEXT,
  detail TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS comments (id {PK}, org_id INTEGER NOT NULL, submission_id INTEGER, author TEXT, role TEXT, text TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS certificates (id {PK}, org_id INTEGER NOT NULL, number INTEGER, submission_id INTEGER, version INTEGER, payload TEXT,
  content_hash TEXT, prev_hash TEXT, cert_hash TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS feedback (id {PK}, org_id INTEGER, name TEXT, role TEXT, ease INTEGER, trust INTEGER, useful INTEGER,
  liked TEXT, improve TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS ai_cache (id {PK}, key TEXT UNIQUE NOT NULL, value TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS benchmark_runs (id {PK}, mode TEXT, status TEXT, result TEXT, created_at TEXT, finished_at TEXT);
CREATE INDEX IF NOT EXISTS ix_sub_org ON submissions(org_id);
CREATE INDEX IF NOT EXISTS ix_ver_sub ON versions(org_id, submission_id);
CREATE INDEX IF NOT EXISTS ix_dec_sub ON decisions(org_id, submission_id);
CREATE INDEX IF NOT EXISTS ix_evt_sub ON events(org_id, submission_id);
CREATE INDEX IF NOT EXISTS ix_facts_org ON facts(org_id);
"""

ORG_TABLES = ["meta", "facts", "rules", "terms", "palette", "assets", "brand_versions", "candidates", "submissions", "versions",
              "decisions", "events", "comments", "certificates", "memberships", "invites", "sessions"]


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today() -> str:
    return date.today().isoformat()


def _connect():
    if IS_PG:
        import psycopg
        from psycopg.rows import dict_row
        url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        c = psycopg.connect(url, autocommit=True, row_factory=dict_row, connect_timeout=15)
        with c.cursor() as cur:
            for stmt in [s.strip() for s in SCHEMA.split(";") if s.strip()]:
                cur.execute(stmt)
        return c
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(SCHEMA)
    return c


def conn():
    global _conn
    if _conn is None:
        _conn = _connect()
    return _conn


def _sql(sql: str) -> str:
    return sql.replace("?", "%s") if IS_PG else sql


def _run(fn):
    """Run a DB call; on a dropped Postgres connection, reconnect once and retry."""
    global _conn
    with _lock:
        try:
            return fn(conn())
        except Exception as e:  # noqa: BLE001
            if IS_PG and e.__class__.__name__ in ("OperationalError", "InterfaceError"):
                try:
                    _conn.close()
                except Exception:  # noqa: BLE001
                    pass
                _conn = None
                time.sleep(0.5)
                return fn(conn())
            raise


def q(sql, args=()):
    def f(c):
        if IS_PG:
            with c.cursor() as cur:
                cur.execute(_sql(sql), args)
                return [dict(r) for r in cur.fetchall()] if cur.description else []
        return [dict(r) for r in c.execute(sql, args).fetchall()]
    return _run(f)


def one(sql, args=()):
    r = q(sql, args)
    return r[0] if r else None


def ex(sql, args=(), returning: str | None = "id"):
    """Execute a write. For INSERTs returns the new row id (column given by `returning`)."""
    def f(c):
        if IS_PG:
            s = _sql(sql)
            is_insert = s.lstrip().upper().startswith("INSERT")
            if is_insert and returning:
                s += f" RETURNING {returning}"
            with c.cursor() as cur:
                cur.execute(s, args)
                if is_insert and returning:
                    r = cur.fetchone()
                    return r[returning] if r else None
                return cur.rowcount
        cur = c.execute(sql, args)
        c.commit()
        return cur.lastrowid if sql.lstrip().upper().startswith("INSERT") else cur.rowcount
    return _run(f)


# ---------------------------------------------------------------- org-scoped helpers

def get_meta(org, key, default=None):
    r = one("SELECT value FROM meta WHERE org_id=? AND key=?", (org, key))
    return json.loads(r["value"]) if r else default


def set_meta(org, key, value):
    ex("INSERT INTO meta(org_id,key,value) VALUES(?,?,?) ON CONFLICT(org_id,key) DO UPDATE SET value=excluded.value",
       (org, key, json.dumps(value)), returning=None)


def brand_version(org) -> int:
    r = one("SELECT MAX(version) AS v FROM brand_versions WHERE org_id=?", (org,))
    return (r and r["v"]) or 1


def bump_brand(org, note: str) -> int:
    v = brand_version(org) + 1
    ex("INSERT INTO brand_versions(org_id,version,note,created_at) VALUES(?,?,?,?)", (org, v, note, now()))
    return v


def brand_snapshot(org) -> dict:
    meta = {k: get_meta(org, k) for k in ("brand_name", "tone", "confidential_terms", "voice_profile", "brand_book")}
    meta["confidential_terms"] = meta.get("confidential_terms") or []
    logo = one("SELECT id,name FROM assets WHERE org_id=? AND kind='logo' ORDER BY id DESC LIMIT 1", (org,))
    return {
        "org_id": org,
        "meta": meta,
        "version": brand_version(org),
        "today": today(),
        "facts": q("SELECT * FROM facts WHERE org_id=? ORDER BY id, valid_from", (org,)),
        "rules": q("SELECT * FROM rules WHERE org_id=? ORDER BY id", (org,)),
        "terms": q("SELECT * FROM terms WHERE org_id=? ORDER BY id", (org,)),
        "palette": q("SELECT * FROM palette WHERE org_id=? ORDER BY id", (org,)),
        "logo": logo,
    }


def logo_data(org) -> str | None:
    r = one("SELECT data FROM assets WHERE org_id=? AND kind='logo' ORDER BY id DESC LIMIT 1", (org,))
    return r["data"] if r else None


def log(org, submission_id, actor, role, action, detail="", when=None, user_id=None):
    ex("INSERT INTO events(org_id,submission_id,actor,actor_user_id,role,action,detail,created_at) VALUES(?,?,?,?,?,?,?,?)",
       (org, submission_id, actor, user_id, role, action, detail, when or now()))


def delete_org(org):
    for t in ORG_TABLES:
        ex(f"DELETE FROM {t} WHERE org_id=?", (org,))
    ex("DELETE FROM orgs WHERE id=?", (org,))


def cache_get(key):
    r = one("SELECT value FROM ai_cache WHERE key=?", (key,))
    return json.loads(r["value"]) if r else None


def cache_set(key, value):
    ex("INSERT INTO ai_cache(key,value,created_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
       (key, json.dumps(value), now()), returning=None)
