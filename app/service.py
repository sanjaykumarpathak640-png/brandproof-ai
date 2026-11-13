"""Business logic: checks, workflow (BrandFlow), insights and brand-book import."""
from __future__ import annotations

import base64
import json
import re
from collections import Counter, defaultdict

from . import ai, certs, db, engine
from .extract import analyse_image

HIGH_GATE_CATEGORIES = {"pricing", "claims", "specs", "confidential", "warranty"}
ROLES = {"creator", "reviewer", "compliance", "admin"}


class Denied(Exception):
    pass


# ---------------------------------------------------------------- checking

def image_findings(info: dict, alt_text: str, brand: dict) -> list[dict]:
    rules = {r["id"]: r for r in brand["rules"] if r.get("enabled", 1)}
    out = []

    def mk(rid, message, metric=None, fix=None, extra=None):
        r = rules.get(rid)
        if not r:
            return
        ev = [{"ref": r["id"], "text": r["title"] + ": " + (r.get("description") or ""), "source": r.get("source", "")}]
        if extra:
            ev += extra
        out.append({"rule_id": rid, "category": r["category"], "severity": r["severity"], "title": r["title"], "quote": "",
                    "start": 0, "end": 0, "message": message, "evidence": ev, "fix": fix, "engine": "vision",
                    "metric": metric, "target": "image", "location": "Image"})

    pal = ", ".join(f"{p['name']} {p['hex']}" for p in brand["palette"])
    for c in info["off_palette"]:
        mk("R-VIS-01", f"Colour {c['hex']} covers {c['share']}% of the image and is ΔE {c['delta_e']} from the nearest brand colour "
                       f"({c['nearest']} {c['nearest_hex']}); limit ΔE {info['de_limit']:.0f}.",
           metric={"found": f"ΔE {c['delta_e']}", "limit": f"ΔE {info['de_limit']:.0f}", "swatch": c["hex"], "nearest": c["nearest_hex"]},
           extra=[{"ref": "Brand palette", "text": pal, "source": "Brand Book · Visual identity"}])
    ce = info.get("contrast_estimate")
    if ce is not None and ce < 3.0:
        mk("R-A11Y-03", f"Estimated contrast between the two main colours is {ce}:1. Text on this background may be hard to read (WCAG AA large text needs 3:1).",
           metric={"found": f"{ce}:1", "limit": "3:1"})
    if not (alt_text or "").strip():
        mk("R-A11Y-02", "The image has no alt text, so screen-reader users cannot understand it.",
           fix={"replacement": info.get("alt_suggestion") or "", "note": "Suggested alt text" + (" (AI-assisted)" if info.get("alt_ai") else ""), "target": "alt"})
    return out


def run_check(text: str, *, confidential: bool = False, use_ai: bool = True, pages=None,
              image_bytes: bytes | None = None, image_mime: str | None = None, alt_text: str = "", goal: str = "") -> dict:
    brand = db.brand_snapshot()
    res = engine.run_rules(text or "", brand, pages)
    findings = res["findings"]
    ai_info = {"used": False, "model": ai.model_name(), "checked": 0, "dropped": 0, "merged": 0, "redactions": 0, "error": None, "dropped_examples": []}
    if confidential:
        ai_info["error"] = "Confidential mode: nothing was sent to any AI service."
    elif use_ai and text.strip():
        ai_info = ai.ai_review(text, brand, findings)
        findings = findings + ai_info.pop("findings", [])
    image_info = None
    if image_bytes:
        image_info = analyse_image(image_bytes, brand["palette"])
        if not alt_text.strip():
            alt = None if confidential else ai.describe_image(image_bytes, image_mime or "image/png")
            image_info["alt_ai"] = bool(alt)
            image_info["alt_suggestion"] = alt or f"{brand['meta'].get('brand_name')} promotional image for {(brand['meta'].get('brand_name') or '')} product (please describe the key visual)."
        findings += image_findings(image_info, alt_text, brand)
    findings = engine.resolve(findings)
    for f in findings:
        f.setdefault("location", "Image" if f.get("target") == "image" else "Paragraph 1")
    engine.locate([f for f in findings if f.get("target") != "image"], text or "", pages)
    return {
        "findings": findings,
        "risk": engine.risk(findings),
        "metrics": res["metrics"],
        "ai": ai_info,
        "image": image_info,
        "brand_version": brand["version"],
        "purpose": engine.purpose_elements(text or "", brand, goal),
    }


def fix(text: str, findings: list[dict], accepted: list[str], goal: str = "", confidential=False) -> dict:
    brand = db.brand_snapshot()
    new = engine.apply_fixes(text, [f for f in findings if f.get("target") != "image"], accepted)
    guard = engine.purpose_guard(text, new, brand, goal)
    recheck = run_check(new, confidential=True)  # re-check with rules only (fast, deterministic)
    return {"text": new, "purpose": guard, "recheck": {"risk": recheck["risk"], "findings": recheck["findings"]}}


# ---------------------------------------------------------------- workflow

def _initial_status(findings, dismissed_keys):
    gate = [f for f in findings if f["severity"] == "high" and f["key"] not in dismissed_keys]
    return "compliance_review" if gate else "in_review"


def open_findings(sub_id: int, version: dict) -> list[dict]:
    fs = json.loads(version["findings"])
    dismissed = {d["finding_key"] for d in db.q("SELECT finding_key FROM decisions WHERE submission_id=? AND version=? AND action='dismissed'",
                                                 (sub_id, version["version"]))}
    return [f for f in fs if f["key"] not in dismissed]


def create_submission(data: dict, demo: bool = False, when: str | None = None) -> dict:
    role = data.get("role", "creator")
    name = data.get("creator") or "Creator"
    original = data.get("original_text") or data["text"]
    final_text = data["text"]
    t = when or db.now()
    sid = db.ex("INSERT INTO submissions(title,channel,creator,goal,ai_generated,status,risk,current_version,demo,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (data.get("title") or "Untitled", data.get("channel") or "Social post", name, data.get("goal", ""),
                 1 if data.get("ai_generated") else 0, "draft", 0, 1, 1 if demo else 0, t, t))
    image = data.get("image")
    image_bytes = base64.b64decode(image.split(",", 1)[1]) if image else None
    image_mime = image.split(";")[0][5:] if image else None
    v = 1
    if original.strip() != final_text.strip():
        chk0 = run_check(original, confidential=True, image_bytes=image_bytes, image_mime=image_mime, alt_text=data.get("alt_text", ""))
        chk0["ai"]["error"] = "Original draft — re-checked with the rule engine for the record."
        db.ex("INSERT INTO versions(submission_id,version,text,findings,risk,note,brand_version,image,image_info,ai_info,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
              (sid, 1, original, json.dumps(chk0["findings"]), chk0["risk"]["score"], "Original draft", db.brand_version(), image,
               json.dumps(chk0.get("image")), json.dumps(chk0.get("ai")), t))
        v = 2
    chk = run_check(final_text, confidential=bool(data.get("confidential")) or demo, image_bytes=image_bytes, image_mime=image_mime,
                    alt_text=data.get("alt_text", ""), goal=data.get("goal", ""))
    if demo:
        chk["ai"]["error"] = "Sample history — checked with the rule engine only."
    db.ex("INSERT INTO versions(submission_id,version,text,findings,risk,note,brand_version,image,image_info,ai_info,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
          (sid, v, final_text, json.dumps(chk["findings"]), chk["risk"]["score"], "After accepted fixes" if v == 2 else "Submitted draft",
           db.brand_version(), image, json.dumps(chk.get("image")), json.dumps(chk.get("ai")), t))
    db.log(sid, name, role, "submitted", f"v{v} submitted with risk {chk['risk']['score']}", when=t)
    dismissed = set()
    for d in data.get("dismissals", []):
        f = next((x for x in chk["findings"] if x["key"] == d["key"]), None)
        if not f:
            continue
        if f["severity"] == "high":
            raise Denied("A creator cannot dismiss a high-severity finding. Fix it or let Compliance decide.")
        db.ex("INSERT INTO decisions(submission_id,version,finding_key,rule_id,action,by_role,by_name,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
              (sid, v, f["key"], f["rule_id"], "contested", role, name, d.get("reason", ""), t))
        db.log(sid, name, role, "contested", f"{f['rule_id']}: {d.get('reason', '')}", when=t)
    status = _initial_status(chk["findings"], dismissed)
    db.ex("UPDATE submissions SET status=?, risk=?, current_version=? WHERE id=?", (status, chk["risk"]["score"], v, sid))
    return get_submission(sid)


def get_submission(sid: int) -> dict | None:
    s = db.one("SELECT * FROM submissions WHERE id=?", (sid,))
    if not s:
        return None
    vs = db.q("SELECT * FROM versions WHERE submission_id=? ORDER BY version", (sid,))
    for v in vs:
        v["findings"] = json.loads(v["findings"])
        v["image_info"] = json.loads(v["image_info"]) if v.get("image_info") else None
        v["ai_info"] = json.loads(v["ai_info"]) if v.get("ai_info") else None
    s["versions"] = vs
    s["decisions"] = db.q("SELECT * FROM decisions WHERE submission_id=? ORDER BY id", (sid,))
    s["events"] = db.q("SELECT * FROM events WHERE submission_id=? ORDER BY id", (sid,))
    s["comments"] = db.q("SELECT * FROM comments WHERE submission_id=? ORDER BY id", (sid,))
    c = db.one("SELECT id FROM certificates WHERE submission_id=? ORDER BY id DESC LIMIT 1", (sid,))
    s["certificate"] = certs.get(c["id"]) if c else None
    cur = vs[-1] if vs else None
    if cur:
        dismissed = {d["finding_key"] for d in s["decisions"] if d["version"] == cur["version"] and d["action"] == "dismissed"}
        s["open_high"] = sum(1 for f in cur["findings"] if f["severity"] == "high" and f["key"] not in dismissed)
        s["open_total"] = sum(1 for f in cur["findings"] if f["key"] not in dismissed)
    return s


def list_submissions() -> list[dict]:
    rows = db.q("SELECT * FROM submissions ORDER BY updated_at DESC, id DESC")
    for r in rows:
        r["has_certificate"] = bool(db.one("SELECT 1 x FROM certificates WHERE submission_id=?", (r["id"],)))
    return rows


def act(sid: int, data: dict, when: str | None = None) -> dict:
    s = get_submission(sid)
    if not s:
        raise Denied("Submission not found")
    role, name = data.get("role", "creator"), data.get("name") or data.get("role", "user").title()
    action = data["action"]
    reason = (data.get("reason") or "").strip()
    cur = s["versions"][-1]
    t = when or db.now()

    def set_status(st):
        db.ex("UPDATE submissions SET status=?, updated_at=? WHERE id=?", (st, t, sid))

    if action == "comment":
        if not (data.get("text") or "").strip():
            raise Denied("Comment is empty")
        db.ex("INSERT INTO comments(submission_id,author,role,text,created_at) VALUES(?,?,?,?,?)", (sid, name, role, data["text"].strip(), t))
        db.log(sid, name, role, "commented", data["text"][:120], when=t)
    elif action == "dismiss":
        key = data["finding_key"]
        f = next((x for x in cur["findings"] if x["key"] == key), None)
        if not f:
            raise Denied("Finding not found in the current version")
        if not reason:
            raise Denied("A reason is required to dismiss a finding.")
        if f["severity"] == "high" and role != "compliance":
            raise Denied("Only Compliance can dismiss a high-severity finding.")
        if role == "creator":
            raise Denied("Creators cannot dismiss findings after submission. Add a comment or resubmit a fixed version.")
        db.ex("INSERT INTO decisions(submission_id,version,finding_key,rule_id,action,by_role,by_name,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
              (sid, cur["version"], key, f["rule_id"], "dismissed", role, name, reason, t))
        db.log(sid, name, role, "dismissed finding", f"{f['rule_id']} — {reason}", when=t)
    elif action == "clear_claims":
        if role != "compliance":
            raise Denied("Only Compliance can clear claims.")
        if s["status"] != "compliance_review":
            raise Denied("This submission is not waiting for Compliance.")
        if s["open_high"]:
            raise Denied(f"{s['open_high']} high-severity finding(s) are still open. Dismiss with a reason, or request changes.")
        set_status("in_review")
        db.log(sid, name, role, "cleared claims", reason, when=t)
    elif action == "approve":
        if role != "reviewer":
            raise Denied("Only a Reviewer can give final approval.")
        if s["status"] != "in_review":
            raise Denied("Content must pass Compliance before final approval." if s["status"] == "compliance_review" else "This submission is not awaiting approval.")
        if s["open_high"]:
            raise Denied("High-severity findings are still open.")
        set_status("approved")
        db.log(sid, name, role, "approved", reason, when=t)
        decisions = db.q("SELECT * FROM decisions WHERE submission_id=? AND version=?", (sid, cur["version"]))
        approvers = [{"name": e["actor"], "role": e["role"], "action": e["action"], "at": e["created_at"]}
                     for e in db.q("SELECT * FROM events WHERE submission_id=? AND action IN ('cleared claims','approved') ORDER BY id", (sid,))]
        ai_model = (cur.get("ai_info") or {}).get("model") or ai.model_name()
        c = certs.issue(s, cur, decisions, approvers, ai_model, when=t)
        db.log(sid, "BrandProof", "system", "certificate issued", f"Proof Certificate #{c['number']}", when=t)
    elif action in ("reject", "request_changes"):
        if role not in ("reviewer", "compliance"):
            raise Denied("Only Reviewers or Compliance can do this.")
        if not reason:
            raise Denied("Please give a reason so the creator knows what to change.")
        set_status("rejected" if action == "reject" else "changes_requested")
        db.log(sid, name, role, "rejected" if action == "reject" else "requested changes", reason, when=t)
    elif action == "resubmit":
        if role != "creator":
            raise Denied("Only the creator can resubmit.")
        if s["status"] not in ("changes_requested", "compliance_review", "in_review"):
            raise Denied("This submission cannot be resubmitted now.")
        text = data.get("text", "")
        v = cur["version"] + 1
        chk = run_check(text, confidential=bool(data.get("confidential")), goal=s.get("goal", ""))
        db.ex("INSERT INTO versions(submission_id,version,text,findings,risk,note,brand_version,image,image_info,ai_info,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
              (sid, v, text, json.dumps(chk["findings"]), chk["risk"]["score"], reason or "Revised after review", db.brand_version(),
               cur.get("image"), json.dumps(cur.get("image_info")), json.dumps(chk.get("ai")), t))
        db.ex("UPDATE submissions SET status=?, risk=?, current_version=?, updated_at=? WHERE id=?",
              (_initial_status(chk["findings"], set()), chk["risk"]["score"], v, t, sid))
        db.log(sid, name, role, "resubmitted", f"v{v} with risk {chk['risk']['score']}", when=t)
    else:
        raise Denied("Unknown action")
    db.ex("UPDATE submissions SET updated_at=? WHERE id=?", (t, sid))
    return get_submission(sid)


# ---------------------------------------------------------------- insights

def insights() -> dict:
    subs = db.q("SELECT * FROM submissions")
    first_versions = {}
    for v in db.q("SELECT * FROM versions ORDER BY version"):
        first_versions.setdefault(v["submission_id"], v)
    rules = {r["id"]: r for r in db.q("SELECT * FROM rules")}
    sub_by_id = {s["id"]: s for s in subs}
    rule_counts, creator_counts, channel_counts = Counter(), defaultdict(Counter), Counter()
    risk_first = []
    for sid, v in first_versions.items():
        fs = json.loads(v["findings"])
        risk_first.append(v["risk"])
        s = sub_by_id.get(sid)
        for f in fs:
            rule_counts[f["rule_id"]] += 1
            if s:
                creator_counts[s["creator"]][f["severity"]] += 1
                channel_counts[s["channel"]] += 1
    flagged_all = Counter()
    for v in db.q("SELECT findings FROM versions"):
        for f in json.loads(v["findings"]):
            flagged_all[f["rule_id"]] += 1
    dec = db.q("SELECT * FROM decisions")
    dismissed = Counter(d["rule_id"] for d in dec if d["action"] == "dismissed")
    contested = Counter(d["rule_id"] for d in dec if d["action"] == "contested")
    reasons = defaultdict(list)
    for d in dec:
        if d["reason"]:
            reasons[d["rule_id"]].append(d["reason"])
    health = []
    for rid, n in flagged_all.most_common():
        r = rules.get(rid)
        if not r:
            continue
        dz, ct = dismissed[rid], contested[rid]
        rate = round(100 * (dz + ct) / n) if n else 0
        status = "unclear" if n >= 3 and rate >= 40 else "watch" if rate >= 20 else "clear"
        top_reason = Counter(reasons[rid]).most_common(1)[0][0] if reasons[rid] else ""
        suggestion = ""
        if status != "clear":
            suggestion = (f"Reviewers disagree with “{r['title']}” in {rate}% of cases"
                          + (f" (most common reason: “{top_reason}”)" if top_reason else "")
                          + ". Add an explicit exception or example to the rule so creators and reviewers apply it the same way.")
        health.append({"rule_id": rid, "title": r["title"], "category": r["category"], "flagged": n, "dismissed": dz, "contested": ct,
                       "disagreement": rate, "status": status, "suggestion": suggestion, "reasons": reasons[rid][:5]})
    approved = [s for s in subs if s["status"] == "approved"]
    final_risk = [s["risk"] for s in approved]
    status_counts = Counter(s["status"] for s in subs)
    return {
        "totals": {"submissions": len(subs), "approved": len(approved), "certificates": len(db.q("SELECT id FROM certificates")),
                   "avg_risk_first": round(sum(risk_first) / len(risk_first)) if risk_first else 0,
                   "avg_risk_approved": round(sum(final_risk) / len(final_risk)) if final_risk else 0,
                   "issues_caught": sum(rule_counts.values())},
        "status": dict(status_counts),
        "top_rules": [{"rule_id": k, "title": rules[k]["title"] if k in rules else k, "count": v} for k, v in rule_counts.most_common(8)],
        "by_creator": [{"creator": k, **dict(v), "total": sum(v.values())} for k, v in sorted(creator_counts.items(), key=lambda kv: -sum(kv[1].values()))],
        "by_channel": [{"channel": k, "count": v} for k, v in channel_counts.most_common()],
        "guideline_health": health,
        "has_demo": any(s["demo"] for s in subs),
    }


# ---------------------------------------------------------------- brand-book import

IMPORT_PATTERNS = [
    ("price", "Product price", "INR", r"(?:price|mrp)\s*[:=\-–]\s*(?:₹|rs\.?|inr)\s?([\d,]+)"),
    ("max_discount", "Maximum discount", "%", r"max(?:imum)?\s+discount\s*[:=\-–]\s*(\d{1,3})\s?%"),
    ("warranty_years", "Warranty", "years", r"warranty\s*[:=\-–]\s*(\d{1,2})\s*(?:years?|yrs?)"),
    ("battery_hours", "Battery life", "hours", r"battery(?:\s+life)?\s*[:=\-–]\s*(\d{1,3})\s*(?:hours?|hrs?)"),
    ("ip_rating", "Water resistance rating", "", r"(?:water\s+resistance|ip\s+rating)\s*[:=\-–]\s*(IP[X\d]\d)"),
    ("tagline", "Approved tagline", "", r"tagline\s*[:=\-–]\s*[\"“]?([^\"”\n]{4,80})"),
    ("product_name", "Official product name", "", r"(?:official\s+)?product\s+name\s*[:=\-–]\s*([^\n]{3,60})"),
]


def import_brand_book(filename: str, text: str) -> dict:
    created = []
    existing = {f["key"]: f for f in db.q("SELECT * FROM facts WHERE status='approved' AND (valid_to IS NULL OR valid_to='' OR valid_to>=?)", (db.today(),))}
    for key, label, unit, pat in IMPORT_PATTERNS:
        for m in re.finditer(pat, text, re.I):
            val = m.group(1).replace(",", "").strip().rstrip(".")
            cur = existing.get(key)
            change = "new" if not cur else ("same" if str(cur["value"]).lower() == val.lower() else "update")
            if change == "same":
                continue
            snippet = text[max(0, m.start() - 40): m.end() + 40].replace("\n", " ")
            cid = db.ex("INSERT INTO candidates(kind,payload,source,snippet,status,created_at) VALUES(?,?,?,?,?,?)",
                        ("fact", json.dumps({"key": key, "label": label, "value": val, "unit": unit, "change": change,
                                             "current": cur["value"] if cur else None}), filename, snippet, "pending", db.now()))
            created.append(cid)
            break
    for m in re.finditer(r"(?:avoid|don'?t\s+use|do\s+not\s+use)\s*[:\-–]?\s*[\"“']([^\"”']{2,40})[\"”']\s*(?:[,;]|→|->|-|–)?\s*(?:use|say|prefer)\s*[:\-–]?\s*[\"“']([^\"”']{2,40})[\"”']", text, re.I):
        avoid, prefer = m.group(1).strip(), m.group(2).strip()
        if db.one("SELECT id FROM terms WHERE lower(avoid)=lower(?)", (avoid,)):
            continue
        cid = db.ex("INSERT INTO candidates(kind,payload,source,snippet,status,created_at) VALUES(?,?,?,?,?,?)",
                    ("term", json.dumps({"avoid": avoid, "prefer": prefer}), filename, m.group(0)[:160], "pending", db.now()))
        created.append(cid)
    for m in re.finditer(r"confidential\s*[:\-–]\s*([^\n]{3,80})", text, re.I):
        for item in re.split(r",|;| and ", m.group(1)):
            item = item.strip().strip(".\"“”")
            if len(item) < 3 or item.lower() in [c.lower() for c in (db.get_meta("confidential_terms") or [])]:
                continue
            cid = db.ex("INSERT INTO candidates(kind,payload,source,snippet,status,created_at) VALUES(?,?,?,?,?,?)",
                        ("confidential", json.dumps({"term": item}), filename, m.group(0)[:160], "pending", db.now()))
            created.append(cid)
    return {"created": len(created), "candidates": pending_candidates()}


def pending_candidates():
    out = db.q("SELECT * FROM candidates WHERE status='pending' ORDER BY id")
    for c in out:
        c["payload"] = json.loads(c["payload"])
    return out


def decide_candidate(cid: int, approve: bool, role: str) -> dict:
    if role != "admin":
        raise Denied("Only the Brand Admin can approve Brand Memory changes.")
    c = db.one("SELECT * FROM candidates WHERE id=?", (cid,))
    if not c or c["status"] != "pending":
        raise Denied("Candidate not found")
    p = json.loads(c["payload"])
    if not approve:
        db.ex("UPDATE candidates SET status='rejected' WHERE id=?", (cid,))
        return {"ok": True, "brand_version": db.brand_version()}
    if c["kind"] == "fact":
        today = db.today()
        old = db.one("SELECT * FROM facts WHERE key=? AND status='approved' AND (valid_to IS NULL OR valid_to='' OR valid_to>=?)", (p["key"], today))
        from datetime import date, timedelta
        if old:
            db.ex("UPDATE facts SET valid_to=? WHERE id=?", ((date.today() - timedelta(days=1)).isoformat(), old["id"]))
        n = db.one("SELECT COUNT(*) c FROM facts")["c"] + 101
        fid = f"F-{n}"
        v = db.bump_brand(f"Imported {p['label']} = {p['value']} from {c['source']}")
        db.ex("INSERT INTO facts(id,key,label,value,unit,valid_from,valid_to,source,status,added_in) VALUES(?,?,?,?,?,?,?,?,?,?)",
              (fid, p["key"], p["label"], p["value"], p.get("unit"), today, None, c["source"], "approved", v))
    elif c["kind"] == "term":
        db.ex("INSERT INTO terms(avoid,prefer,note,status) VALUES(?,?,?,?)", (p["avoid"], p["prefer"], f"Imported from {c['source']}", "approved"))
        db.bump_brand(f"Added term “{p['avoid']}” → “{p['prefer']}”")
    elif c["kind"] == "confidential":
        terms = db.get_meta("confidential_terms") or []
        terms.append(p["term"])
        db.set_meta("confidential_terms", terms)
        db.bump_brand(f"Marked “{p['term']}” as confidential")
    db.ex("UPDATE candidates SET status='approved' WHERE id=?", (cid,))
    return {"ok": True, "brand_version": db.brand_version()}
