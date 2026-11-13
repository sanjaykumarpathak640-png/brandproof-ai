"""Optional AI layer (Google Gemini) with redaction and an evidence verifier.

The AI is only used for meaning-based checks (tone, paraphrased or implied claims)
and for drafting suggestions. Every AI finding must quote text that really exists
in the draft and cite a real rule ID from Brand Memory; anything else is dropped
and counted, so reviewers can see how much the verifier filtered out.
"""
from __future__ import annotations

import json
import os
import re

import httpx

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

AI_CATEGORIES = {"voice", "messaging", "claims"}


def available() -> bool:
    return bool(API_KEY)


def model_name() -> str:
    return MODEL if available() else "none (rules only)"


def redact(text: str, confidential_terms: list[str]) -> tuple[str, int]:
    """Mask personal data and confidential terms before anything leaves the server."""
    n = 0
    out = text
    for pat, tag in [(r"[\w.+-]+@[\w-]+\.[\w.]+", "[EMAIL]"), (r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)", "[PHONE]")]:
        out, k = re.subn(pat, tag, out)
        n += k
    for t in confidential_terms or []:
        out, k = re.subn(re.escape(t), "[CONFIDENTIAL]", out, flags=re.I)
        n += k
    return out, n


def _call(prompt: str, timeout: float = 30.0) -> str:
    r = httpx.post(
        URL.format(model=MODEL),
        params={"key": API_KEY},
        json={
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
        },
        timeout=timeout,
    )
    r.raise_for_status()
    data = r.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def ai_review(text: str, brand: dict, existing: list[dict]) -> dict:
    info = {"used": False, "model": model_name(), "checked": 0, "dropped": 0, "merged": 0,
            "redactions": 0, "findings": [], "error": None, "dropped_examples": []}
    if not available():
        info["error"] = "No GEMINI_API_KEY configured — deterministic rules only."
        return info
    red, n = redact(text, brand["meta"].get("confidential_terms") or [])
    info["redactions"] = n
    rules = [r for r in brand["rules"] if r.get("enabled", 1) and r["category"] in AI_CATEGORIES]
    facts = [f"{f['id']}: {f['label']} = {f['value']} {f.get('unit') or ''}".strip() for f in brand["facts"] if f["status"] == "approved"]
    prompt = f"""You are a strict brand-governance reviewer for the brand "{brand['meta'].get('brand_name')}".
Brand voice: {brand['meta'].get('tone')}. Voice profile: {brand['meta'].get('voice_profile')}.
Approved facts:\n- """ + "\n- ".join(facts) + """
Rules you may cite (use ONLY these IDs):\n- """ + "\n- ".join(f"{r['id']} [{r['severity']}] {r['title']}: {r['description']}" for r in rules) + f"""

Review the DRAFT below. Report only real problems about tone/voice, messaging or claims that are implied or paraphrased
(exact number checks are already done elsewhere). For each problem return:
- "rule_id": one of the IDs above
- "quote": the EXACT words copied from the draft (5-120 characters, must appear verbatim)
- "message": one short sentence explaining the issue
- "replacement": a short rewrite of the quoted words that keeps the creator's purpose and follows the rules
Return JSON: {{"findings": [ ... ]}}. Return an empty list if the draft is fine. Do not invent facts.

DRAFT:
\"\"\"{red}\"\"\""""
    try:
        raw = _call(prompt)
        data = json.loads(raw)
    except Exception as e:  # network, quota, bad JSON
        info["error"] = f"AI call failed: {type(e).__name__}. Showing rule-based results only."
        return info
    info["used"] = True
    items = data.get("findings", []) if isinstance(data, dict) else []
    valid_ids = {r["id"]: r for r in rules}
    low = text.lower()
    for it in items:
        info["checked"] += 1
        quote = (it.get("quote") or "").strip()
        rid = (it.get("rule_id") or "").strip()
        reason = None
        if rid not in valid_ids:
            reason = f"cited unknown rule “{rid}”"
        elif len(quote) < 3 or quote.lower() not in low:
            reason = "quote not found in the draft"
        if reason:
            info["dropped"] += 1
            if len(info["dropped_examples"]) < 3:
                info["dropped_examples"].append({"quote": quote[:80], "reason": reason})
            continue
        s = low.index(quote.lower())
        e = s + len(quote)
        if any(f["start"] < e and s < f["end"] for f in existing + info["findings"]):
            info["merged"] += 1
            continue
        r = valid_ids[rid]
        rep = it.get("replacement")
        info["findings"].append({
            "rule_id": rid, "category": r["category"], "severity": r["severity"] if r["severity"] != "high" else "medium",
            "title": r["title"], "quote": text[s:e], "start": s, "end": e,
            "message": (it.get("message") or "").strip()[:300],
            "evidence": [{"ref": r["id"], "text": r["title"] + ": " + (r.get("description") or ""), "source": r.get("source", "")}],
            "fix": {"replacement": rep, "note": "AI-suggested rewrite (AI-assisted)"} if isinstance(rep, str) else None,
            "engine": "ai",
        })
    return info


def suggest_rule(rule: dict, reasons: list[str]) -> str | None:
    if not available():
        return None
    prompt = (f"A brand rule is often dismissed by reviewers. Rule {rule['id']}: {rule['title']} — {rule['description']}.\n"
              f"Reviewer reasons: {json.dumps(reasons[:8])}.\nWrite a clearer version of this rule (max 45 words) with an explicit "
              "exception or example that resolves the confusion. Return JSON {\"rule\": \"...\"}.")
    try:
        return json.loads(_call(prompt, timeout=20)).get("rule")
    except Exception:
        return None


def describe_image(image_bytes: bytes, mime: str) -> str | None:
    """Draft alt text for an image (vision model). Returns None when AI is unavailable."""
    if not available():
        return None
    import base64
    try:
        r = httpx.post(
            URL.format(model=MODEL), params={"key": API_KEY},
            json={"contents": [{"role": "user", "parts": [
                {"inline_data": {"mime_type": mime, "data": base64.b64encode(image_bytes).decode()}},
                {"text": "Write one concise alt text (max 20 words) describing this marketing image for screen-reader users. Return JSON {\"alt\": \"...\"}."}]}],
                "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}},
            timeout=30)
        r.raise_for_status()
        return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"]).get("alt")
    except Exception:
        return None
