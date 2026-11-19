"""Test-only server: runs BrandProof with a fake AI (canned responses) on port 8010 for the e2e browser test."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DB_PATH", "/tmp/brandproof_e2e.db")
from app import ai
ai.API_KEY = "fake"
def fake_call(parts, timeout=40):
    text = " ".join(p.get("text", "") for p in parts if isinstance(p, dict))
    if "Read ALL visible text" in text:
        return json.dumps({"lines": [
            {"text": "DIWALI MEGA SALE", "box_2d": [105, 60, 200, 760]},
            {"text": "50% OFF", "box_2d": [215, 60, 345, 560]},
            {"text": "SoundPods Pro – just ₹7,000", "box_2d": [735, 60, 800, 900]},
            {"text": "India's No. 1 earbuds · Lifetime warranty", "box_2d": [818, 60, 870, 960]}],
            "alt": "Red Diwali sale poster with earbuds and price text.",
            "logo": {"present": False, "altered": False, "box_2d": None, "notes": "No ABC logo visible."}})
    if "approved logo" in text:
        return json.dumps({"present": False, "altered": False, "box_2d": None, "notes": "No ABC logo visible."})
    if "alt text" in text:
        return json.dumps({"alt": "Red Diwali sale poster with earbuds and price text."})
    if "Extract brand facts" in text:
        return json.dumps({"facts": [], "terms": [], "confidential": []})
    if "clearer version of this rule" in text:
        return json.dumps({"rule": "Urgency words are allowed only for dated offers; no pressure phrases."})
    out = []
    if "Brand X" in text:
        out.append({"rule_id": "R-MSG-01", "quote": "Better than Brand X earbuds", "message": "Attacks a competitor.", "replacement": "Made for everyday listening"})
    out.append({"rule_id": "R-VOICE-01", "quote": "this phrase does not exist", "message": "hallucinated"})
    return json.dumps({"findings": out})
ai._call = fake_call
import uvicorn
from app.main import app
uvicorn.run(app, host="127.0.0.1", port=8010, log_level="warning")
