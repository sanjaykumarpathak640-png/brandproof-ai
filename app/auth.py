"""Accounts, workspaces, invites, sessions and the per-request context.

- Team workspaces: real users (email + password, scrypt-hashed), memberships with
  one or more roles, invite links, HTTP-only session cookies.
- Demo workspaces: one private sandbox per visitor, pre-filled with the ABC
  Electronics demo brand; the visitor can switch between the four roles.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from . import db

ROLES = ["creator", "compliance", "reviewer", "admin"]
ROLE_LABEL = {"creator": "Creator", "compliance": "Compliance", "reviewer": "Reviewer", "admin": "Brand Admin"}
DEMO_PEOPLE = {"creator": "Riya Sharma", "compliance": "Neha Verma", "reviewer": "Kabir Singh", "admin": "Ayush (Brand Admin)"}
COOKIE = "bp_session"
SESSION_DAYS = 14
DEMO_TTL_HOURS = 48


class AuthError(Exception):
    status = 401


class Forbidden(Exception):
    status = 403


@dataclass
class Ctx:
    org_id: int
    org_name: str
    demo: bool
    role: str
    roles: list[str]
    user_id: int | None = None
    user_name: str = ""
    user_email: str = ""
    members: int = 1
    extra: dict = field(default_factory=dict)

    @property
    def actor(self) -> str:
        return DEMO_PEOPLE[self.role] if self.demo else self.user_name

    @property
    def identity(self) -> dict:
        if self.demo:
            return {"name": DEMO_PEOPLE[self.role], "role": self.role, "verified": False, "note": "demo identity"}
        return {"name": self.user_name, "email": self.user_email, "user_id": self.user_id, "role": self.role, "verified": True}


# ---------------------------------------------------------------- passwords & tokens

def hash_pw(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(h).decode()


def check_pw(pw: str, stored: str) -> bool:
    try:
        _, s, h = stored.split("$")
        calc = hashlib.scrypt(pw.encode(), salt=base64.b64decode(s), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(calc, base64.b64decode(h))
    except Exception:  # noqa: BLE001
        return False


def _tok_hash(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


def _expiry(days=SESSION_DAYS) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(microsecond=0).isoformat()


def new_session(org_id: int, user_id: int | None, demo: bool) -> str:
    token = secrets.token_urlsafe(32)
    db.ex("INSERT INTO sessions(token_hash,user_id,org_id,demo,created_at,expires_at) VALUES(?,?,?,?,?,?)",
          (_tok_hash(token), user_id, org_id, 1 if demo else 0, db.now(), _expiry(2 if demo else SESSION_DAYS)))
    return token


def end_session(token: str | None):
    if token:
        db.ex("DELETE FROM sessions WHERE token_hash=?", (_tok_hash(token),))


# ---------------------------------------------------------------- validation

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def clean_email(e: str) -> str:
    e = (e or "").strip().lower()
    if not EMAIL_RE.match(e) or len(e) > 200:
        raise Forbidden("Please enter a valid email address.")
    return e


def check_password_rules(pw: str):
    if len(pw or "") < 8:
        raise Forbidden("Password must be at least 8 characters.")
    if len(pw) > 200:
        raise Forbidden("Password is too long.")


def parse_roles(roles) -> list[str]:
    if isinstance(roles, str):
        roles = [r.strip() for r in roles.split(",")]
    out = [r for r in ROLES if r in (roles or [])]
    if not out:
        raise Forbidden("Choose at least one role.")
    return out


# ---------------------------------------------------------------- accounts

def signup(name: str, email: str, password: str, org_name: str, template: str = "demo") -> tuple[str, int]:
    from . import seed
    name = (name or "").strip()[:80]
    org_name = (org_name or "").strip()[:80]
    if not name or not org_name:
        raise Forbidden("Name and workspace name are required.")
    email = clean_email(email)
    check_password_rules(password)
    if db.one("SELECT id FROM users WHERE email=?", (email,)):
        raise Forbidden("An account with this email already exists. Please sign in.")
    uid = db.ex("INSERT INTO users(email,name,pw_hash,created_at) VALUES(?,?,?,?)", (email, name, hash_pw(password), db.now()))
    org = db.ex("INSERT INTO orgs(name,kind,created_at,last_active) VALUES(?,?,?,?)", (org_name, "team", db.now(), db.now()))
    db.ex("INSERT INTO memberships(org_id,user_id,roles,created_at) VALUES(?,?,?,?)", (org, uid, ",".join(ROLES), db.now()))
    seed.seed_org(org, with_history=False, starter=(template == "demo"))
    return new_session(org, uid, False), org


def login(email: str, password: str) -> str:
    email = (email or "").strip().lower()
    u = db.one("SELECT * FROM users WHERE email=?", (email,))
    if not u or not check_pw(password or "", u["pw_hash"]):
        raise AuthError("Wrong email or password.")
    m = db.one("SELECT org_id FROM memberships WHERE user_id=? ORDER BY id LIMIT 1", (u["id"],))
    if not m:
        raise AuthError("This account is not a member of any workspace.")
    return new_session(m["org_id"], u["id"], False)


def start_demo() -> tuple[str, int]:
    from . import seed
    cleanup_demos()
    org = db.ex("INSERT INTO orgs(name,kind,created_at,last_active) VALUES(?,?,?,?)", ("ABC Electronics (demo)", "demo", db.now(), db.now()))
    seed.seed_org(org, with_history=True, starter=True)
    return new_session(org, None, True), org


def cleanup_demos():
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=DEMO_TTL_HOURS)).replace(microsecond=0).isoformat()
    for o in db.q("SELECT id FROM orgs WHERE kind='demo' AND last_active < ?", (cutoff,)):
        db.delete_org(o["id"])
    db.ex("DELETE FROM sessions WHERE expires_at < ?", (db.now(),))


def create_invite(ctx: Ctx, roles, email: str | None = None) -> dict:
    require(ctx, "admin")
    if ctx.demo:
        raise Forbidden("Invites are available in team workspaces. Create a free workspace to invite your team.")
    roles = parse_roles(roles)
    code = secrets.token_urlsafe(9)
    db.ex("INSERT INTO invites(code,org_id,roles,email,created_by,created_at) VALUES(?,?,?,?,?,?)",
          (code, ctx.org_id, ",".join(roles), (email or "").strip().lower() or None, ctx.user_id, db.now()))
    return {"code": code, "roles": roles}


def invite_info(code: str) -> dict:
    inv = db.one("SELECT i.*, o.name AS org_name FROM invites i JOIN orgs o ON o.id=i.org_id WHERE i.code=?", (code,))
    if not inv:
        raise Forbidden("This invite link is not valid.")
    if inv["used_by"]:
        raise Forbidden("This invite link has already been used.")
    return {"org_name": inv["org_name"], "roles": inv["roles"].split(","), "email": inv["email"]}


def accept_invite(code: str, name: str, email: str, password: str) -> str:
    inv = db.one("SELECT * FROM invites WHERE code=?", (code,))
    if not inv or inv["used_by"]:
        raise Forbidden("This invite link is not valid or was already used.")
    email = clean_email(email)
    if inv["email"] and inv["email"] != email:
        raise Forbidden(f"This invite is for {inv['email']}.")
    u = db.one("SELECT * FROM users WHERE email=?", (email,))
    if u:
        if not check_pw(password or "", u["pw_hash"]):
            raise AuthError("An account with this email exists. Enter its password to join.")
        uid = u["id"]
    else:
        name = (name or "").strip()[:80]
        if not name:
            raise Forbidden("Please enter your name.")
        check_password_rules(password)
        uid = db.ex("INSERT INTO users(email,name,pw_hash,created_at) VALUES(?,?,?,?)", (email, name, hash_pw(password), db.now()))
    if not db.one("SELECT id FROM memberships WHERE org_id=? AND user_id=?", (inv["org_id"], uid)):
        db.ex("INSERT INTO memberships(org_id,user_id,roles,created_at) VALUES(?,?,?,?)", (inv["org_id"], uid, inv["roles"], db.now()))
    db.ex("UPDATE invites SET used_by=?, used_at=? WHERE id=?", (uid, db.now(), inv["id"]))
    return new_session(inv["org_id"], uid, False)


def members(ctx: Ctx) -> list[dict]:
    rows = db.q("SELECT m.user_id, m.roles, m.created_at, u.name, u.email FROM memberships m JOIN users u ON u.id=m.user_id "
                "WHERE m.org_id=? ORDER BY m.id", (ctx.org_id,))
    for r in rows:
        r["roles"] = r["roles"].split(",")
    return rows


def set_member_roles(ctx: Ctx, user_id: int, roles) -> None:
    require(ctx, "admin")
    roles = parse_roles(roles)
    if user_id == ctx.user_id and "admin" not in roles:
        others = [m for m in members(ctx) if m["user_id"] != ctx.user_id and "admin" in m["roles"]]
        if not others:
            raise Forbidden("A workspace needs at least one Brand Admin.")
    n = db.ex("UPDATE memberships SET roles=? WHERE org_id=? AND user_id=?", (",".join(roles), ctx.org_id, user_id))
    if not n:
        raise Forbidden("Member not found.")


def remove_member(ctx: Ctx, user_id: int) -> None:
    require(ctx, "admin")
    if user_id == ctx.user_id:
        raise Forbidden("You cannot remove yourself.")
    db.ex("DELETE FROM memberships WHERE org_id=? AND user_id=?", (ctx.org_id, user_id))
    db.ex("DELETE FROM sessions WHERE org_id=? AND user_id=?", (ctx.org_id, user_id))


# ---------------------------------------------------------------- request context

def context(token: str | None, acting_role: str | None) -> Ctx:
    if not token:
        raise AuthError("Please start the demo or sign in.")
    s = db.one("SELECT * FROM sessions WHERE token_hash=?", (_tok_hash(token),))
    if not s or (s["expires_at"] and s["expires_at"] < db.now()):
        raise AuthError("Your session has expired. Please start the demo again or sign in.")
    org = db.one("SELECT * FROM orgs WHERE id=?", (s["org_id"],))
    if not org:
        raise AuthError("This workspace no longer exists. Please start a new demo or sign in.")
    db.ex("UPDATE orgs SET last_active=? WHERE id=?", (db.now(), org["id"]))
    if s["demo"]:
        role = acting_role if acting_role in ROLES else "creator"
        return Ctx(org_id=org["id"], org_name=org["name"], demo=True, role=role, roles=list(ROLES))
    u = db.one("SELECT * FROM users WHERE id=?", (s["user_id"],))
    m = db.one("SELECT * FROM memberships WHERE org_id=? AND user_id=?", (org["id"], s["user_id"]))
    if not u or not m:
        raise AuthError("You are no longer a member of this workspace.")
    roles = m["roles"].split(",")
    role = acting_role if acting_role in roles else roles[0]
    n = db.one("SELECT COUNT(*) AS c FROM memberships WHERE org_id=?", (org["id"],))["c"]
    return Ctx(org_id=org["id"], org_name=org["name"], demo=False, role=role, roles=roles, user_id=u["id"],
               user_name=u["name"], user_email=u["email"], members=n)


def require(ctx: Ctx, *roles: str):
    if ctx.role not in roles:
        need = " or ".join(ROLE_LABEL[r] for r in roles)
        if ctx.demo:
            raise Forbidden(f"Switch “Acting as” to {need} to do this.")
        if not any(r in ctx.roles for r in roles):
            raise Forbidden(f"You need the {need} role in this workspace. Ask your Brand Admin.")
        raise Forbidden(f"Switch “Acting as” to {need} to do this.")
