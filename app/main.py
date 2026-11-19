"""BrandProof AI — FastAPI application (REST API + static frontend)."""
from __future__ import annotations

import base64
import json
import logging
import os
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import ai, auth, certs, db, service
from .auth import COOKIE, Ctx
from .extract import extract_text

STATIC = os.path.join(os.path.dirname(__file__), "..", "static")
MAX_UPLOAD = 6 * 1024 * 1024
MAX_BODY = 12 * 1024 * 1024
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "").strip()
log = logging.getLogger("brandproof")

app = FastAPI(title="BrandProof AI", version="3.0", lifespan=None,
              description="Evidence-driven brand governance: check content against approved guidelines, facts and assets before it is published.")


# ---------------------------------------------------------------- errors & limits

@app.middleware("http")
async def limit_body(request: Request, call_next):
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > MAX_BODY:
        return JSONResponse(status_code=413, content={"detail": "Upload too large (max 6 MB per file)."})
    return await call_next(request)


@app.exception_handler(auth.AuthError)
def _auth_err(_, exc):
    return JSONResponse(status_code=401, content={"detail": str(exc), "code": "auth"})


@app.exception_handler(auth.Forbidden)
@app.exception_handler(service.Denied)
def _denied(_, exc):
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(service.Conflict)
def _conflict(_, exc):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(RequestValidationError)
def _invalid(_, exc):
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(x) for x in first.get("loc", [])[1:]) or "input"
    return JSONResponse(status_code=422, content={"detail": f"Invalid {field}: {first.get('msg', 'please check your input')}."})


@app.exception_handler(Exception)
def _crash(_, exc):
    log.exception("Unhandled error")
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on our side. Your data is safe — please try again."})


@asynccontextmanager
async def lifespan(_app):
    db.conn()
    try:
        auth.cleanup_demos()
    except Exception:  # noqa: BLE001
        log.exception("cleanup failed")
    yield


app.router.lifespan_context = lifespan


# ---------------------------------------------------------------- context

def ctx_dep(request: Request, x_acting_role: str | None = Header(default=None)) -> Ctx:
    return auth.context(request.cookies.get(COOKIE), x_acting_role)


def _set_cookie(request: Request, response: Response, token: str, demo: bool):
    secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", secure=secure,
                        max_age=(2 if demo else auth.SESSION_DAYS) * 86400, path="/")


def me_payload(c: Ctx) -> dict:
    return {"org_id": c.org_id, "org_name": c.org_name, "demo": c.demo, "role": c.role, "roles": c.roles,
            "user": None if c.demo else {"id": c.user_id, "name": c.user_name, "email": c.user_email},
            "actor": c.actor, "members": c.members, "brand_version": db.brand_version(c.org_id)}


# ---------------------------------------------------------------- models

class SignupIn(BaseModel):
    name: str = Field(max_length=80)
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)
    org_name: str = Field(max_length=80)
    template: str = "demo"


class LoginIn(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


class AcceptIn(BaseModel):
    name: str = ""
    email: str
    password: str


class CheckIn(BaseModel):
    text: str = Field(default="", max_length=20000)
    goal: str = Field(default="", max_length=200)
    confidential: bool = False
    use_ai: bool = True
    image: str | None = None
    alt_text: str = Field(default="", max_length=300)
    pages: list[int] | None = None


class FixIn(BaseModel):
    text: str = Field(max_length=20000)
    findings: list[dict]
    accepted: list[str]
    goal: str = ""


class SubmitIn(BaseModel):
    title: str = Field(default="Untitled", max_length=120)
    channel: str = "Social post"
    goal: str = ""
    ai_generated: bool = False
    confidential: bool = False
    text: str = Field(default="", max_length=20000)
    original_text: str | None = Field(default=None, max_length=20000)
    dismissals: list[dict] = Field(default_factory=list)
    image: str | None = None
    alt_text: str = ""


class ActionIn(BaseModel):
    action: str
    reason: str | None = None
    finding_key: str | None = None
    text: str | None = Field(default=None, max_length=20000)
    confidential: bool = False


class ChangeIn(BaseModel):
    kind: str
    key: str | None = None
    value: str | None = None
    source: str | None = None
    rule_id: str | None = None
    enabled: bool | None = None
    description: str | None = None
    avoid: str | None = None
    prefer: str | None = None
    note: str | None = None
    term: str | None = None


class InviteIn(BaseModel):
    roles: list[str]
    email: str | None = None


class RolesIn(BaseModel):
    roles: list[str]


class LogoIn(BaseModel):
    image: str
    name: str = "Logo"


class PaletteIn(BaseModel):
    colours: list[dict]


class ProfileIn(BaseModel):
    brand_name: str | None = None
    tone: str | None = None
    voice_profile: str | None = None


class FeedbackIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    role: str = Field(default="", max_length=80)
    ease: int = Field(ge=1, le=5)
    trust: int = Field(ge=1, le=5)
    useful: int = Field(ge=1, le=5)
    liked: str = Field(default="", max_length=1000)
    improve: str = Field(default="", max_length=1000)


class VerifyIn(BaseModel):
    text: str = Field(max_length=20000)


def _decode_image(data_url: str | None):
    if not data_url:
        return None, None
    try:
        head, b64 = data_url.split(",", 1)
        raw = base64.b64decode(b64)
        mime = head[5:].split(";")[0]
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "Invalid image data")
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "Image too large (max 6 MB)")
    if not mime.startswith("image/"):
        raise HTTPException(400, "That file is not an image.")
    try:
        import io
        from PIL import Image
        Image.open(io.BytesIO(raw)).verify()
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "This image could not be read. Try a PNG or JPG.")
    return raw, mime


# ---------------------------------------------------------------- public / auth

@app.get("/api/health")
def health():
    return {"ok": True, "ai": ai.available(), "model": ai.model_name(), "db": "postgres" if db.IS_PG else "sqlite", "version": app.version}


class TryIn(BaseModel):
    text: str = Field(min_length=1, max_length=1500)


_try_hits: dict = {}


@app.post("/api/try")
def try_caption(body: TryIn, request: Request):
    """Public, no sign-up: rules-only check of one short caption against the ABC Electronics demo brand. Nothing is stored."""
    import time as _t
    from . import engine
    from .benchmark_runner import bench_org
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
    now = _t.time()
    hits = [h for h in _try_hits.get(ip, []) if now - h < 60]
    if len(hits) >= 20:
        raise HTTPException(429, "Too many tries in a minute. Wait a moment, or start the demo for the full product.")
    _try_hits[ip] = hits + [now]
    if len(_try_hits) > 5000:
        _try_hits.clear()
    brand = db.brand_snapshot(bench_org())
    r = engine.run_rules(body.text, brand)
    return {"findings": r["findings"], "risk": r["risk"],
            "brand": brand["meta"].get("brand_name", "ABC Electronics"), "brand_version": brand.get("version")}


@app.post("/api/demo/start")
def demo_start(request: Request, response: Response):
    old = request.cookies.get(COOKIE)
    if old:
        auth.end_session(old)
    token, org = auth.start_demo()
    _set_cookie(request, response, token, True)
    return me_payload(auth.context(token, "creator"))


@app.post("/api/auth/signup")
def signup(body: SignupIn, request: Request, response: Response):
    token, org = auth.signup(body.name, body.email, body.password, body.org_name, body.template)
    _set_cookie(request, response, token, False)
    return me_payload(auth.context(token, None))


@app.post("/api/auth/login")
def login(body: LoginIn, request: Request, response: Response):
    token = auth.login(body.email, body.password)
    _set_cookie(request, response, token, False)
    return me_payload(auth.context(token, None))


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    auth.end_session(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def me(c: Ctx = Depends(ctx_dep)):
    return me_payload(c)


@app.get("/api/invites/{code}")
def invite(code: str):
    return auth.invite_info(code)


@app.post("/api/invites/{code}/accept")
def invite_accept(code: str, body: AcceptIn, request: Request, response: Response):
    token = auth.accept_invite(code, body.name, body.email, body.password)
    _set_cookie(request, response, token, False)
    return me_payload(auth.context(token, None))


# ---------------------------------------------------------------- team

@app.get("/api/team")
def team(c: Ctx = Depends(ctx_dep)):
    if c.demo:
        return {"demo": True, "members": [{"name": n, "roles": [r], "demo": True} for r, n in auth.DEMO_PEOPLE.items()], "invites": []}
    invites = db.q("SELECT code, roles, email, created_at FROM invites WHERE org_id=? AND used_by IS NULL ORDER BY id DESC", (c.org_id,)) if c.role == "admin" else []
    return {"demo": False, "members": auth.members(c), "invites": invites}


@app.post("/api/team/invites")
def team_invite(body: InviteIn, c: Ctx = Depends(ctx_dep)):
    return auth.create_invite(c, body.roles, body.email)


@app.post("/api/team/members/{user_id}")
def team_roles(user_id: int, body: RolesIn, c: Ctx = Depends(ctx_dep)):
    auth.set_member_roles(c, user_id, body.roles)
    return {"ok": True}


@app.delete("/api/team/members/{user_id}")
def team_remove(user_id: int, c: Ctx = Depends(ctx_dep)):
    auth.remove_member(c, user_id)
    return {"ok": True}


# ---------------------------------------------------------------- brand memory

@app.get("/api/brand")
def brand(c: Ctx = Depends(ctx_dep)):
    b = db.brand_snapshot(c.org_id)
    b["versions"] = db.q("SELECT version, note, created_at FROM brand_versions WHERE org_id=? ORDER BY version DESC", (c.org_id,))
    b["candidates"] = service.pending_candidates(c.org_id)
    b["logo_data"] = db.logo_data(c.org_id)
    return b


@app.post("/api/brand/impact")
def brand_impact(body: ChangeIn, c: Ctx = Depends(ctx_dep)):
    return service.impact_preview(c.org_id, body.model_dump(exclude_none=True))


@app.post("/api/brand/change")
def brand_change(body: ChangeIn, c: Ctx = Depends(ctx_dep)):
    return service.apply_change(c, body.model_dump(exclude_none=True))


@app.post("/api/brand/logo")
def brand_logo(body: LogoIn, c: Ctx = Depends(ctx_dep)):
    return service.set_logo(c, body.image, body.name)


@app.post("/api/brand/palette")
def brand_palette(body: PaletteIn, c: Ctx = Depends(ctx_dep)):
    return service.set_palette(c, body.colours)


@app.post("/api/brand/profile")
def brand_profile(body: ProfileIn, c: Ctx = Depends(ctx_dep)):
    return service.set_brand_profile(c, body.model_dump(exclude_none=True))


@app.post("/api/brand/import")
async def import_book(file: UploadFile = File(...), c: Ctx = Depends(ctx_dep)):
    auth.require(c, "admin")
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "File too large (max 6 MB)")
    try:
        out = extract_text(file.filename or "", data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "Could not read this file. Is it a valid PDF, DOCX or TXT?")
    if not out["text"].strip():
        raise HTTPException(400, "No text found in this file (scanned PDFs are not supported yet).")
    return service.import_brand_book(c, file.filename or "upload", out["text"])


@app.post("/api/brand/candidates/{cid}/{decision}")
def decide(cid: int, decision: str, c: Ctx = Depends(ctx_dep)):
    if decision not in ("approve", "reject"):
        raise HTTPException(400, "Decision must be approve or reject")
    return service.decide_candidate(c, cid, decision == "approve")


# ---------------------------------------------------------------- checking

@app.post("/api/check")
def check(body: CheckIn, c: Ctx = Depends(ctx_dep)):
    if not body.text.strip() and not body.image:
        raise HTTPException(400, "Add some text or an image to check.")
    img, mime = _decode_image(body.image)
    return service.run_check(c.org_id, body.text, confidential=body.confidential, use_ai=body.use_ai, image_bytes=img,
                             image_mime=mime, alt_text=body.alt_text, goal=body.goal, pages=body.pages)


@app.post("/api/extract")
async def extract(file: UploadFile = File(...), c: Ctx = Depends(ctx_dep)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "The file is empty.")
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "File too large (max 6 MB)")
    name = (file.filename or "").lower()
    if name.endswith((".png", ".jpg", ".jpeg", ".webp")):
        mime = file.content_type if (file.content_type or "").startswith("image/") else "image/png"
        url = f"data:{mime};base64," + base64.b64encode(data).decode()
        _decode_image(url)
        return {"kind": "image", "image": url, "filename": file.filename}
    try:
        out = extract_text(file.filename or "", data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "Could not read this file. Is it a valid PDF/DOCX?")
    if not out["text"].strip():
        raise HTTPException(400, "No text found in this file. If it is a scanned PDF, upload the page as an image instead.")
    out["text"] = out["text"][:20000]
    out["filename"] = file.filename
    return out


@app.post("/api/fix")
def fix(body: FixIn, c: Ctx = Depends(ctx_dep)):
    return service.fix(c.org_id, body.text, body.findings, body.accepted, body.goal)


# ---------------------------------------------------------------- workflow

@app.get("/api/submissions")
def submissions(c: Ctx = Depends(ctx_dep)):
    return service.list_submissions(c.org_id)


@app.post("/api/submissions")
def submit(body: SubmitIn, c: Ctx = Depends(ctx_dep)):
    if body.image:
        _decode_image(body.image)
    return service.create_submission(c, body.model_dump())


@app.get("/api/submissions/{sid}")
def submission(sid: int, c: Ctx = Depends(ctx_dep)):
    s = service.get_submission(c.org_id, sid)
    if not s:
        raise HTTPException(404, "This submission does not exist in your workspace.")
    return s


@app.post("/api/submissions/{sid}/action")
def action(sid: int, body: ActionIn, c: Ctx = Depends(ctx_dep)):
    return service.act(c, sid, body.model_dump())


# ---------------------------------------------------------------- insights & certificates

@app.get("/api/insights")
def insights(c: Ctx = Depends(ctx_dep)):
    return service.insights(c.org_id)


@app.post("/api/insights/suggest/{rule_id}")
def suggest(rule_id: str, c: Ctx = Depends(ctx_dep)):
    r = db.one("SELECT * FROM rules WHERE org_id=? AND id=?", (c.org_id, rule_id))
    if not r:
        raise HTTPException(404, "Rule not found")
    reasons = [d["reason"] for d in db.q("SELECT reason FROM decisions WHERE org_id=? AND rule_id=? AND reason<>''", (c.org_id, rule_id))]
    text = ai.suggest_rule(r, reasons)
    used_ai = bool(text)
    if not text:
        text = (f"{r['description']} Exception: factual time limits for a dated, approved offer (e.g. “Offer ends Sunday”) are allowed; "
                "pressure phrases that are not tied to a real deadline (“Hurry”, “Buy now or regret”) are not.") if rule_id == "R-VOICE-02" else \
               f"{r['description']} Add one allowed and one not-allowed example to make this rule clear."
    return {"rule_id": rule_id, "suggestion": text, "ai": used_ai}


@app.get("/api/certificates")
def certificates(c: Ctx = Depends(ctx_dep)):
    return {"certificates": certs.all_certs(c.org_id), "chain": certs.verify_chain(c.org_id)}


@app.post("/api/certificates/verify")
def verify(body: VerifyIn, c: Ctx = Depends(ctx_dep)):
    return certs.verify_text(c.org_id, body.text)


# ---------------------------------------------------------------- feedback, about, benchmark

@app.post("/api/feedback")
def feedback(body: FeedbackIn, request: Request):
    org = None
    try:
        org = auth.context(request.cookies.get(COOKIE), None).org_id
    except Exception:  # noqa: BLE001
        pass
    db.ex("INSERT INTO feedback(org_id,name,role,ease,trust,useful,liked,improve,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
          (org, body.name.strip(), body.role.strip(), body.ease, body.trust, body.useful, body.liked.strip(), body.improve.strip(), db.now()))
    return {"ok": True}


@app.get("/api/feedback")
def feedback_list():
    rows = db.q("SELECT name, role, ease, trust, useful, liked, improve, created_at FROM feedback ORDER BY id DESC LIMIT 100")
    avg = {k: round(sum(r[k] for r in rows) / len(rows), 2) if rows else None for k in ("ease", "trust", "useful")}
    return {"count": len(rows), "average": avg, "items": rows}


@app.get("/api/about")
def about():
    return {
        "ai": {"provider": "Google Gemini API" if ai.available() else "Not configured", "model": ai.model_name(),
               "used_for": ["tone, messaging and implied/paraphrased claims (English, Hindi, Hinglish)", "reading text inside images",
                            "logo check fallback", "alt-text drafts", "free-form brand-book extraction", "clearer-rule drafts"]},
        "deterministic_checks": ["prices (digits or words, EN/HI/Hinglish) & outdated prices", "discount limits (incl. “half price”)", "T&C disclaimer",
                                 "warranty (incl. lifetime/paraphrased)", "battery (incl. “never runs out”) & IP rating", "superlatives (EN/HI)",
                                 "absolute guarantees", "terminology & product name", "hype / caps / exclamations", "urgency (EN/HI)",
                                 "confidential terms", "sentence length", "palette ΔE", "per-text contrast", "logo pixel match", "alt text"],
        "storage": "PostgreSQL" if db.IS_PG else "SQLite",
    }


@app.get("/api/benchmark")
def benchmark():
    from .benchmark_runner import latest
    return latest()


@app.post("/api/benchmark/run")
def benchmark_run(request: Request, x_admin_token: str | None = Header(default=None), x_acting_role: str | None = Header(default=None)):
    """Server operators (X-Admin-Token) can always run it; any Brand Admin can start it, at most once per cooldown window."""
    from .benchmark_runner import run_ai_async
    if ADMIN_TOKEN and x_admin_token == ADMIN_TOKEN:
        return run_ai_async(force=True)
    c = auth.context(request.cookies.get(COOKIE), x_acting_role)
    auth.require(c, "admin")
    return run_ai_async()


# ---------------------------------------------------------------- static frontend

app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"), headers={"Cache-Control": "no-cache"})
