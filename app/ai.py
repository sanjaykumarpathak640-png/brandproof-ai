"""Optional AI layer (Google Gemini): text review, image text reading, logo check and
brand-book extraction — always behind redaction, an evidence verifier and a cache.

Rules the AI must follow:
- A text finding is kept only if it quotes words that really exist in the draft and cites a
  real rule ID from Brand Memory; anything else is dropped and counted.
- Brand-book facts extracted by AI become *pending* candidates and are kept only if the
  value really appears in the document.
- Every call is cached by content hash, so repeating a check never costs a second call,
  and a short-term rate limiter protects the free quota. On any failure the app falls back
  to the deterministic rules and says so.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import threading
import time

import logging

import httpx

from . import db

log = logging.getLogger("brandproof.ai")

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash").strip()
_model_checked = False
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
AI_CATEGORIES = {"voice", "messaging", "claims", "pricing", "warranty", "specs"}
MAX_CALLS_PER_MIN = int(os.environ.get("AI_MAX_CALLS_PER_MIN", "12"))

_calls: list[float] = []
_rl_lock = threading.Lock()


def available() -> bool:
    return bool(API_KEY)


def model_name() -> str:
    return MODEL if available() else "none (rules only)"


def _allow_call() -> bool:
    with _rl_lock:
        t = time.time()
        while _calls and t - _calls[0] > 60:
            _calls.pop(0)
        if len(_calls) >= MAX_CALLS_PER_MIN:
            return False
        _calls.append(t)
        return True


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


_THINKING = {"ok": True}


def _post(model: str, parts: list, timeout: float):
    cfg = {"temperature": 0.1, "responseMimeType": "application/json"}
    if _THINKING["ok"]:
        cfg["thinkingConfig"] = {"thinkingLevel": "low"}  # faster answers; dropped automatically if unsupported
    r = httpx.post(URL.format(model=model), params={"key": API_KEY},
                   json={"contents": [{"role": "user", "parts": parts}], "generationConfig": cfg}, timeout=timeout)
    if r.status_code == 400 and _THINKING["ok"] and "think" in r.text.lower():
        _THINKING["ok"] = False
        cfg.pop("thinkingConfig", None)
        r = httpx.post(URL.format(model=model), params={"key": API_KEY},
                       json={"contents": [{"role": "user", "parts": parts}], "generationConfig": cfg}, timeout=timeout)
    return r


def _err_msg(r) -> str:
    try:
        msg = r.json().get("error", {}).get("message", "")
    except Exception:  # noqa: BLE001
        msg = r.text[:300]
    return re.sub(r"key=[^&\s]+", "key=***", msg)


def _version(name: str) -> tuple:
    nums = re.findall(r"\d+(?:\.\d+)?", name)
    return tuple(float(n) for n in nums[:2]) or (0.0,)


_models_cache: dict = {}


def _list_models() -> list[str]:
    if "names" in _models_cache:
        return _models_cache["names"]
    try:
        r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models", params={"key": API_KEY, "pageSize": 200}, timeout=15)
        r.raise_for_status()
        names = [m["name"].split("/", 1)[-1] for m in r.json().get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
    except Exception:  # noqa: BLE001
        names = []
    _models_cache["names"] = names
    return names


def fallback_model() -> str | None:
    """A fast backup model (prefer the newest Flash-Lite) for when the main model is overloaded."""
    if "fallback" in _models_cache:
        return _models_cache["fallback"]
    names = [n for n in _list_models() if n != MODEL and "flash" in n and not any(b in n for b in ("image", "tts", "audio", "live", "embed", "exp", "preview"))]
    lite = [n for n in names if "lite" in n]
    pick = max(lite or names, key=_version) if (lite or names) else None
    _models_cache["fallback"] = pick
    return pick


def discover_model() -> str | None:
    """Pick the newest general-purpose Flash model this key can use (used when the configured model is retired)."""
    try:
        r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models", params={"key": API_KEY, "pageSize": 200}, timeout=20)
        r.raise_for_status()
        names = [m["name"].split("/", 1)[-1] for m in r.json().get("models", [])
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
    except Exception:  # noqa: BLE001
        return None
    bad = ("lite", "image", "tts", "audio", "live", "embed", "thinking", "exp", "preview", "8b", "learnlm")
    flash = [n for n in names if "flash" in n and not any(b in n for b in bad)]
    return max(flash, key=_version) if flash else None


def _call(parts: list, timeout: float = 40.0) -> str:
    global MODEL, _model_checked
    r = _post(MODEL, parts, timeout)
    if r.status_code == 404 and not _model_checked:
        _model_checked = True
        msg = _err_msg(r)
        suggested = [x.rstrip(".") for x in re.findall(r"models/(gemini-[\w.\-]*flash[\w.\-]*)", msg) if x.rstrip(".") != MODEL]
        new = suggested[0] if suggested else discover_model()
        if new and new != MODEL:
            log.warning("Gemini model %s unavailable; switching to %s", MODEL, new)
            MODEL = new
            r = _post(MODEL, parts, timeout)
    if r.status_code in (500, 503):
        fb = fallback_model()
        if fb:
            log.warning("Gemini %s overloaded (HTTP %s); retrying once with %s", MODEL, r.status_code, fb)
            r = _post(fb, parts, min(timeout, 30))
    if r.status_code == 429:
        raise RuntimeError("AI quota reached")
    if r.status_code >= 400:
        msg = _err_msg(r)[:160]
        log.warning("Gemini HTTP %s: %s", r.status_code, msg)
        raise RuntimeError(f"AI service error (HTTP {r.status_code}: {msg})")
    data = r.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _cached_json(kind: str, key_material: str, parts_fn, timeout=40.0) -> dict:
    """Call the model once per unique input; cache the parsed JSON."""
    key = f"{kind}:{MODEL}:" + hashlib.sha256(key_material.encode()).hexdigest()
    hit = db.cache_get(key)
    if hit is not None:
        hit["_cached"] = True
        return hit
    if not _allow_call():
        return {"_error": "AI is busy (rate limit). Showing rule-based results only — try again in a minute."}
    try:
        try:
            raw = _call(parts_fn(), timeout=timeout)
        except httpx.TimeoutException:
            fb = fallback_model()
            if not fb:
                raise
            log.warning("Gemini %s timed out; retrying once with %s", MODEL, fb)
            r = _post(fb, parts_fn(), 25)
            if r.status_code >= 400:
                raise RuntimeError(f"AI service error (HTTP {r.status_code})")
            raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(raw)
    except RuntimeError as e:
        return {"_error": f"{e}. Showing rule-based results only."}
    except httpx.TimeoutException:
        return {"_error": "AI took too long to answer. Showing rule-based results only."}
    except Exception as e:  # noqa: BLE001  network, timeout, bad JSON
        return {"_error": f"AI call failed ({type(e).__name__}). Showing rule-based results only."}
    if isinstance(data, list):
        data = {"items": data}
    db.cache_set(key, data)
    return data


def _img_part(data: bytes, mime: str) -> dict:
    return {"inline_data": {"mime_type": mime or "image/png", "data": base64.b64encode(data).decode()}}


# ---------------------------------------------------------------- text review

def ai_review(text: str, brand: dict, existing: list[dict]) -> dict:
    info = {"used": False, "model": model_name(), "checked": 0, "dropped": 0, "merged": 0,
            "redactions": 0, "findings": [], "error": None, "dropped_examples": [], "cached": False}
    if not available():
        info["error"] = "No GEMINI_API_KEY configured — deterministic rules only."
        return info
    red, n = redact(text, brand["meta"].get("confidential_terms") or [])
    info["redactions"] = n
    rules = [r for r in brand["rules"] if r.get("enabled", 1) and r["category"] in AI_CATEGORIES]
    facts = [f"{f['id']}: {f['label']} = {f['value']} {f.get('unit') or ''}".strip()
             for f in brand["facts"] if f["status"] == "approved" and not (f.get("valid_to") and f["valid_to"] < brand["today"])]
    prompt = (f'You are a strict brand-governance reviewer for the brand "{brand["meta"].get("brand_name")}".\n'
              f'Brand voice: {brand["meta"].get("tone")}. Voice profile: {brand["meta"].get("voice_profile")}.\n'
              "Approved facts (current):\n- " + "\n- ".join(facts or ["(none)"]) + "\n"
              "Rules you may cite (use ONLY these IDs):\n- " + "\n- ".join(f"{r['id']} [{r['severity']}] {r['title']}: {r['description']}" for r in rules) +
              "\n\nThe DRAFT may be in English, Hindi (Devanagari) or Hinglish (Hindi in Roman script). Report only real problems: tone/voice, "
              "messaging (e.g. attacking competitors, fear-based claims), and claims that are implied, paraphrased or written in words that "
              "contradict the approved facts or have no evidence. For each problem return:\n"
              '- "rule_id": one of the IDs above\n- "quote": the EXACT words copied from the draft (3-120 characters, must appear verbatim)\n'
              '- "message": one short English sentence explaining the issue\n'
              '- "replacement": a short rewrite of the quoted words in the same language as the draft that keeps the creator\'s purpose and follows the rules\n'
              'Return JSON: {"findings": [ ... ]}. Return an empty list if the draft is fine. Do not invent facts.\n\nDRAFT:\n"""' + red + '"""')
    data = _cached_json("review", prompt, lambda: [{"text": prompt}])
    if "_error" in data:
        info["error"] = data["_error"]
        return info
    info["used"] = True
    info["cached"] = bool(data.get("_cached"))
    items = data.get("findings", data.get("items", [])) or []
    valid_ids = {r["id"]: r for r in rules}
    low = text.lower()
    for it in items:
        if not isinstance(it, dict):
            continue
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
        if any(f["start"] < e and s < f["end"] for f in existing + info["findings"] if f.get("target") not in ("image", "image_text")):
            info["merged"] += 1
            continue
        r = valid_ids[rid]
        rep = it.get("replacement")
        info["findings"].append({
            "rule_id": rid, "category": r["category"], "severity": r["severity"] if r["severity"] != "high" else "medium",
            "title": r["title"], "quote": text[s:e], "start": s, "end": e,
            "message": (it.get("message") or "").strip()[:300],
            "evidence": [{"ref": r["id"], "text": r["title"] + ": " + (r.get("description") or ""), "source": r.get("source", "")},
                         {"ref": "AI quote check", "text": "Quoted words verified to exist in the draft.", "source": MODEL}],
            "fix": {"replacement": rep, "note": "AI-suggested rewrite (AI-assisted)"} if isinstance(rep, str) and rep.strip() else None,
            "engine": "ai",
        })
    return info


# ---------------------------------------------------------------- images

def read_image_text(image: bytes, mime: str) -> dict:
    prompt = ("Read ALL visible text in this marketing image, line by line, exactly as written (keep ₹, %, numbers, Hindi). "
              'Return JSON {"lines":[{"text":"...","box_2d":[ymin,xmin,ymax,xmax]}]} where box_2d is normalised to 0-1000. '
              'If there is no text return {"lines":[]}.')
    h = hashlib.sha256(image).hexdigest()
    data = _cached_json("ocr", h + prompt, lambda: [_img_part(image, mime), {"text": prompt}], timeout=60)
    if "_error" in data:
        return {"error": data["_error"]}
    lines = []
    for ln in data.get("lines", data.get("items", [])) or []:
        if not isinstance(ln, dict) or not str(ln.get("text", "")).strip():
            continue
        box = ln.get("box_2d") or ln.get("box")
        if isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box):
            box = [max(0, min(1000, float(v))) for v in box]
        else:
            box = None
        lines.append({"text": str(ln["text"]).strip()[:300], "box": box})
    return {"lines": lines[:60], "model": MODEL, "cached": bool(data.get("_cached"))}


def find_logo(image: bytes, mime: str, logo: bytes, logo_mime: str) -> dict:
    prompt = ("The FIRST image is a brand's approved logo. The SECOND image is a marketing creative. Is the approved logo present in "
              "the creative (it may be resized)? Is it altered (recoloured, stretched, cropped, different design)? "
              'Return JSON {"present": true/false, "altered": true/false, "box_2d": [ymin,xmin,ymax,xmax] (0-1000, or null), "notes": "one short sentence"}.')
    key = hashlib.sha256(image).hexdigest() + hashlib.sha256(logo).hexdigest() + prompt
    data = _cached_json("logo", key, lambda: [_img_part(logo, logo_mime), _img_part(image, mime), {"text": prompt}], timeout=60)
    if "_error" in data:
        return {"error": data["_error"]}
    box = data.get("box_2d")
    if not (isinstance(box, list) and len(box) == 4):
        box = None
    return {"present": bool(data.get("present")), "altered": bool(data.get("altered")), "box": box,
            "notes": str(data.get("notes", ""))[:200], "model": MODEL}


def read_creative(image: bytes, mime: str, logo: bytes | None, logo_mime: str | None) -> dict:
    """One call for a poster: every text line with its box, an alt text, and (if a logo is given) whether it is present."""
    logo_q = ('The FIRST image is the brand\'s approved logo; the SECOND image is the creative. Also report whether the approved logo appears '
              'in the creative (it may be resized), and whether it looks altered (recoloured, stretched, cropped, redrawn). ') if logo else ""
    prompt = (logo_q + "Read ALL visible text in the creative, line by line, exactly as written (keep ₹, %, numbers and Hindi). "
              "Write one concise alt text (max 20 words) for screen-reader users. Return JSON "
              '{"lines":[{"text":"...","box_2d":[ymin,xmin,ymax,xmax]}],"alt":"...",'
              + ('"logo":{"present":true/false,"altered":true/false,"box_2d":[ymin,xmin,ymax,xmax] or null,"notes":"one short sentence"}' if logo else '"logo":null')
              + "} with every box normalised to 0-1000. Use an empty list if there is no text.")
    key = hashlib.sha256(image).hexdigest() + (hashlib.sha256(logo).hexdigest() if logo else "") + prompt
    parts = (lambda: ([_img_part(logo, logo_mime)] if logo else []) + [_img_part(image, mime), {"text": prompt}])
    data = _cached_json("creative", key, parts, timeout=45)
    if "_error" in data:
        return {"error": data["_error"]}
    lines = []
    for ln in data.get("lines", []) or []:
        if not isinstance(ln, dict) or not str(ln.get("text", "")).strip():
            continue
        box = ln.get("box_2d") or ln.get("box")
        box = [max(0, min(1000, float(v))) for v in box] if isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box) else None
        lines.append({"text": str(ln["text"]).strip()[:300], "box": box})
    lg = data.get("logo") if isinstance(data.get("logo"), dict) else None
    if lg:
        b = lg.get("box_2d")
        lg = {"present": bool(lg.get("present")), "altered": bool(lg.get("altered")),
              "box": b if isinstance(b, list) and len(b) == 4 else None, "notes": str(lg.get("notes", ""))[:200]}
    return {"lines": lines[:60], "alt": (str(data.get("alt") or "")[:200] or None), "logo": lg, "model": MODEL, "cached": bool(data.get("_cached"))}


def describe_image(image_bytes: bytes, mime: str) -> str | None:
    if not available():
        return None
    prompt = 'Write one concise alt text (max 20 words) describing this marketing image for screen-reader users. Return JSON {"alt": "..."}.'
    data = _cached_json("alt", hashlib.sha256(image_bytes).hexdigest() + prompt, lambda: [_img_part(image_bytes, mime), {"text": prompt}])
    return None if "_error" in data else (data.get("alt") or None)


# ---------------------------------------------------------------- brand memory helpers

def suggest_rule(rule: dict, reasons: list[str]) -> str | None:
    if not available():
        return None
    prompt = (f"A brand rule is often dismissed by reviewers. Rule {rule['id']}: {rule['title']} — {rule['description']}.\n"
              f"Reviewer reasons: {json.dumps(reasons[:8])}.\nWrite a clearer version of this rule (max 45 words) with an explicit "
              'exception or example that resolves the confusion. Return JSON {"rule": "..."}.')
    data = _cached_json("rule", prompt, lambda: [{"text": prompt}], timeout=25)
    return None if "_error" in data else data.get("rule")


FACT_KEYS = {"price": "Product price (MRP) in INR, number only", "max_discount": "Maximum discount percent, number only",
             "warranty_years": "Warranty in years, number only", "battery_hours": "Battery life in hours, number only",
             "ip_rating": "Water resistance rating like IPX4", "tagline": "Approved tagline", "product_name": "Official product name"}


def extract_brand_facts(text: str) -> dict:
    """Free-form brand books: ask the model for facts/terms; every value must appear in the document."""
    if not available():
        return {"error": "No AI key configured."}
    doc = text[:15000]
    prompt = ("Extract brand facts from this brand book. Keys: " + json.dumps(FACT_KEYS) +
              '. Also extract terminology rules (words to avoid and what to use instead) and confidential/internal names. '
              'Return JSON {"facts":[{"key":"...","value":"...","quote":"exact sentence from the document"}],'
              '"terms":[{"avoid":"...","prefer":"...","quote":"..."}],"confidential":[{"term":"...","quote":"..."}]}. '
              "Only include items clearly stated in the document.\n\nDOCUMENT:\n" + doc)
    data = _cached_json("bookx", prompt, lambda: [{"text": prompt}], timeout=60)
    if "_error" in data:
        return {"error": data["_error"]}
    low = text.lower()

    def ok(item, field):
        v = str(item.get(field, "")).strip()
        q = str(item.get("quote", "")).strip()
        return v and v.lower().replace(",", "") in low.replace(",", "") and (not q or q[:40].lower() in low)
    facts = [f for f in data.get("facts", []) if isinstance(f, dict) and f.get("key") in FACT_KEYS and ok(f, "value")]
    terms = [t for t in data.get("terms", []) if isinstance(t, dict) and ok(t, "avoid") and str(t.get("prefer", "")).strip()]
    conf = [c for c in data.get("confidential", []) if isinstance(c, dict) and ok(c, "term")]
    return {"facts": facts, "terms": terms, "confidential": conf}
