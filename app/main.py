"""BrandProof AI — FastAPI application."""
from __future__ import annotations

import base64
import json
import os

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import ai, certs, db, seed, service
from .extract import extract_text

STATIC = os.path.join(os.path.dirname(__file__), "..", "static")
MAX_UPLOAD = 6 * 1024 * 1024

app = FastAPI(title="BrandProof AI", version="2.0",
              description="Evidence-driven brand governance: check content against approved guidelines, facts and assets before it is published.")


@app.on_event("startup")
def _startup():
    seed.seed()


@app.exception_handler(service.Denied)
def _denied(_, exc: service.Denied):
    return JSONResponse(status_code=403, content={"detail": str(exc)})


# ---------------------------------------------------------------- models

class CheckIn(BaseModel):
    text: str = ""
    goal: str = ""
    confidential: bool = False
    use_ai: bool = True
    image: str | None = None  # data URL
    alt_text: str = ""
    pages: list[int] | None = None


class FixIn(BaseModel):
    text: str
    findings: list[dict]
    accepted: list[str]
    goal: str = ""


class SubmitIn(BaseModel):
    title: str
    channel: str = "Social post"
    creator: str = "Riya Sharma"
    goal: str = ""
    ai_generated: bool = False
    confidential: bool = False
    text: str
    original_text: str | None = None
    dismissals: list[dict] = Field(default_factory=list)
    image: str | None = None
    alt_text: str = ""
    role: str = "creator"


class ActionIn(BaseModel):
    action: str
    role: str
    name: str | None = None
    reason: str | None = None
    finding_key: str | None = None
    text: str | None = None
    confidential: bool = False


class FactIn(BaseModel):
    key: str
    label: str
    value: str
    unit: str = ""
    source: str = "Added by Brand Admin"
    role: str = "admin"


class TermIn(BaseModel):
    avoid: str
    prefer: str
    note: str = ""
    role: str = "admin"


class RoleIn(BaseModel):
    role: str


class FeedbackIn(BaseModel):
    name: str
    role: str = ""
    ease: int = Field(ge=1, le=5)
    trust: int = Field(ge=1, le=5)
    useful: int = Field(ge=1, le=5)
    liked: str = ""
    improve: str = ""


class VerifyIn(BaseModel):
    text: str


def _decode_image(data_url: str | None):
    if not data_url:
        return None, None
    try:
        head, b64 = data_url.split(",", 1)
        raw = base64.b64decode(b64)
    except Exception:
        raise HTTPException(400, "Invalid image data")
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "Image too large (max 6 MB)")
    return raw, head[5:].split(";")[0]


# ---------------------------------------------------------------- API

@app.get("/api/health")
def health():
    return {"ok": True, "ai": ai.available(), "model": ai.model_name(), "brand_version": db.brand_version()}


@app.get("/api/brand")
def brand():
    b = db.brand_snapshot()
    b["versions"] = db.q("SELECT * FROM brand_versions ORDER BY version DESC")
    b["candidates"] = service.pending_candidates()
    return b


@app.post("/api/check")
def check(body: CheckIn):
    if not body.text.strip() and not body.image:
        raise HTTPException(400, "Add some text or an image to check.")
    img, mime = _decode_image(body.image)
    return service.run_check(body.text, confidential=body.confidential, use_ai=body.use_ai,
                             image_bytes=img, image_mime=mime, alt_text=body.alt_text, goal=body.goal, pages=body.pages)


@app.post("/api/extract")
async def extract(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "File too large (max 6 MB)")
    name = (file.filename or "").lower()
    if name.endswith((".png", ".jpg", ".jpeg", ".webp")):
        mime = file.content_type or "image/png"
        return {"kind": "image", "image": f"data:{mime};base64," + base64.b64encode(data).decode(), "filename": file.filename}
    try:
        out = extract_text(file.filename or "", data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        raise HTTPException(400, "Could not read this file. Is it a valid PDF/DOCX?")
    out["filename"] = file.filename
    return out


@app.post("/api/fix")
def fix(body: FixIn):
    return service.fix(body.text, body.findings, body.accepted, body.goal)


@app.get("/api/submissions")
def submissions():
    return service.list_submissions()


@app.post("/api/submissions")
def submit(body: SubmitIn):
    if body.role != "creator":
        raise service.Denied("Switch to the Creator role to submit content.")
    if not body.text.strip() and not body.image:
        raise HTTPException(400, "Nothing to submit")
    return service.create_submission(body.model_dump())


@app.get("/api/submissions/{sid}")
def submission(sid: int):
    s = service.get_submission(sid)
    if not s:
        raise HTTPException(404, "Not found")
    return s


@app.post("/api/submissions/{sid}/action")
def action(sid: int, body: ActionIn):
    return service.act(sid, body.model_dump())


@app.get("/api/insights")
def insights():
    return service.insights()


@app.post("/api/insights/suggest/{rule_id}")
def suggest(rule_id: str):
    r = db.one("SELECT * FROM rules WHERE id=?", (rule_id,))
    if not r:
        raise HTTPException(404, "Rule not found")
    reasons = [d["reason"] for d in db.q("SELECT reason FROM decisions WHERE rule_id=? AND reason<>''", (rule_id,))]
    text = ai.suggest_rule(r, reasons)
    if not text:
        text = (f"{r['description']} Exception: factual time limits for a dated, approved offer (e.g. “Offer ends Sunday”) are allowed; "
                "pressure phrases that are not tied to a real deadline (“Hurry”, “Buy now or regret”) are not.") if rule_id == "R-VOICE-02" else \
               f"{r['description']} Add one allowed and one not-allowed example to make this rule clear."
    return {"rule_id": rule_id, "suggestion": text, "ai": ai.available()}


@app.post("/api/brand/rules/{rule_id}/update")
def update_rule(rule_id: str, body: dict):
    if body.get("role") != "admin":
        raise service.Denied("Only the Brand Admin can edit rules.")
    r = db.one("SELECT * FROM rules WHERE id=?", (rule_id,))
    if not r:
        raise HTTPException(404, "Rule not found")
    if "description" in body and body["description"].strip():
        db.ex("UPDATE rules SET description=? WHERE id=?", (body["description"].strip(), rule_id))
    if "enabled" in body:
        db.ex("UPDATE rules SET enabled=? WHERE id=?", (1 if body["enabled"] else 0, rule_id))
    v = db.bump_brand(f"Updated rule {rule_id}")
    return {"ok": True, "brand_version": v}


@app.post("/api/brand/facts")
def add_fact(body: FactIn):
    if body.role != "admin":
        raise service.Denied("Only the Brand Admin can change Brand Memory.")
    from datetime import date, timedelta
    old = db.one("SELECT * FROM facts WHERE key=? AND status='approved' AND (valid_to IS NULL OR valid_to='' OR valid_to>=?)", (body.key, db.today()))
    if old:
        db.ex("UPDATE facts SET valid_to=? WHERE id=?", ((date.today() - timedelta(days=1)).isoformat(), old["id"]))
    n = db.one("SELECT COUNT(*) c FROM facts")["c"] + 101
    v = db.bump_brand(f"{'Updated' if old else 'Added'} {body.label} = {body.value}")
    db.ex("INSERT INTO facts(id,key,label,value,unit,valid_from,valid_to,source,status,added_in) VALUES(?,?,?,?,?,?,?,?,?,?)",
          (f"F-{n}", body.key, body.label, body.value, body.unit, db.today(), None, body.source, "approved", v))
    return {"ok": True, "brand_version": v}


@app.post("/api/brand/terms")
def add_term(body: TermIn):
    if body.role != "admin":
        raise service.Denied("Only the Brand Admin can change Brand Memory.")
    db.ex("INSERT INTO terms(avoid,prefer,note,status) VALUES(?,?,?,'approved')", (body.avoid.strip(), body.prefer.strip(), body.note))
    return {"ok": True, "brand_version": db.bump_brand(f"Added term “{body.avoid}” → “{body.prefer}”")}


@app.post("/api/brand/import")
async def import_book(file: UploadFile = File(...), role: str = Form("admin")):
    if role != "admin":
        raise service.Denied("Only the Brand Admin can import a brand book.")
    data = await file.read()
    try:
        out = extract_text(file.filename or "", data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return service.import_brand_book(file.filename or "upload", out["text"])


@app.post("/api/brand/candidates/{cid}/{decision}")
def decide(cid: int, decision: str, body: RoleIn):
    return service.decide_candidate(cid, decision == "approve", body.role)


@app.get("/api/certificates")
def certificates():
    return {"certificates": certs.all_certs(), "chain": certs.verify_chain()}


@app.post("/api/certificates/verify")
def verify(body: VerifyIn):
    return certs.verify_text(body.text)


@app.post("/api/feedback")
def feedback(body: FeedbackIn):
    db.ex("INSERT INTO feedback(name,role,ease,trust,useful,liked,improve,created_at) VALUES(?,?,?,?,?,?,?,?)",
          (body.name, body.role, body.ease, body.trust, body.useful, body.liked, body.improve, db.now()))
    return {"ok": True}


@app.get("/api/feedback")
def feedback_list():
    rows = db.q("SELECT * FROM feedback ORDER BY id DESC")
    avg = {k: round(sum(r[k] for r in rows) / len(rows), 2) if rows else None for k in ("ease", "trust", "useful")}
    return {"count": len(rows), "average": avg, "items": rows}


@app.get("/api/about")
def about():
    return {
        "ai": {"provider": "Google Gemini API" if ai.available() else "Not configured", "model": ai.model_name(),
               "used_for": ["tone & messaging judgement", "implied-claim detection", "rewrite suggestions", "alt-text drafts", "clearer-rule drafts"]},
        "deterministic_checks": ["prices & outdated prices", "discount limits", "T&C disclaimer", "warranty", "battery & IP rating",
                                 "superlatives", "absolute guarantees", "terminology & product name", "hype / caps / exclamations",
                                 "urgency language", "confidential terms", "sentence length", "palette ΔE", "contrast", "alt text"],
        "brand_version": db.brand_version(),
    }


# ---------------------------------------------------------------- static frontend

app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))
