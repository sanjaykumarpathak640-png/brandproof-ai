"""Business logic: checks, BrandFlow workflow, insights, brand-book import and impact preview.

Every function is scoped to one workspace (org). Workflow actions take a Ctx that carries the
verified user (team workspaces) or the demo role (demo sandboxes).
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from . import ai, certs, db, engine, vision
from .auth import Ctx, ROLE_LABEL, require
from .extract import analyse_image

MAX_TEXT = 20000
STATUS_LABEL = {"compliance_review": "Waiting for Compliance", "in_review": "Waiting for Reviewer", "approved": "Approved",
                "rejected": "Rejected", "changes_requested": "Changes requested", "draft": "Draft"}


class Denied(Exception):
    status = 403


class Conflict(Exception):
    status = 409


def _clip(s, n):
    return (s or "").strip()[:n] if isinstance(s, str) else ""


# ---------------------------------------------------------------- image findings

def _rule_ev(r):
    return [{"ref": r["id"], "text": r["title"] + ": " + (r.get("description") or ""), "source": r.get("source", "")}]


def image_findings(info: dict, creative: dict | None, alt_text: str, brand: dict) -> list[dict]:
    rules = {r["id"]: r for r in brand["rules"] if r.get("enabled", 1)}
    out = []

    def mk(rid, message, metric=None, fix=None, extra=None, target="image", box=None, quote=""):
        r = rules.get(rid)
        if not r:
            return
        out.append({"rule_id": rid, "category": r["category"], "severity": r["severity"], "title": r["title"], "quote": quote,
                    "start": 0, "end": 0, "message": message, "evidence": _rule_ev(r) + (extra or []), "fix": fix, "engine": "vision",
                    "metric": metric, "target": target, "location": "Image", "box": box})

    pal = ", ".join(f"{p['name']} {p['hex']}" for p in brand["palette"])
    for c in info["off_palette"]:
        mk("R-VIS-01", f"Colour {c['hex']} covers {c['share']}% of the image and is ΔE {c['delta_e']} from the nearest brand colour "
                       f"({c['nearest']} {c['nearest_hex']}); limit ΔE {info['de_limit']:.0f}.",
           metric={"found": f"ΔE {c['delta_e']}", "limit": f"ΔE {info['de_limit']:.0f}", "swatch": c["hex"], "nearest": c["nearest_hex"]},
           extra=[{"ref": "Brand palette", "text": pal, "source": "Brand Book · Visual identity"}])
    text_lines = ((creative or {}).get("text") or {}).get("lines") or []
    measured = [ln for ln in text_lines if ln.get("contrast") is not None]
    if measured:
        for ln in measured:
            if ln["contrast"] < 3.0:
                mk("R-IMG-01", f"Text “{ln['text'][:60]}” has a contrast of {ln['contrast']}:1 against its background (needs 3:1).",
                   metric={"found": f"{ln['contrast']}:1", "limit": "3:1"}, box=ln.get("box"), quote=ln["text"][:120], target="image_text")
    else:
        ce = info.get("contrast_estimate")
        if ce is not None and ce < 3.0:
            mk("R-A11Y-03", f"Estimated contrast between the two main colours is {ce}:1. Text on this background may be hard to read (WCAG AA large text needs 3:1).",
               metric={"found": f"{ce}:1", "limit": "3:1"})
    logo = (creative or {}).get("logo") or {}
    if logo.get("status") == "ok" and not logo.get("present"):
        mk("R-LOGO-01", "The approved logo was not found in this creative." + (f" Vision model: {logo['notes']}" if logo.get("notes") else ""),
           metric={"found": "not found", "approved": "logo required"},
           extra=[{"ref": "Logo asset", "text": f"Checked by {logo.get('method')} (best pixel match {logo.get('score')})", "source": "Brand Memory · assets"}])
    elif logo.get("present") and logo.get("altered"):
        mk("R-LOGO-01", "The logo appears altered (recoloured, stretched or redrawn)." + (f" {logo['notes']}" if logo.get("notes") else ""),
           metric={"found": "altered", "approved": "original logo"}, box=logo.get("box"))
    if not (alt_text or "").strip():
        mk("R-A11Y-02", "The image has no alt text, so screen-reader users cannot understand it.",
           fix={"replacement": info.get("alt_suggestion") or "", "note": "Suggested alt text" + (" (AI-assisted)" if info.get("alt_ai") else ""), "target": "alt"})
    return out


def image_text_findings(creative: dict, brand: dict) -> tuple[list[dict], str]:
    """Run the same rule engine on the text read from the image and attach each finding to its box."""
    lines = ((creative or {}).get("text") or {}).get("lines") or []
    if not lines:
        return [], ""
    joined, spans = "", []
    for ln in lines:
        s = len(joined)
        joined += ln["text"]
        spans.append((s, len(joined), ln.get("box")))
        joined += "\n"
    res = engine.run_rules(joined, brand)
    out = []
    for f in res["findings"]:
        if f["rule_id"] == "R-A11Y-01" or (f["rule_id"] == "R-VOICE-01" and "all caps" in f["message"]):
            continue  # long lines and ALL-CAPS headlines are normal typography on posters
        if f["rule_id"] == "R-PRC-03":
            f.update(quote="", message="The image promotes an offer but its text has no “T&C apply” disclaimer.")
        boxes = [b for (s, e, b) in spans if b and s < max(f["end"], f["start"] + 1) and f["start"] < e]
        f["target"] = "image_text"
        f["box"] = boxes[0] if boxes else None
        f["location"] = "Text in image"
        f["engine"] = "vision"
        if f.get("fix"):
            f["fix"]["note"] = "Change this text in the design. " + f["fix"].get("note", "")
            f["fix"]["design_only"] = True
        f["evidence"] = f["evidence"] + [{"ref": "Image text", "text": f"Read from the image by {creative['text'].get('model')}", "source": "Vision model"}]
        out.append(f)
    return out, joined


# ---------------------------------------------------------------- checking

def run_check(org: int, text: str, *, confidential: bool = False, use_ai: bool = True, pages=None,
              image_bytes: bytes | None = None, image_mime: str | None = None, alt_text: str = "", goal: str = "",
              brand: dict | None = None) -> dict:
    text = (text or "")[:MAX_TEXT]
    brand = brand or db.brand_snapshot(org)
    res = engine.run_rules(text, brand, pages)
    findings = res["findings"]
    ai_info = {"used": False, "model": ai.model_name(), "checked": 0, "dropped": 0, "merged": 0, "redactions": 0, "error": None,
               "dropped_examples": []}
    # the text review and the image reading run at the same time
    pool = ThreadPoolExecutor(max_workers=2)
    fut_text = fut_img = None
    if confidential:
        ai_info["error"] = "Confidential mode: nothing was sent to any AI service."
    elif use_ai and text.strip():
        fut_text = pool.submit(ai.ai_review, text, brand, list(findings))
    if image_bytes:
        logo = db.logo_data(org)
        fut_img = pool.submit(vision.analyse_creative, image_bytes, image_mime or "image/png", logo, use_ai=(use_ai and not confidential))
    if fut_text:
        ai_info = fut_text.result()
        findings = findings + ai_info.pop("findings", [])
    image_info = None
    if image_bytes:
        image_info = analyse_image(image_bytes, brand["palette"])
        creative = fut_img.result()
        image_info["creative"] = creative
        if not alt_text.strip():
            alt = creative.get("alt")
            image_info["alt_ai"] = bool(alt)
            image_info["alt_suggestion"] = alt or f"{brand['meta'].get('brand_name')} promotional image (please describe the key visual and any text)."
        txt_findings, joined = image_text_findings(creative, brand)
        image_info["image_text"] = joined
        findings += txt_findings + image_findings(image_info, creative, alt_text, brand)
    pool.shutdown(wait=False)
    findings = engine.resolve(findings)
    engine.locate([f for f in findings if f.get("target") not in ("image", "image_text")], text, pages)
    for f in findings:
        f.setdefault("location", "Paragraph 1")
    return {
        "findings": findings,
        "risk": engine.risk(findings),
        "metrics": res["metrics"],
        "ai": ai_info,
        "image": image_info,
        "brand_version": brand["version"],
        "purpose": engine.purpose_elements(text, brand, goal),
    }


def fix(org: int, text: str, findings: list[dict], accepted: list[str], goal: str = "") -> dict:
    brand = db.brand_snapshot(org)
    new = engine.apply_fixes(text, [f for f in findings if f.get("target") not in ("image", "image_text")], accepted)
    guard = engine.purpose_guard(text, new, brand, goal)
    recheck = run_check(org, new, confidential=True, brand=brand)
    return {"text": new, "purpose": guard, "recheck": {"risk": recheck["risk"], "findings": recheck["findings"]}}


# ---------------------------------------------------------------- workflow

def _initial_status(findings, dismissed_keys):
    gate = [f for f in findings if f["severity"] == "high" and f["key"] not in dismissed_keys]
    return "compliance_review" if gate else "in_review"


def _insert_version(org, sid, v, text, chk, note, image, t):
    db.ex("INSERT INTO versions(org_id,submission_id,version,text,findings,risk,note,brand_version,image,image_info,ai_info,created_at) "
          "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
          (org, sid, v, text, json.dumps(chk["findings"]), chk["risk"]["score"], note, db.brand_version(org), image,
           json.dumps(chk.get("image")), json.dumps(chk.get("ai")), t))


def _seconds_ago(n):
    return (datetime.now(timezone.utc) - timedelta(seconds=n)).replace(microsecond=0).isoformat()


def create_submission(ctx: Ctx, data: dict, demo: bool = False, when: str | None = None, creator_name: str | None = None) -> dict:
    if not demo:
        require(ctx, "creator")
    org = ctx.org_id
    final_text = (data.get("text") or "")[:MAX_TEXT]
    original = (data.get("original_text") or final_text)[:MAX_TEXT]
    image = data.get("image")
    if not final_text.strip() and not image:
        raise Denied("Nothing to submit. Add text or an image.")
    title = _clip(data.get("title"), 120) or "Untitled"
    name = creator_name or ctx.actor
    t = when or db.now()
    if not demo:  # idempotency: a double click must not create two submissions
        recent = db.one("SELECT id, created_at FROM submissions WHERE org_id=? AND title=? ORDER BY id DESC LIMIT 1", (org, title))
        if recent and recent["created_at"] >= _seconds_ago(30):
            v = db.one("SELECT text FROM versions WHERE org_id=? AND submission_id=? ORDER BY version DESC LIMIT 1", (org, recent["id"]))
            if v and v["text"] == final_text:
                return get_submission(org, recent["id"])
    sid = db.ex("INSERT INTO submissions(org_id,title,channel,creator,creator_user_id,goal,ai_generated,status,risk,current_version,demo,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (org, title, _clip(data.get("channel"), 40) or "Social post", name, ctx.user_id, _clip(data.get("goal"), 200),
                 1 if data.get("ai_generated") else 0, "draft", 0, 1, 1 if demo else 0, t, t))
    image_bytes = image_mime = None
    if image:
        image_bytes, image_mime = vision.decode_data_url(image)
    confidential = bool(data.get("confidential")) or demo
    v = 1
    if original.strip() != final_text.strip():
        chk0 = run_check(org, original, confidential=True, image_bytes=image_bytes, image_mime=image_mime, alt_text=data.get("alt_text", ""))
        chk0["ai"]["error"] = "Original draft — re-checked with the rule engine for the record."
        _insert_version(org, sid, 1, original, chk0, "Original draft", image, t)
        v = 2
    chk = run_check(org, final_text, confidential=confidential, image_bytes=image_bytes, image_mime=image_mime,
                    alt_text=data.get("alt_text", ""), goal=data.get("goal", ""))
    if demo:
        chk["ai"]["error"] = "Sample history — checked with the rule engine only."
    _insert_version(org, sid, v, final_text, chk, "After accepted fixes" if v == 2 else "Submitted draft", image, t)
    db.log(org, sid, name, "creator", "submitted", f"v{v} submitted with risk {chk['risk']['score']}", when=t, user_id=ctx.user_id)
    for d in data.get("dismissals", []) or []:
        f = next((x for x in chk["findings"] if x["key"] == d.get("key")), None)
        if not f:
            continue
        if f["severity"] == "high":
            raise Denied("A creator cannot dismiss a high-severity finding. Fix it or let Compliance decide.")
        reason = _clip(d.get("reason"), 500)
        db.ex("INSERT INTO decisions(org_id,submission_id,version,finding_key,rule_id,action,by_role,by_name,by_user_id,reason,created_at) "
              "VALUES(?,?,?,?,?,?,?,?,?,?,?)", (org, sid, v, f["key"], f["rule_id"], "contested", "creator", name, ctx.user_id, reason, t))
        db.log(org, sid, name, "creator", "contested", f"{f['rule_id']}: {reason}", when=t, user_id=ctx.user_id)
    status = _initial_status(chk["findings"], set())
    db.ex("UPDATE submissions SET status=?, risk=?, current_version=? WHERE id=? AND org_id=?", (status, chk["risk"]["score"], v, sid, org))
    out = get_submission(org, sid)
    out["next"] = next_step(out)
    return out


def get_submission(org: int, sid: int) -> dict | None:
    s = db.one("SELECT * FROM submissions WHERE id=? AND org_id=?", (sid, org))
    if not s:
        return None
    vs = db.q("SELECT * FROM versions WHERE org_id=? AND submission_id=? ORDER BY version", (org, sid))
    for v in vs:
        v["findings"] = json.loads(v["findings"])
        v["image_info"] = json.loads(v["image_info"]) if v.get("image_info") else None
        v["ai_info"] = json.loads(v["ai_info"]) if v.get("ai_info") else None
    s["versions"] = vs
    s["decisions"] = db.q("SELECT * FROM decisions WHERE org_id=? AND submission_id=? ORDER BY id", (org, sid))
    s["events"] = db.q("SELECT * FROM events WHERE org_id=? AND submission_id=? ORDER BY id", (org, sid))
    s["comments"] = db.q("SELECT * FROM comments WHERE org_id=? AND submission_id=? ORDER BY id", (org, sid))
    c = db.one("SELECT id FROM certificates WHERE org_id=? AND submission_id=? ORDER BY id DESC LIMIT 1", (org, sid))
    s["certificate"] = certs.get(org, c["id"]) if c else None
    cur = vs[-1] if vs else None
    s["open_high"] = s["open_total"] = 0
    if cur:
        dismissed = {d["finding_key"] for d in s["decisions"] if d["version"] == cur["version"] and d["action"] == "dismissed"}
        s["open_high"] = sum(1 for f in cur["findings"] if f["severity"] == "high" and f["key"] not in dismissed)
        s["open_total"] = sum(1 for f in cur["findings"] if f["key"] not in dismissed)
    s["status_label"] = STATUS_LABEL.get(s["status"], s["status"])
    s["next"] = next_step(s)
    return s


def list_submissions(org: int) -> list[dict]:
    rows = db.q("SELECT * FROM submissions WHERE org_id=? ORDER BY updated_at DESC, id DESC", (org,))
    certified = {r["submission_id"] for r in db.q("SELECT submission_id FROM certificates WHERE org_id=?", (org,))}
    for r in rows:
        r["has_certificate"] = r["id"] in certified
        r["status_label"] = STATUS_LABEL.get(r["status"], r["status"])
    return rows


def next_step(s: dict) -> dict:
    """What should happen next, and which role does it — shown on the review page."""
    st = s["status"]
    if st == "compliance_review":
        if s.get("open_high"):
            return {"role": "compliance", "text": f"Compliance reviews the {s['open_high']} high-severity finding(s): dismiss each with a reason, or request changes."}
        return {"role": "compliance", "text": "All high-severity findings are handled. Compliance clicks “Clear claims” to send it to the Reviewer."}
    if st == "in_review":
        return {"role": "reviewer", "text": "The Reviewer does the final brand check and approves (a Proof Certificate is issued) or requests changes."}
    if st == "changes_requested":
        return {"role": "creator", "text": "The Creator edits the text (or applies the suggested fixes) and resubmits a new version."}
    if st == "approved":
        return {"role": None, "text": "Approved and certified. The Proof Certificate shows exactly what was approved and by whom."}
    return {"role": None, "text": "This submission was rejected. The reason is in the audit trail."}


def act(ctx: Ctx, sid: int, data: dict, when: str | None = None) -> dict:
    org = ctx.org_id
    s = get_submission(org, sid)
    if not s:
        raise Denied("Submission not found")
    role, name, uid = ctx.role, ctx.actor, ctx.user_id
    action = data.get("action")
    reason = _clip(data.get("reason"), 500)
    cur = s["versions"][-1]
    t = when or db.now()

    def set_status(st):
        db.ex("UPDATE submissions SET status=?, updated_at=? WHERE id=? AND org_id=?", (st, t, sid, org))

    if action == "comment":
        text = _clip(data.get("text"), 1000)
        if not text:
            raise Denied("Comment is empty")
        db.ex("INSERT INTO comments(org_id,submission_id,author,role,text,created_at) VALUES(?,?,?,?,?,?)", (org, sid, name, role, text, t))
        db.log(org, sid, name, role, "commented", text[:120], when=t, user_id=uid)
    elif action == "dismiss":
        key = data.get("finding_key")
        f = next((x for x in cur["findings"] if x["key"] == key), None)
        if not f:
            raise Denied("This finding is not in the current version (the page may be out of date — refresh).")
        if any(d["finding_key"] == key and d["version"] == cur["version"] and d["action"] == "dismissed" for d in s["decisions"]):
            raise Conflict("This finding was already dismissed.")
        if s["status"] not in ("compliance_review", "in_review"):
            raise Denied("Findings can only be dismissed while the content is under review.")
        if role == "creator":
            raise Denied("Creators cannot dismiss findings after submission. Add a comment or resubmit a fixed version.")
        if f["severity"] == "high" and role != "compliance":
            raise Denied("Only Compliance can dismiss a high-severity finding.")
        if role not in ("compliance", "reviewer"):
            raise Denied("Only Compliance or a Reviewer can dismiss findings.")
        if not reason:
            raise Denied("A reason is required to dismiss a finding.")
        db.ex("INSERT INTO decisions(org_id,submission_id,version,finding_key,rule_id,action,by_role,by_name,by_user_id,reason,created_at) "
              "VALUES(?,?,?,?,?,?,?,?,?,?,?)", (org, sid, cur["version"], key, f["rule_id"], "dismissed", role, name, uid, reason, t))
        db.log(org, sid, name, role, "dismissed finding", f"{f['rule_id']} — {reason}", when=t, user_id=uid)
    elif action == "clear_claims":
        require(ctx, "compliance")
        if s["status"] != "compliance_review":
            raise Conflict("This submission is not waiting for Compliance (it may already be cleared — refresh).")
        if s["open_high"]:
            raise Denied(f"{s['open_high']} high-severity finding(s) are still open. Dismiss each with a reason, or request changes.")
        set_status("in_review")
        db.log(org, sid, name, role, "cleared claims", reason, when=t, user_id=uid)
    elif action == "approve":
        require(ctx, "reviewer")
        if s["status"] == "approved":
            raise Conflict("Already approved — see the Proof Certificate.")
        if s["status"] != "in_review":
            raise Denied("Content must pass Compliance before final approval." if s["status"] == "compliance_review" else "This submission is not awaiting approval.")
        if s["open_high"]:
            raise Denied("High-severity findings are still open.")
        if not ctx.demo and s.get("creator_user_id") == uid and ctx.members > 1:
            raise Denied("Four-eyes rule: you cannot approve content you submitted yourself. Ask another Reviewer.")
        set_status("approved")
        db.log(org, sid, name, role, "approved", reason, when=t, user_id=uid)
        decisions = db.q("SELECT * FROM decisions WHERE org_id=? AND submission_id=? AND version=?", (org, sid, cur["version"]))
        approvers = []
        for e in db.q("SELECT * FROM events WHERE org_id=? AND submission_id=? AND action IN ('cleared claims','approved') ORDER BY id", (org, sid)):
            ident = {"name": e["actor"], "role": e["role"], "action": e["action"], "at": e["created_at"], "verified": bool(e["actor_user_id"])}
            if e["actor_user_id"]:
                u = db.one("SELECT email FROM users WHERE id=?", (e["actor_user_id"],))
                ident.update(user_id=e["actor_user_id"], email=u["email"] if u else None)
            approvers.append(ident)
        ai_model = (cur.get("ai_info") or {}).get("model") or ai.model_name()
        c = certs.issue(org, s, cur, decisions, approvers, ai_model, demo=ctx.demo, when=t)
        db.log(org, sid, "BrandProof", "system", "certificate issued", f"Proof Certificate #{c['number']}", when=t)
    elif action in ("reject", "request_changes"):
        if role not in ("reviewer", "compliance"):
            raise Denied("Only Reviewers or Compliance can do this.")
        if s["status"] not in ("compliance_review", "in_review"):
            raise Conflict(f"This submission is already “{STATUS_LABEL.get(s['status'], s['status'])}”.")
        if not reason:
            raise Denied("Please give a reason so the creator knows what to change.")
        set_status("rejected" if action == "reject" else "changes_requested")
        db.log(org, sid, name, role, "rejected" if action == "reject" else "requested changes", reason, when=t, user_id=uid)
    elif action == "resubmit":
        require(ctx, "creator")
        if s["status"] not in ("changes_requested", "compliance_review", "in_review"):
            raise Conflict("This submission cannot be resubmitted now.")
        text = (data.get("text") or "")[:MAX_TEXT]
        if not text.strip() and not cur.get("image"):
            raise Denied("The new version is empty.")
        if text.strip() == (cur["text"] or "").strip():
            raise Denied("The text has not changed. Edit it (or apply the suggested fixes) before resubmitting.")
        v = cur["version"] + 1
        img_b = img_m = None
        if cur.get("image"):
            img_b, img_m = vision.decode_data_url(cur["image"])
        chk = run_check(org, text, confidential=bool(data.get("confidential")), goal=s.get("goal", ""), image_bytes=img_b, image_mime=img_m,
                        alt_text="(kept from previous version)" if cur.get("image") else "")
        _insert_version(org, sid, v, text, chk, reason or "Revised after review", cur.get("image"), t)
        db.ex("UPDATE submissions SET status=?, risk=?, current_version=?, updated_at=? WHERE id=? AND org_id=?",
              (_initial_status(chk["findings"], set()), chk["risk"]["score"], v, t, sid, org))
        db.log(org, sid, name, role, "resubmitted", f"v{v} with risk {chk['risk']['score']}", when=t, user_id=uid)
    else:
        raise Denied("Unknown action")
    db.ex("UPDATE submissions SET updated_at=? WHERE id=? AND org_id=?", (t, sid, org))
    return get_submission(org, sid)


# ---------------------------------------------------------------- insights

def insights(org: int) -> dict:
    subs = db.q("SELECT * FROM submissions WHERE org_id=?", (org,))
    vers = db.q("SELECT submission_id, version, findings, risk FROM versions WHERE org_id=? ORDER BY version", (org,))
    first_versions = {}
    for v in vers:
        first_versions.setdefault(v["submission_id"], v)
    rules = {r["id"]: r for r in db.q("SELECT * FROM rules WHERE org_id=?", (org,))}
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
    for v in vers:
        for f in json.loads(v["findings"]):
            flagged_all[f["rule_id"]] += 1
    dec = db.q("SELECT * FROM decisions WHERE org_id=?", (org,))
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
                       "disagreement": rate, "status": status, "suggestion": suggestion, "reasons": reasons[rid][:5],
                       "description": r["description"]})
    approved = [s for s in subs if s["status"] == "approved"]
    final_risk = [s["risk"] for s in approved]
    return {
        "totals": {"submissions": len(subs), "approved": len(approved),
                   "certificates": db.one("SELECT COUNT(*) AS c FROM certificates WHERE org_id=?", (org,))["c"],
                   "avg_risk_first": round(sum(risk_first) / len(risk_first)) if risk_first else 0,
                   "avg_risk_approved": round(sum(final_risk) / len(final_risk)) if final_risk else 0,
                   "issues_caught": sum(rule_counts.values())},
        "status": dict(Counter(s["status"] for s in subs)),
        "top_rules": [{"rule_id": k, "title": rules[k]["title"] if k in rules else k, "count": v} for k, v in rule_counts.most_common(8)],
        "by_creator": [{"creator": k, **dict(v), "total": sum(v.values())} for k, v in sorted(creator_counts.items(), key=lambda kv: -sum(kv[1].values()))],
        "by_channel": [{"channel": k, "count": v} for k, v in channel_counts.most_common()],
        "guideline_health": health,
        "has_demo": any(s["demo"] for s in subs),
    }


# ---------------------------------------------------------------- brand-book import

IMPORT_PATTERNS = [
    ("price", "Product price (MRP)", "INR", r"(?:price|mrp)\s*[:=\-–]\s*(?:₹|rs\.?|inr)\s?([\d,]+)"),
    ("max_discount", "Maximum discount", "%", r"max(?:imum)?\s+discount\s*[:=\-–]\s*(\d{1,3})\s?%"),
    ("warranty_years", "Warranty", "years", r"warranty\s*[:=\-–]\s*(\d{1,2})\s*(?:years?|yrs?)"),
    ("battery_hours", "Battery life (tested)", "hours", r"battery(?:\s+life)?\s*[:=\-–]\s*(\d{1,3})\s*(?:hours?|hrs?)"),
    ("ip_rating", "Water resistance rating", "", r"(?:water\s+resistance|ip\s+rating)\s*[:=\-–]\s*(IP[X\d]\d)"),
    ("tagline", "Approved tagline", "", r"tagline\s*[:=\-–]\s*[\"“]?([^\"”\n]{4,80})"),
    ("product_name", "Official product name", "", r"(?:official\s+)?product\s+name\s*[:=\-–]\s*([^\n]{3,60})"),
]
FACT_META = {k: (label, unit) for k, label, unit, _ in IMPORT_PATTERNS}


def _current_facts(org):
    return {f["key"]: f for f in db.q("SELECT * FROM facts WHERE org_id=? AND status='approved' AND (valid_to IS NULL OR valid_to='' OR valid_to>=?)",
                                      (org, db.today()))}


def _add_candidate(org, kind, payload, source, snippet, method):
    return db.ex("INSERT INTO candidates(org_id,kind,payload,source,snippet,method,status,created_at) VALUES(?,?,?,?,?,?,?,?)",
                 (org, kind, json.dumps(payload), source, (snippet or "")[:200], method, "pending", db.now()))


def import_brand_book(ctx: Ctx, filename: str, text: str, use_ai: bool = True) -> dict:
    require(ctx, "admin")
    org = ctx.org_id
    created = []
    existing = _current_facts(org)
    seen_keys, seen_terms = set(), set()
    pend = [json.loads(c["payload"]) | {"_kind": c["kind"]} for c in db.q("SELECT kind,payload FROM candidates WHERE org_id=? AND status='pending'", (org,))]
    pending_keys = {p.get("key") for p in pend if p["_kind"] == "fact"}
    pending_terms = {str(p.get("avoid", "")).lower() for p in pend if p["_kind"] == "term"}
    pending_conf = {str(p.get("term", "")).lower() for p in pend if p["_kind"] == "confidential"}

    def add_fact(key, val, snippet, method):
        if key in seen_keys or key in pending_keys:
            return
        label, unit = FACT_META[key]
        val = str(val).strip()
        val = val.replace(",", "").rstrip(".") if key not in ("tagline", "product_name") else val.strip("\"“” ").rstrip(".")
        cur = existing.get(key)
        change = "new" if not cur else ("same" if str(cur["value"]).lower() == val.lower() else "update")
        if change == "same":
            return
        seen_keys.add(key)
        created.append(_add_candidate(org, "fact", {"key": key, "label": label, "value": val, "unit": unit, "change": change,
                                                     "current": cur["value"] if cur else None}, filename, snippet, method))

    for key, label, unit, pat in IMPORT_PATTERNS:
        m = re.search(pat, text, re.I)
        if m:
            add_fact(key, m.group(1), text[max(0, m.start() - 40): m.end() + 40].replace("\n", " "), "pattern")
    for m in re.finditer(r"(?:avoid|don'?t\s+use|do\s+not\s+use)\s*[:\-–]?\s*[\"“']([^\"”']{2,40})[\"”']\s*(?:[,;]|→|->|-|–)?\s*(?:use|say|prefer)\s*[:\-–]?\s*[\"“']([^\"”']{2,40})[\"”']", text, re.I):
        avoid, prefer = m.group(1).strip(), m.group(2).strip()
        if avoid.lower() in seen_terms or avoid.lower() in pending_terms or db.one("SELECT id FROM terms WHERE org_id=? AND lower(avoid)=lower(?)", (org, avoid)):
            continue
        seen_terms.add(avoid.lower())
        created.append(_add_candidate(org, "term", {"avoid": avoid, "prefer": prefer}, filename, m.group(0), "pattern"))
    conf_now = [c.lower() for c in (db.get_meta(org, "confidential_terms") or [])] + list(pending_conf)
    for m in re.finditer(r"confidential\s*[:\-–]\s*([^\n]{3,80})", text, re.I):
        for item in re.split(r",|;| and ", m.group(1)):
            item = item.strip().strip(".\"“”")
            if len(item) < 3 or item.lower() in conf_now:
                continue
            conf_now.append(item.lower())
            created.append(_add_candidate(org, "confidential", {"term": item}, filename, m.group(0), "pattern"))
    ai_note = None
    missing = [k for k in FACT_META if k not in seen_keys and k not in existing]
    if use_ai and ai.available() and (missing or not created):
        res = ai.extract_brand_facts(text)
        if res.get("error"):
            ai_note = res["error"]
        else:
            for f in res["facts"]:
                add_fact(f["key"], f["value"], f.get("quote", ""), "AI (value verified in document)")
            for tm in res["terms"]:
                a = str(tm["avoid"]).strip()
                if a.lower() not in seen_terms and a.lower() not in pending_terms and not db.one("SELECT id FROM terms WHERE org_id=? AND lower(avoid)=lower(?)", (org, a)):
                    seen_terms.add(a.lower())
                    created.append(_add_candidate(org, "term", {"avoid": a, "prefer": str(tm["prefer"]).strip()}, filename, tm.get("quote", ""), "AI (verified)"))
            for c in res["confidential"]:
                term = str(c["term"]).strip()
                if term.lower() not in conf_now:
                    conf_now.append(term.lower())
                    created.append(_add_candidate(org, "confidential", {"term": term}, filename, c.get("quote", ""), "AI (verified)"))
    return {"created": len(created), "candidates": pending_candidates(org), "ai_note": ai_note,
            "message": None if created else "No new facts, terms or confidential items were found (they may already be in Brand Memory or waiting for approval)."}


def pending_candidates(org: int):
    out = db.q("SELECT * FROM candidates WHERE org_id=? AND status='pending' ORDER BY id", (org,))
    for c in out:
        c["payload"] = json.loads(c["payload"])
    return out


def _set_fact(org, key, label, value, unit, source) -> int:
    today = db.today()
    old = db.one("SELECT * FROM facts WHERE org_id=? AND key=? AND status='approved' AND (valid_to IS NULL OR valid_to='' OR valid_to>=?)", (org, key, today))
    if old:
        db.ex("UPDATE facts SET valid_to=? WHERE pk=?", ((date.today() - timedelta(days=1)).isoformat(), old["pk"]))
    n = db.one("SELECT COUNT(*) AS c FROM facts WHERE org_id=?", (org,))["c"] + 101
    v = db.bump_brand(org, f"{'Updated' if old else 'Added'} {label} = {value}" + (f" (from {source})" if source else ""))
    db.ex("INSERT INTO facts(org_id,id,key,label,value,unit,valid_from,valid_to,source,status,added_in) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
          (org, f"F-{n}", key, label, value, unit, today, None, source, "approved", v))
    return v


def decide_candidate(ctx: Ctx, cid: int, approve: bool) -> dict:
    require(ctx, "admin")
    org = ctx.org_id
    c = db.one("SELECT * FROM candidates WHERE id=? AND org_id=?", (cid, org))
    if not c:
        raise Denied("Candidate not found")
    if c["status"] != "pending":
        raise Conflict(f"This candidate was already {c['status']}.")
    p = json.loads(c["payload"])
    if not approve:
        db.ex("UPDATE candidates SET status='rejected' WHERE id=?", (cid,))
        return {"ok": True, "brand_version": db.brand_version(org)}
    if c["kind"] == "fact":
        _set_fact(org, p["key"], p["label"], p["value"], p.get("unit"), c["source"])
    elif c["kind"] == "term":
        db.ex("INSERT INTO terms(org_id,avoid,prefer,note,status) VALUES(?,?,?,?,?)", (org, p["avoid"], p["prefer"], f"Imported from {c['source']}", "approved"))
        db.bump_brand(org, f"Added term “{p['avoid']}” → “{p['prefer']}”")
    elif c["kind"] == "confidential":
        terms = db.get_meta(org, "confidential_terms") or []
        terms.append(p["term"])
        db.set_meta(org, "confidential_terms", terms)
        db.bump_brand(org, f"Marked “{p['term']}” as confidential")
    db.ex("UPDATE candidates SET status='approved' WHERE id=?", (cid,))
    return {"ok": True, "brand_version": db.brand_version(org)}


# ---------------------------------------------------------------- guideline-change impact preview

def _validate_change(change: dict) -> dict:
    kind = change.get("kind")
    if kind == "fact":
        key = change.get("key")
        if key not in FACT_META:
            raise Denied("Unknown fact")
        value = str(change.get("value", "")).strip()
        if not value:
            raise Denied("Enter a value")
        if key in ("price", "max_discount", "warranty_years", "battery_hours"):
            try:
                n = float(value.replace(",", ""))
            except ValueError:
                raise Denied("This fact needs a number.")
            if n <= 0 or (key == "max_discount" and n > 100):
                raise Denied("That number is out of range.")
            value = f"{n:g}"
        return {"kind": "fact", "key": key, "value": value, "source": _clip(change.get("source"), 120)}
    if kind == "rule":
        return {"kind": "rule", "rule_id": change.get("rule_id"), "enabled": change.get("enabled", True),
                **({"description": _clip(change.get("description"), 600)} if change.get("description") else {})}
    if kind == "term":
        a, p = _clip(change.get("avoid"), 60), _clip(change.get("prefer"), 60)
        if not a or not p:
            raise Denied("Enter both the word to avoid and the preferred word.")
        return {"kind": "term", "avoid": a, "prefer": p, "note": _clip(change.get("note"), 200)}
    if kind == "confidential":
        term = _clip(change.get("term"), 80)
        if not term:
            raise Denied("Enter a term")
        return {"kind": "confidential", "term": term}
    raise Denied("Unknown change type")


def _hypothetical(brand: dict, change: dict) -> dict:
    b = json.loads(json.dumps(brand))
    kind = change["kind"]
    if kind == "fact":
        key, value = change["key"], change["value"]
        label, unit = FACT_META.get(key, (key, ""))
        y = (date.today() - timedelta(days=1)).isoformat()
        for f in b["facts"]:
            if f["key"] == key and not (f.get("valid_to") and f["valid_to"] < b["today"]):
                f["valid_to"] = y
        b["facts"].append({"id": "F-new", "key": key, "label": label, "value": value, "unit": unit, "valid_from": b["today"],
                           "valid_to": None, "source": "proposed change", "status": "approved"})
    elif kind == "rule":
        for r in b["rules"]:
            if r["id"] == change["rule_id"]:
                r["enabled"] = 1 if change.get("enabled", True) else 0
    elif kind == "term":
        b["terms"].append({"id": 0, "avoid": change["avoid"], "prefer": change["prefer"], "note": "", "status": "approved"})
    elif kind == "confidential":
        b["meta"]["confidential_terms"] = list(b["meta"].get("confidential_terms") or []) + [change["term"]]
    b["version"] = brand["version"] + 1
    return b


def impact_preview(org: int, change: dict) -> dict:
    """Re-check every approved piece of content against the proposed Brand Memory, before the change is saved."""
    change = _validate_change(change)
    brand = db.brand_snapshot(org)
    after = _hypothetical(brand, change)
    rows = db.q("SELECT id, title, channel FROM submissions WHERE org_id=? AND status='approved' ORDER BY id", (org,))
    newly, cleared, unchanged = [], [], 0
    for s in rows:
        v = db.one("SELECT text FROM versions WHERE org_id=? AND submission_id=? ORDER BY version DESC LIMIT 1", (org, s["id"]))
        text = (v or {}).get("text") or ""
        before_f = engine.run_rules(text, brand)["findings"]
        after_f = engine.run_rules(text, after)["findings"]
        b_keys = {(f["rule_id"], f["quote"]) for f in before_f}
        a_keys = {(f["rule_id"], f["quote"]) for f in after_f}
        added = [f for f in after_f if (f["rule_id"], f["quote"]) not in b_keys]
        removed = [{"rule_id": r, "quote": q} for (r, q) in b_keys - a_keys]
        if added:
            newly.append({"id": s["id"], "title": s["title"], "channel": s["channel"], "text": text,
                          "findings": [{"rule_id": f["rule_id"], "quote": f["quote"], "message": f["message"], "severity": f["severity"]} for f in added]})
        elif removed:
            cleared.append({"id": s["id"], "title": s["title"], "findings": removed})
        else:
            unchanged += 1
    return {"change": change, "checked": len(rows), "newly_flagged": newly, "no_longer_flagged": cleared, "unchanged": unchanged}


def apply_change(ctx: Ctx, change: dict) -> dict:
    require(ctx, "admin")
    org = ctx.org_id
    c = _validate_change(change)
    kind = c["kind"]
    if kind == "fact":
        label, unit = FACT_META[c["key"]]
        v = _set_fact(org, c["key"], label, c["value"], unit, c.get("source") or f"Set by {ctx.actor}")
    elif kind == "rule":
        r = db.one("SELECT * FROM rules WHERE org_id=? AND id=?", (org, c["rule_id"]))
        if not r:
            raise Denied("Rule not found")
        if c.get("description"):
            db.ex("UPDATE rules SET description=? WHERE org_id=? AND id=?", (c["description"], org, r["id"]))
        if "enabled" in change:
            db.ex("UPDATE rules SET enabled=? WHERE org_id=? AND id=?", (1 if change["enabled"] else 0, org, r["id"]))
        v = db.bump_brand(org, f"Updated rule {r['id']}")
    elif kind == "term":
        if db.one("SELECT id FROM terms WHERE org_id=? AND lower(avoid)=lower(?)", (org, c["avoid"])):
            raise Conflict(f"“{c['avoid']}” is already on the terminology list.")
        db.ex("INSERT INTO terms(org_id,avoid,prefer,note,status) VALUES(?,?,?,?,'approved')", (org, c["avoid"], c["prefer"], c.get("note", "")))
        v = db.bump_brand(org, f"Added term “{c['avoid']}” → “{c['prefer']}”")
    else:
        terms = db.get_meta(org, "confidential_terms") or []
        if c["term"].lower() in [x.lower() for x in terms]:
            raise Conflict("Already confidential.")
        db.set_meta(org, "confidential_terms", terms + [c["term"]])
        v = db.bump_brand(org, f"Marked “{c['term']}” as confidential")
    return {"ok": True, "brand_version": v}


def set_logo(ctx: Ctx, data_url: str, name: str) -> dict:
    require(ctx, "admin")
    import io
    from PIL import Image
    try:
        raw, _mime = vision.decode_data_url(data_url)
        Image.open(io.BytesIO(raw)).verify()
    except Exception:  # noqa: BLE001
        raise Denied("That file is not a valid image.")
    if len(raw) > 2 * 1024 * 1024:
        raise Denied("Logo must be under 2 MB.")
    db.ex("DELETE FROM assets WHERE org_id=? AND kind='logo'", (ctx.org_id,))
    db.ex("INSERT INTO assets(org_id,kind,name,data,created_at) VALUES(?,?,?,?,?)", (ctx.org_id, "logo", _clip(name, 80) or "Logo", data_url, db.now()))
    return {"ok": True, "brand_version": db.bump_brand(ctx.org_id, "Updated the approved logo")}


def set_palette(ctx: Ctx, colours: list[dict]) -> dict:
    require(ctx, "admin")
    clean = []
    for c in (colours or [])[:12]:
        hx = str(c.get("hex", "")).strip()
        if not re.fullmatch(r"#?[0-9a-fA-F]{6}", hx):
            raise Denied(f"“{hx}” is not a valid hex colour (e.g. #1F5FAE).")
        clean.append((_clip(c.get("name"), 40) or "Colour", "#" + hx.lstrip("#").upper()))
    if not clean:
        raise Denied("Add at least one colour.")
    db.ex("DELETE FROM palette WHERE org_id=?", (ctx.org_id,))
    for n, hx in clean:
        db.ex("INSERT INTO palette(org_id,name,hex) VALUES(?,?,?)", (ctx.org_id, n, hx))
    return {"ok": True, "brand_version": db.bump_brand(ctx.org_id, "Updated the colour palette")}


def set_brand_profile(ctx: Ctx, data: dict) -> dict:
    require(ctx, "admin")
    if data.get("brand_name"):
        db.set_meta(ctx.org_id, "brand_name", _clip(data["brand_name"], 80))
    if data.get("tone"):
        db.set_meta(ctx.org_id, "tone", _clip(data["tone"], 120))
    if data.get("voice_profile"):
        db.set_meta(ctx.org_id, "voice_profile", _clip(data["voice_profile"], 400))
    return {"ok": True, "brand_version": db.bump_brand(ctx.org_id, "Updated brand profile (name / tone / voice)")}


def role_label(r):
    return ROLE_LABEL.get(r, r)
