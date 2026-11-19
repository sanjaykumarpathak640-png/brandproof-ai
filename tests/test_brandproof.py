"""BrandProof AI test suite — run with `pytest -q`. No network needed (AI calls are mocked)."""
import base64
import json
import os

os.environ["DB_PATH"] = "/tmp/brandproof_test.db"
for suffix in ("", "-wal", "-shm"):
    if os.path.exists(os.environ["DB_PATH"] + suffix):
        os.remove(os.environ["DB_PATH"] + suffix)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import ai  # noqa: E402
from app.main import app  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
RISKY = "ABC Electronics – India's No. 1 Brand! Buy SoundPods Pro for just ₹7,000. Get 50% OFF. 100% guaranteed performance with lifetime warranty!!"


def demo_client():
    c = TestClient(app)
    c.__enter__()
    assert c.post("/api/demo/start").status_code == 200
    return c


def H(role):
    return {"X-Acting-Role": role}


def img(name):
    return "data:image/png;base64," + base64.b64encode(open(os.path.join(ROOT, "static", "samples", name), "rb").read()).decode()


@pytest.fixture(scope="module")
def C():
    return demo_client()


def rules(c, text):
    r = c.post("/api/check", json={"text": text, "use_ai": False}, headers=H("creator"))
    assert r.status_code == 200, r.text
    return {f["rule_id"] for f in r.json()["findings"]}


# ---------------------------------------------------------------- access & isolation

def test_api_requires_a_session():
    c = TestClient(app)
    assert c.post("/api/check", json={"text": "x"}).status_code == 401
    assert c.get("/api/submissions").status_code == 401


def test_demo_workspaces_are_isolated(C):
    other = demo_client()
    s = other.post("/api/submissions", json={"title": "secret", "text": "Hello"}, headers=H("creator")).json()
    assert C.get(f"/api/submissions/{s['id']}").status_code == 404
    assert all(x["title"] != "secret" for x in C.get("/api/submissions").json())


# ---------------------------------------------------------------- rule engine (English, Hindi, Hinglish, words)

def test_risky_ad_flags_all_core_issues(C):
    assert {"R-PRC-01", "R-PRC-02", "R-WAR-01", "R-CLM-01", "R-CLM-02", "R-PRC-03", "R-VOICE-01"} <= rules(C, RISKY)


def test_clean_copy_passes(C):
    assert rules(C, "SoundPods Pro – Smart Technology for Everyday Life. Now ₹10,000 with a 2-year warranty.") == set()


def test_valid_offer_price_and_percent_guarantee_not_flagged(C):
    assert "R-PRC-01" not in rules(C, "Get SoundPods Pro for ₹8,500 with up to 15% off. T&C apply.")
    assert rules(C, "100% guaranteed performance.") == {"R-CLM-02"}


@pytest.mark.parametrize("text,expected", [
    ("Buy it for seven thousand rupees.", {"R-PRC-01"}),
    ("SoundPods Pro sirf saat hazaar rupaye mein.", {"R-PRC-01"}),
    ("SoundPods Pro सिर्फ सात हज़ार रुपये में।", {"R-PRC-01"}),
    ("Get fifty percent off. T&C apply.", {"R-PRC-02"}),
    ("SoundPods Pro aadhe daam par! T&C apply.", {"R-PRC-02"}),
    ("SoundPods Pro पर पचास प्रतिशत की छूट। शर्तें लागू।", {"R-PRC-02"}),
    ("SoundPods Pro ke saath aajeevan warranty.", {"R-WAR-01"}),
    ("SoundPods Pro के साथ आजीवन वारंटी।", {"R-WAR-01"}),
    ("With SoundPods Pro, your battery never runs out.", {"R-SPEC-01"}),
    ("ABC – भारत का नंबर 1 ऑडियो ब्रांड।", {"R-CLM-01"}),
    ("Jaldi karo, stock kam hai.", {"R-VOICE-02"}),
])
def test_multilingual_and_words(C, text, expected):
    assert rules(C, text) == expected


def test_outdated_price_cites_expired_fact(C):
    r = C.post("/api/check", json={"text": "Now only ₹12,000.", "use_ai": False}, headers=H("creator")).json()
    f = next(f for f in r["findings"] if f["rule_id"] == "R-PRC-01")
    assert "outdated" in f["message"] and any("expired" in e["ref"] for e in f["evidence"])


def test_every_finding_has_evidence(C):
    for f in C.post("/api/check", json={"text": RISKY, "use_ai": False}, headers=H("creator")).json()["findings"]:
        assert f["evidence"] and f["evidence"][0]["ref"].startswith("R-")


def test_fix_preserves_purpose_and_clears_risk(C):
    chk = C.post("/api/check", json={"text": RISKY, "use_ai": False}, headers=H("creator")).json()
    keys = [f["key"] for f in chk["findings"] if f["fix"] and not f["fix"].get("overlaps")]
    fx = C.post("/api/fix", json={"text": RISKY, "findings": chk["findings"], "accepted": keys}, headers=H("creator")).json()
    assert fx["recheck"]["risk"]["score"] == 0 and fx["purpose"]["ok"]
    assert "₹10,000" in fx["text"] and "2-year warranty" in fx["text"]


def test_confidential_term_is_high_and_has_no_auto_fix(C):
    f = next(f for f in C.post("/api/check", json={"text": "Project Falcon is coming.", "use_ai": False}, headers=H("creator")).json()["findings"] if f["rule_id"] == "R-CONF-01")
    assert f["severity"] == "high" and f["fix"] is None


# ---------------------------------------------------------------- workflow & certificates

def test_workflow_roles_certificate_and_idempotency(C):
    s = C.post("/api/submissions", json={"title": "wf", "text": RISKY}, headers=H("creator")).json()
    assert s["status"] == "compliance_review"
    dup = C.post("/api/submissions", json={"title": "wf", "text": RISKY}, headers=H("creator")).json()
    assert dup["id"] == s["id"]  # a double click does not create a second submission
    sid = s["id"]
    act = lambda role, **b: C.post(f"/api/submissions/{sid}/action", json=b, headers=H(role))  # noqa: E731
    assert act("reviewer", action="approve").status_code == 403
    assert act("compliance", action="clear_claims").status_code == 403
    high = [f for f in s["versions"][-1]["findings"] if f["severity"] == "high"]
    assert act("reviewer", action="dismiss", finding_key=high[0]["key"], reason="x").status_code == 403
    assert act("compliance", action="dismiss", finding_key=high[0]["key"]).status_code == 403  # reason required
    for f in high:
        assert act("compliance", action="dismiss", finding_key=f["key"], reason="test").status_code == 200
    assert act("compliance", action="dismiss", finding_key=high[0]["key"], reason="again").status_code == 409
    assert act("compliance", action="clear_claims").json()["status"] == "in_review"
    assert act("compliance", action="clear_claims").status_code == 409
    s = act("reviewer", action="approve").json()
    assert s["status"] == "approved" and s["certificate"]
    assert act("reviewer", action="approve").status_code == 409  # approving twice is refused
    assert C.get("/api/certificates").json()["chain"]["ok"]
    assert C.post("/api/certificates/verify", json={"text": RISKY}).json()["match"]
    assert not C.post("/api/certificates/verify", json={"text": RISKY.replace("₹7,000", "₹6,000")}).json()["match"]


def test_resubmit_requires_changed_text(C):
    s = C.post("/api/submissions", json={"title": "rs", "text": "OMG INSANE value!!"}, headers=H("creator")).json()
    sid = s["id"]
    C.post(f"/api/submissions/{sid}/action", json={"action": "request_changes", "reason": "tone"}, headers=H("reviewer"))
    assert C.post(f"/api/submissions/{sid}/action", json={"action": "resubmit", "text": "OMG INSANE value!!"}, headers=H("creator")).status_code == 403
    r = C.post(f"/api/submissions/{sid}/action", json={"action": "resubmit", "text": "Great value."}, headers=H("creator")).json()
    assert r["current_version"] == 2 and r["status"] == "in_review"


# ---------------------------------------------------------------- team accounts, invites, four-eyes

def test_team_signup_invite_four_eyes_and_verified_identity():
    a = TestClient(app)
    a.__enter__()
    assert a.post("/api/auth/signup", json={"name": "Ayush", "email": "ayush@t.io", "password": "short", "org_name": "T"}).status_code == 403
    me = a.post("/api/auth/signup", json={"name": "Ayush", "email": "ayush@t.io", "password": "password123", "org_name": "Team T"}).json()
    assert me["roles"] == ["creator", "compliance", "reviewer", "admin"] and not me["demo"]
    assert a.post("/api/auth/signup", json={"name": "X", "email": "ayush@t.io", "password": "password123", "org_name": "T2"}).status_code == 403
    code = a.post("/api/team/invites", json={"roles": ["reviewer"]}, headers=H("admin")).json()["code"]
    assert a.post("/api/team/invites", json={"roles": ["reviewer"]}, headers=H("creator")).status_code == 403
    s = a.post("/api/submissions", json={"title": "t", "text": "SoundPods Pro – Smart Technology for Everyday Life."}, headers=H("creator")).json()
    r = TestClient(app)
    r.__enter__()
    me2 = r.post(f"/api/invites/{code}/accept", json={"name": "Kanika", "email": "kanika@t.io", "password": "password123"}).json()
    assert me2["roles"] == ["reviewer"] and me2["org_name"] == "Team T"
    assert r.post(f"/api/invites/{code}/accept", json={"name": "Z", "email": "z@t.io", "password": "password123"}).status_code == 403
    # four-eyes: the submitter cannot approve their own content once the team has 2+ members
    assert a.post(f"/api/submissions/{s['id']}/action", json={"action": "approve"}, headers=H("reviewer")).status_code == 403
    # the invited reviewer cannot act as admin even if they ask to
    assert r.post("/api/brand/change", json={"kind": "term", "avoid": "x", "prefer": "y"}, headers=H("admin")).status_code == 403
    out = r.post(f"/api/submissions/{s['id']}/action", json={"action": "approve"}, headers=H("reviewer")).json()
    appr = out["certificate"]["payload"]["approvers"][-1]
    assert appr["verified"] and appr["email"] == "kanika@t.io"
    # sign out and sign back in
    a.post("/api/auth/logout")
    assert a.get("/api/auth/me").status_code == 401
    assert a.post("/api/auth/login", json={"email": "ayush@t.io", "password": "wrong-pass"}).status_code == 401
    assert a.post("/api/auth/login", json={"email": "AYUSH@t.io", "password": "password123"}).status_code == 200


# ---------------------------------------------------------------- brand memory: import & impact preview

def test_brand_import_requires_admin_and_creates_version(C):
    data = open(os.path.join(ROOT, "static", "samples", "ABC_Brand_Update_Nov2026.docx"), "rb").read()
    assert C.post("/api/brand/import", files={"file": ("u.docx", data)}, headers=H("creator")).status_code == 403
    r = C.post("/api/brand/import", files={"file": ("u.docx", data)}, headers=H("admin")).json()
    disc = next(c for c in r["candidates"] if c["payload"].get("key") == "max_discount")
    again = C.post("/api/brand/import", files={"file": ("u.docx", data)}, headers=H("admin")).json()
    assert again["created"] == 0  # importing the same file twice does not duplicate candidates
    v = C.post(f"/api/brand/candidates/{disc['id']}/approve", headers=H("admin")).json()["brand_version"]
    assert v >= 2
    assert C.post(f"/api/brand/candidates/{disc['id']}/approve", headers=H("admin")).status_code == 409
    assert "R-PRC-02" not in rules(C, "SoundPods Pro up to 25% off. T&C apply.")


def test_impact_preview_lists_approved_content_that_would_be_flagged():
    c = demo_client()
    r = c.post("/api/brand/impact", json={"kind": "fact", "key": "max_discount", "value": "10"}, headers=H("admin")).json()
    assert r["checked"] >= 5 and len(r["newly_flagged"]) >= 1
    assert all(f["rule_id"] == "R-PRC-02" for s in r["newly_flagged"] for f in s["findings"])
    assert c.post("/api/brand/impact", json={"kind": "fact", "key": "max_discount", "value": "abc"}, headers=H("admin")).status_code == 403
    assert c.post("/api/brand/change", json={"kind": "fact", "key": "max_discount", "value": "10"}, headers=H("creator")).status_code == 403
    assert c.post("/api/brand/change", json={"kind": "fact", "key": "max_discount", "value": "10"}, headers=H("admin")).status_code == 200
    assert "R-PRC-02" in rules(c, "Up to 15% off. T&C apply.")


# ---------------------------------------------------------------- images: palette, logo, text in image

def test_image_palette_and_logo_without_ai(C):
    off = C.post("/api/check", json={"text": "", "image": img("diwali_poster_offbrand.png"), "alt_text": "poster", "use_ai": False}, headers=H("creator")).json()
    ids = [f["rule_id"] for f in off["findings"]]
    assert "R-VIS-01" in ids and "R-LOGO-01" in ids
    on = C.post("/api/check", json={"text": "", "image": img("diwali_poster_onbrand.png"), "alt_text": "poster", "use_ai": False}, headers=H("creator")).json()
    assert on["image"]["creative"]["logo"]["present"] and on["findings"] == []


def test_text_inside_image_is_checked_with_boxes(monkeypatch):
    c = demo_client()
    monkeypatch.setattr(ai, "API_KEY", "test")
    lines = {"lines": [{"text": "50% OFF", "box_2d": [215, 60, 345, 560]}, {"text": "SoundPods Pro – just ₹7,000", "box_2d": [735, 60, 800, 900]},
                       {"text": "DIWALI MEGA SALE", "box_2d": [105, 60, 200, 760]}]}

    def fake(parts, timeout=40):
        t = " ".join(p.get("text", "") for p in parts)
        if "Read ALL visible text" in t:
            return json.dumps({**lines, "alt": "Red Diwali sale poster", "logo": {"present": False, "altered": False, "box_2d": None, "notes": "none"}})
        return json.dumps({"alt": "poster"}) if "alt text" in t else json.dumps({"findings": []})
    monkeypatch.setattr(ai, "_call", fake)
    r = c.post("/api/check", json={"text": "", "image": img("diwali_poster_offbrand.png"), "alt_text": "poster"}, headers=H("creator")).json()
    txt = [f for f in r["findings"] if f.get("target") == "image_text"]
    ids = {f["rule_id"] for f in txt}
    assert {"R-PRC-01", "R-PRC-02"} <= ids
    assert all(f["box"] for f in txt if f["rule_id"] in ("R-PRC-01", "R-PRC-02"))
    assert "R-VOICE-01" not in ids  # ALL-CAPS headlines are allowed on posters
    measured = [ln for ln in r["image"]["creative"]["text"]["lines"] if ln["contrast"] is not None]
    assert measured and any(ln["contrast"] < 3 for ln in measured)  # the pink-on-red headline is low contrast
    # second call is served from the cache (no new model call)
    calls = []
    monkeypatch.setattr(ai, "_call", lambda parts, timeout=40: calls.append(1) or "{}")
    r2 = c.post("/api/check", json={"text": "", "image": img("diwali_poster_offbrand.png"), "alt_text": "poster"}, headers=H("creator")).json()
    assert r2["image"]["creative"]["text"]["cached"] and not calls


# ---------------------------------------------------------------- AI verifier, redaction, bad input

def test_ai_verifier_drops_unevidenced_findings(monkeypatch):
    from app import db
    monkeypatch.setattr(ai, "API_KEY", "test")
    fake = {"findings": [
        {"rule_id": "R-MSG-01", "quote": "Better than Brand X earbuds", "message": "Attacks a competitor.", "replacement": "Made for everyday listening"},
        {"rule_id": "R-MSG-01", "quote": "this text is not in the draft", "message": "hallucinated"},
        {"rule_id": "R-FAKE-99", "quote": "break in a month", "message": "unknown rule"}]}
    monkeypatch.setattr(ai, "_call", lambda parts, timeout=40: json.dumps(fake))
    org = db.one("SELECT id FROM orgs WHERE kind='demo' ORDER BY id LIMIT 1")["id"]
    info = ai.ai_review("Better than Brand X earbuds, which break in a month. v1", db.brand_snapshot(org), [])
    assert info["checked"] == 3 and info["dropped"] == 2 and len(info["findings"]) == 1


def test_slow_ai_never_blocks_rule_results(C, monkeypatch):
    import time
    from app import service
    monkeypatch.setattr(ai, "API_KEY", "test")
    monkeypatch.setattr(service, "AI_WAIT", 0.3)
    monkeypatch.setattr(ai, "ai_review", lambda *a, **k: time.sleep(2) or {"used": True, "findings": []})
    t = time.time()
    r = C.post("/api/check", json={"text": "Best earbuds in India, only Rs 999!", "use_ai": True}, headers=H("creator"))
    assert r.status_code == 200 and time.time() - t < 1.8
    body = r.json()
    assert "slow" in body["ai"]["error"] and "R-PRC-01" in {f["rule_id"] for f in body["findings"]}


def test_redaction_masks_personal_and_confidential():
    out, n = ai.redact("Mail riya@abc.in or call 9876543210 about Project Falcon", ["Project Falcon"])
    assert "riya@abc.in" not in out and "9876543210" not in out and "Project Falcon" not in out and n == 3


def test_bad_inputs_are_rejected_cleanly(C):
    assert C.post("/api/check", json={"text": "   "}, headers=H("creator")).status_code == 400
    assert C.post("/api/check", json={"text": "x" * 20001}, headers=H("creator")).status_code == 422
    assert C.post("/api/check", json={"text": "", "image": "data:image/png;base64,bm90IGFuIGltYWdl"}, headers=H("creator")).status_code == 400
    assert C.post("/api/extract", files={"file": ("a.exe", b"MZ")}, headers=H("creator")).status_code == 400
    assert C.post("/api/extract", files={"file": ("a.pdf", b"not a pdf")}, headers=H("creator")).status_code == 400
    assert C.post("/api/submissions/999999/action", json={"action": "approve"}, headers=H("reviewer")).status_code == 403
    s = C.post("/api/submissions", json={"title": "u", "text": "Fine text."}, headers=H("creator")).json()
    assert C.post(f"/api/submissions/{s['id']}/action", json={"action": "explode"}, headers=H("reviewer")).status_code == 403


# ---------------------------------------------------------------- accuracy

def test_benchmark_rules_quality():
    from app import benchmark_runner
    r = benchmark_runner.run_rules()
    assert r["samples"] >= 200
    assert r["precision"] >= 0.95
    assert r["groups"]["rule_detectable"]["recall"] >= 0.95
