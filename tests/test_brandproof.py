import os

os.environ["DB_PATH"] = "/tmp/brandproof_test.db"
if os.path.exists(os.environ["DB_PATH"]):
    os.remove(os.environ["DB_PATH"])

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

RISKY = "ABC Electronics – India's No. 1 Brand! Buy SoundPods Pro for just ₹7,000. Get 50% OFF. 100% guaranteed performance with lifetime warranty!!"


def client():
    c = TestClient(app)
    c.__enter__()
    return c


C = client()


def rules(text):
    return {f["rule_id"] for f in C.post("/api/check", json={"text": text}).json()["findings"]}


def test_risky_ad_flags_all_core_issues():
    got = rules(RISKY)
    assert {"R-PRC-01", "R-PRC-02", "R-WAR-01", "R-CLM-01", "R-CLM-02", "R-PRC-03", "R-VOICE-01"} <= got


def test_clean_copy_passes():
    assert rules("SoundPods Pro – Smart Technology for Everyday Life. Now ₹10,000 with a 2-year warranty.") == set()


def test_valid_offer_price_is_not_flagged():
    assert "R-PRC-01" not in rules("Get SoundPods Pro for ₹8,500 with up to 15% off. T&C apply.")


def test_outdated_price_cites_expired_fact():
    f = next(f for f in C.post("/api/check", json={"text": "Now only ₹12,000."}).json()["findings"] if f["rule_id"] == "R-PRC-01")
    assert "outdated" in f["message"] and any("expired" in e["ref"] for e in f["evidence"])


def test_every_finding_has_evidence():
    for f in C.post("/api/check", json={"text": RISKY}).json()["findings"]:
        assert f["evidence"] and f["evidence"][0]["ref"].startswith("R-")


def test_fix_preserves_purpose_and_clears_risk():
    chk = C.post("/api/check", json={"text": RISKY}).json()
    keys = [f["key"] for f in chk["findings"] if f["fix"] and not f["fix"].get("overlaps")]
    fx = C.post("/api/fix", json={"text": RISKY, "findings": chk["findings"], "accepted": keys}).json()
    assert fx["recheck"]["risk"]["score"] == 0
    assert fx["purpose"]["ok"]
    assert "₹10,000" in fx["text"] and "2-year warranty" in fx["text"]


def test_confidential_term_is_high_and_has_no_auto_fix():
    f = next(f for f in C.post("/api/check", json={"text": "Project Falcon is coming."}).json()["findings"] if f["rule_id"] == "R-CONF-01")
    assert f["severity"] == "high" and f["fix"] is None


def test_workflow_roles_and_certificate_chain():
    s = C.post("/api/submissions", json={"title": "t", "text": RISKY, "role": "creator"}).json()
    assert s["status"] == "compliance_review"
    sid = s["id"]
    assert C.post(f"/api/submissions/{sid}/action", json={"action": "approve", "role": "reviewer"}).status_code == 403
    assert C.post(f"/api/submissions/{sid}/action", json={"action": "clear_claims", "role": "compliance"}).status_code == 403
    high = [f for f in s["versions"][-1]["findings"] if f["severity"] == "high"]
    r = C.post(f"/api/submissions/{sid}/action", json={"action": "dismiss", "role": "reviewer", "finding_key": high[0]["key"], "reason": "x"})
    assert r.status_code == 403  # only compliance may dismiss high
    for f in high:
        assert C.post(f"/api/submissions/{sid}/action", json={"action": "dismiss", "role": "compliance", "finding_key": f["key"], "reason": "test"}).status_code == 200
    assert C.post(f"/api/submissions/{sid}/action", json={"action": "clear_claims", "role": "compliance"}).json()["status"] == "in_review"
    s = C.post(f"/api/submissions/{sid}/action", json={"action": "approve", "role": "reviewer", "name": "Kabir"}).json()
    assert s["status"] == "approved" and s["certificate"]
    chain = C.get("/api/certificates").json()["chain"]
    assert chain["ok"]
    assert C.post("/api/certificates/verify", json={"text": RISKY}).json()["match"]
    assert not C.post("/api/certificates/verify", json={"text": RISKY.replace("₹7,000", "₹6,000")}).json()["match"]


def test_brand_import_requires_admin_and_creates_version():
    data = open(os.path.join(os.path.dirname(__file__), "..", "static", "samples", "ABC_Brand_Update_Nov2026.docx"), "rb").read()
    assert C.post("/api/brand/import", files={"file": ("u.docx", data)}, data={"role": "creator"}).status_code == 403
    r = C.post("/api/brand/import", files={"file": ("u.docx", data)}, data={"role": "admin"}).json()
    disc = next(c for c in r["candidates"] if c["payload"].get("key") == "max_discount")
    v = C.post(f"/api/brand/candidates/{disc['id']}/approve", json={"role": "admin"}).json()["brand_version"]
    assert v >= 2
    assert "R-PRC-02" not in rules("SoundPods Pro up to 25% off. T&C apply.")


def test_image_palette_measured():
    import base64
    img = open(os.path.join(os.path.dirname(__file__), "..", "static", "samples", "diwali_poster_offbrand.png"), "rb").read()
    r = C.post("/api/check", json={"text": "", "image": "data:image/png;base64," + base64.b64encode(img).decode()}).json()
    vis = [f for f in r["findings"] if f["rule_id"] == "R-VIS-01"]
    assert vis and "ΔE" in vis[0]["message"]


def test_ai_verifier_drops_unevidenced_findings(monkeypatch):
    import json as _j
    from app import ai, db
    monkeypatch.setattr(ai, "API_KEY", "test")
    fake = {"findings": [
        {"rule_id": "R-MSG-01", "quote": "Better than Brand X earbuds", "message": "Attacks a competitor.", "replacement": "Made for everyday listening"},
        {"rule_id": "R-MSG-01", "quote": "this text is not in the draft", "message": "hallucinated"},
        {"rule_id": "R-FAKE-99", "quote": "break in a month", "message": "unknown rule"}]}
    monkeypatch.setattr(ai, "_call", lambda prompt, timeout=30: _j.dumps(fake))
    text = "Better than Brand X earbuds, which break in a month."
    info = ai.ai_review(text, db.brand_snapshot(), [])
    assert info["checked"] == 3 and info["dropped"] == 2 and len(info["findings"]) == 1
    assert info["findings"][0]["quote"] == "Better than Brand X earbuds"


def test_redaction_masks_personal_and_confidential():
    from app import ai
    out, n = ai.redact("Mail riya@abc.in or call 9876543210 about Project Falcon", ["Project Falcon"])
    assert "riya@abc.in" not in out and "9876543210" not in out and "Project Falcon" not in out and n == 3
