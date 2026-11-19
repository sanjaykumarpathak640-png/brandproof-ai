"""Proof Certificates: a tamper-evident, hash-chained record of every approval (one chain per workspace)."""
from __future__ import annotations

import hashlib
import json

from . import db

GENESIS = "0" * 64


def sha(s: str | bytes) -> str:
    if isinstance(s, str):
        s = s.encode("utf-8")
    return hashlib.sha256(s).hexdigest()


def content_hash(text: str, image: str | None = None) -> str:
    return sha((text or "").strip() + ("\n[image]" + sha(image) if image else ""))


def canon(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def issue(org: int, submission: dict, version: dict, decisions: list[dict], approvers: list[dict], ai_model: str,
          demo: bool = False, when: str | None = None) -> dict:
    last = db.one("SELECT cert_hash, number FROM certificates WHERE org_id=? ORDER BY id DESC LIMIT 1", (org,))
    prev = last["cert_hash"] if last else GENESIS
    number = (last["number"] if last else 0) + 1
    ch = content_hash(version["text"], version.get("image"))
    payload = {
        "number": number,
        "workspace_id": org,
        "submission_id": submission["id"],
        "title": submission["title"],
        "channel": submission["channel"],
        "creator": submission["creator"],
        "version": version["version"],
        "content_hash": ch,
        "brand_memory_version": version.get("brand_version") or db.brand_version(org),
        "risk_at_approval": version.get("risk"),
        "decisions": [{"rule": d["rule_id"], "action": d["action"], "by": f"{d['by_name']} ({d['by_role']})", "reason": d["reason"]} for d in decisions],
        "approvers": approvers,
        "identity": "demo identities (not verified)" if demo else "verified workspace accounts",
        "ai_model": ai_model,
        "ai_generated_draft": bool(submission.get("ai_generated")),
        "issued_at": when or db.now(),
        "prev_hash": prev,
    }
    cert_hash = sha(canon(payload))
    cid = db.ex("INSERT INTO certificates(org_id,number,submission_id,version,payload,content_hash,prev_hash,cert_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (org, number, submission["id"], version["version"], canon(payload), ch, prev, cert_hash, payload["issued_at"]))
    return get(org, cid)


def _row(r):
    r["payload"] = json.loads(r["payload"])
    return r


def get(org: int, cid: int) -> dict | None:
    r = db.one("SELECT * FROM certificates WHERE id=? AND org_id=?", (cid, org))
    return _row(r) if r else None


def all_certs(org: int) -> list[dict]:
    return [_row(r) for r in db.q("SELECT * FROM certificates WHERE org_id=? ORDER BY id", (org,))]


def verify_chain(org: int) -> dict:
    prev = GENESIS
    results = []
    ok = True
    for c in all_certs(org):
        recomputed = sha(canon(c["payload"]))
        good = recomputed == c["cert_hash"] and c["payload"]["prev_hash"] == prev and c["prev_hash"] == prev
        results.append({"number": c["number"], "ok": good})
        ok = ok and good
        prev = c["cert_hash"]
    return {"ok": ok, "count": len(results), "certificates": results}


def verify_text(org: int, text: str) -> dict:
    h = content_hash(text)
    hits = [c for c in all_certs(org) if c["content_hash"] == h]
    return {"content_hash": h, "match": bool(hits),
            "certificates": [{"number": c["number"], "title": c["payload"]["title"], "issued_at": c["created_at"]} for c in hits]}
