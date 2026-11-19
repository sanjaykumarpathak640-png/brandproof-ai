"""Demo Brand Memory (ABC Electronics, fictional) and sample review history."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import base64
import os

from . import db

BRAND_BOOK = "ABC Electronics Brand Book v3.0"

FACTS = [
    ("F-101", "product_name", "Official product name", "ABC SoundPods Pro", "", "2026-01-01", None, BRAND_BOOK + " · p.2"),
    ("F-102", "price", "Product price (MRP)", "10000", "INR", "2026-10-01", None, "Price List · Oct 2026"),
    ("F-103", "price", "Product price (MRP)", "12000", "INR", "2026-01-01", "2026-09-30", "Price List · Jan 2026"),
    ("F-104", "max_discount", "Maximum discount", "20", "%", "2026-10-01", None, "Festive Offer Policy · Oct 2026"),
    ("F-105", "warranty_years", "Warranty", "2", "years", "2026-01-01", None, BRAND_BOOK + " · p.6"),
    ("F-106", "battery_hours", "Battery life (tested)", "30", "hours", "2026-01-01", None, "Lab Test Report LT-22"),
    ("F-107", "ip_rating", "Water resistance rating", "IPX4", "", "2026-01-01", None, "Certification IPX4-0917"),
    ("F-108", "tagline", "Approved tagline", "Smart Technology for Everyday Life", "", "2026-01-01", None, BRAND_BOOK + " · p.3"),
]

RULES = [
    ("R-PRC-01", "pricing", "high", "Price must match the current price list", "Any price shown must equal the current approved MRP, or a valid offer price within the maximum discount.", BRAND_BOOK + " · p.7"),
    ("R-PRC-02", "pricing", "high", "Discount must not exceed the approved maximum", "Promotions may not advertise a discount above the maximum in the active offer policy.", "Festive Offer Policy · §2"),
    ("R-PRC-03", "pricing", "medium", "Offers need a “T&C apply” disclaimer", "Every promotion must carry the approved disclaimer “T&C apply.”", "Festive Offer Policy · §4"),
    ("R-WAR-01", "warranty", "high", "Warranty claims must match the approved warranty", "Only the approved warranty period may be promised.", BRAND_BOOK + " · p.6"),
    ("R-SPEC-01", "specs", "high", "Product specs must match tested values", "Battery life, water resistance and other specs must match certified test results.", "Lab Test Report LT-22"),
    ("R-CLM-01", "claims", "medium", "No rankings or superlatives without evidence", "Claims like “No. 1”, “best” or “unbeatable” need a cited study, award or ranking in Brand Memory.", BRAND_BOOK + " · p.9"),
    ("R-CLM-02", "claims", "high", "No absolute guarantees", "Do not promise “100% guaranteed”, “never fails” or similar absolute outcomes.", "Legal Guidelines · §3"),
    ("R-TERM-01", "terminology", "medium", "Use approved terminology", "Words on the avoid list must be replaced with the preferred term.", "Terminology list"),
    ("R-TERM-02", "terminology", "medium", "Use the official product name", "Always write the product name exactly as “SoundPods Pro”.", BRAND_BOOK + " · p.2"),
    ("R-VOICE-01", "voice", "medium", "Tone: professional and friendly", "Avoid hype words, shouting (ALL CAPS) and repeated exclamation marks.", BRAND_BOOK + " · p.4"),
    ("R-VOICE-02", "voice", "review", "Avoid pressure and urgency tactics", "Do not pressure customers with urgency language such as “Hurry” or “Last chance”.", BRAND_BOOK + " · p.4"),
    ("R-MSG-01", "messaging", "medium", "Keep to the brand's key messages", "Messaging should focus on everyday reliability, comfort and support. Do not attack competitors or make fear-based claims.", BRAND_BOOK + " · p.5"),
    ("R-CONF-01", "confidential", "high", "No confidential or unreleased information", "Internal code names, unreleased products and internal figures must never appear in public content.", "Information Security Policy"),
    ("R-A11Y-01", "accessibility", "review", "Keep sentences readable", "Sentences longer than 28 words are hard to read.", "Accessibility Guidelines · §1"),
    ("R-A11Y-02", "accessibility", "review", "Images need alt text", "Every published image needs descriptive alt text.", "Accessibility Guidelines · §2 (WCAG 1.1.1)"),
    ("R-A11Y-03", "accessibility", "review", "Text and background need enough contrast", "Main colours should reach at least 3:1 contrast (WCAG AA, large text).", "Accessibility Guidelines · §3 (WCAG 1.4.3)"),
    ("R-VIS-01", "visual", "medium", "Use the brand colour palette", "Main colours must be within ΔE 20 of a brand palette colour.", BRAND_BOOK + " · Visual identity p.11"),
]

TERMS = [
    ("cheap", "affordable", "“Cheap” suggests low quality."),
    ("killer deal", "great value", ""),
    ("ABC Earbuds", "ABC SoundPods Pro", "Use the official product name."),
    ("risk-free", "backed by easy 7-day returns", "Only the approved returns promise may be used."),
    ("miracle", "advanced", ""),
    ("bumper sale", "festive offer", ""),
]

PALETTE = [("Brand Blue", "#1F5FAE"), ("Navy", "#0D2A4A"), ("Sky", "#4FA3E3"), ("White", "#FFFFFF"), ("Cloud Grey", "#E9EEF4")]

SAMPLES = [
    # (title, channel, creator, goal, ai_generated, original, fixed or None, dismissals, flow)
    ("Diwali Instagram post", "Instagram", "Riya Sharma", "Promote the Diwali offer and drive purchases", True,
     "ABC Electronics – India's No. 1 Brand! Buy SoundPods Pro for just ₹7,000. Get 50% OFF. 100% guaranteed performance with lifetime warranty!!",
     None, [], "approve_after_fix"),
    ("Festive email banner", "Email", "Pixel Mint Agency", "Announce festive offer", False,
     "Hurry! Festive offer on SoundPods Pro – up to 20% off. Last chance this Diwali. T&C apply.", None,
     [("R-VOICE-02", "Festive offers are time-limited, so urgency is accurate here.")], "approve_dismiss_urgency"),
    ("Weekend sale story", "Instagram", "Aman Gupta", "Weekend sale", True,
     "OMG this weekend is INSANE! SoundPods Pro at ₹12,000 with a killer deal. Don't miss out!!", None, [], "changes"),
    ("Product page copy", "Website", "Sana Khan", "Explain product features", False,
     "SoundPods Pro gives you 40 hours of battery and is fully waterproof. Built for everyday life with a 2-year warranty.", None, [], "approve_after_fix"),
    ("Last-chance SMS", "SMS", "Pixel Mint Agency", "Clear stock before season end", False,
     "Last chance! SoundPods Pro up to 15% off till Sunday. T&C apply.", None,
     [("R-VOICE-02", "Season-end sale really ends Sunday; this is factual.")], "approve_dismiss_urgency"),
    ("Launch teaser", "Twitter/X", "Aman Gupta", "Build hype for new launch", True,
     "Something big is coming: Project Falcon! Our new SoundPods Max will be the best earbuds in India.", None, [], "reject"),
    ("Retail standee text", "Print", "Riya Sharma", "In-store awareness", False,
     "SoundPods Pro – Smart Technology for Everyday Life. Now ₹10,000 with a 2-year warranty.", None, [], "approve"),
    ("Flash sale push", "App notification", "Pixel Mint Agency", "Drive app sales", False,
     "Only today: grab SoundPods Pro with up to 20% off. T&C apply.", None,
     [("R-VOICE-02", "One-day app offer; urgency is part of the offer.")], "approve_dismiss_urgency"),
    ("Cheap earbuds ad", "Facebook", "Aman Gupta", "Attract budget buyers", True,
     "Looking for cheap earbuds? ABC Earbuds are risk-free and the best choice. Buy now!", None, [], "changes"),
    ("Back-to-college post", "Instagram", "Sana Khan", "Reach students", False,
     "Back to college with SoundPods Pro: 30 hours of playback, IPX4 splash resistance and up to 10% off for students. T&C apply.", None, [], "approve"),
    ("Year-end promo", "Email", "Riya Sharma", "Year-end sale", False,
     "Hurry up, year-end sale! SoundPods Pro up to 20% off. T&C apply.", None,
     [("R-VOICE-02", "Fine for a dated sale — but the rule says never; please clarify.")], "pending_review"),
]


GENERIC_RULE_IDS = {"R-CLM-01", "R-CLM-02", "R-TERM-01", "R-VOICE-01", "R-VOICE-02", "R-MSG-01", "R-CONF-01",
                    "R-A11Y-01", "R-A11Y-02", "R-A11Y-03", "R-VIS-01", "R-PRC-01", "R-PRC-02", "R-PRC-03", "R-WAR-01", "R-SPEC-01",
                    "R-TERM-02", "R-LOGO-01", "R-IMG-01"}

EXTRA_RULES = [
    ("R-LOGO-01", "visual", "medium", "Approved logo must be present", "Brand creatives must show the approved logo, unaltered.", BRAND_BOOK + " · Logo usage p.12"),
    ("R-IMG-01", "visual", "review", "Text in images must be readable", "Text placed on images needs at least 3:1 contrast against its background (WCAG AA, large text).", "Accessibility Guidelines · §3 (WCAG 1.4.3)"),
]

LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "abc_logo.png")


def _ts(days_ago: int, hour: int = 11) -> str:
    d = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return d.replace(hour=hour, minute=(days_ago * 7) % 60, second=0, microsecond=0).isoformat()


def seed_org(org: int, with_history: bool = False, starter: bool = True):
    """Fill a new workspace's Brand Memory. starter=True loads the ABC Electronics demo brand."""
    org_name = (db.one("SELECT name FROM orgs WHERE id=?", (org,)) or {}).get("name", "My brand")
    if starter:
        db.set_meta(org, "brand_name", "ABC Electronics")
        db.set_meta(org, "tone", "professional and friendly")
        db.set_meta(org, "voice_profile", "Warm, clear and confident. Explain benefits simply. No hype, no shouting, no pressure.")
        db.set_meta(org, "confidential_terms", ["Project Falcon", "SoundPods Max", "Q4 margin target"])
        db.set_meta(org, "brand_book", BRAND_BOOK)
        db.ex("INSERT INTO brand_versions(org_id,version,note,created_at) VALUES(?,?,?,?)", (org, 1, f"Initial import of {BRAND_BOOK}", _ts(30)))
        for f in FACTS:
            db.ex("INSERT INTO facts(org_id,id,key,label,value,unit,valid_from,valid_to,source,status,added_in) VALUES(?,?,?,?,?,?,?,?,?,?,1)",
                  (org, *f, "approved"))
        for t in TERMS:
            db.ex("INSERT INTO terms(org_id,avoid,prefer,note,status) VALUES(?,?,?,?,'approved')", (org, *t))
        for p in PALETTE:
            db.ex("INSERT INTO palette(org_id,name,hex) VALUES(?,?,?)", (org, *p))
        if os.path.exists(LOGO_PATH):
            data = "data:image/png;base64," + base64.b64encode(open(LOGO_PATH, "rb").read()).decode()
            db.ex("INSERT INTO assets(org_id,kind,name,data,created_at) VALUES(?,?,?,?,?)", (org, "logo", "ABC Electronics logo", data, db.now()))
    else:
        db.set_meta(org, "brand_name", org_name)
        db.set_meta(org, "tone", "professional and friendly")
        db.set_meta(org, "voice_profile", "Clear, friendly and honest.")
        db.set_meta(org, "confidential_terms", [])
        db.set_meta(org, "brand_book", "Not imported yet")
        db.ex("INSERT INTO brand_versions(org_id,version,note,created_at) VALUES(?,?,?,?)", (org, 1, "Workspace created with the standard rule set", db.now()))
    for r in RULES + EXTRA_RULES:
        db.ex("INSERT INTO rules(org_id,id,category,severity,title,description,source,enabled) VALUES(?,?,?,?,?,?,?,1)", (org, *r))
    if with_history:
        seed_history(org)


def seed_history(org: int):
    from . import engine, service
    from .auth import Ctx, ROLES
    n = len(SAMPLES)

    def ctx(role):
        return Ctx(org_id=org, org_name="demo", demo=True, role=role, roles=list(ROLES))
    for i, (title, ch, creator, goal, ai_gen, text, fixed, dismissals, flow) in enumerate(SAMPLES):
        day = (n - i) + 1
        t0 = _ts(day, 10)
        chk = service.run_check(org, text, confidential=True)
        final = fixed
        if flow == "approve_after_fix":
            keys = [f["key"] for f in chk["findings"] if f.get("fix") and not f["fix"].get("overlaps")]
            final = engine.apply_fixes(text, chk["findings"], keys)
        data = {"title": title, "channel": ch, "creator": creator, "goal": goal, "ai_generated": ai_gen,
                "text": final or text, "original_text": text}
        s = service.create_submission(ctx("creator"), data, demo=True, when=t0, creator_name=creator)
        sid = s["id"]
        cur = s["versions"][-1]
        t1, t2 = _ts(day, 13), _ts(day, 16)
        if flow in ("approve", "approve_after_fix"):
            if s["status"] == "compliance_review":
                service.act(ctx("compliance"), sid, {"action": "clear_claims", "reason": "Claims match Brand Memory."}, when=t1)
            service.act(ctx("reviewer"), sid, {"action": "approve", "reason": "On brand."}, when=t2)
        elif flow == "approve_dismiss_urgency":
            for rid, reason in dismissals:
                for f in cur["findings"]:
                    if f["rule_id"] == rid:
                        service.act(ctx("reviewer"), sid, {"action": "dismiss", "finding_key": f["key"], "reason": reason}, when=t1)
            if service.get_submission(org, sid)["status"] == "compliance_review":
                service.act(ctx("compliance"), sid, {"action": "clear_claims", "reason": "OK"}, when=t1)
            service.act(ctx("reviewer"), sid, {"action": "approve", "reason": "Approved with urgency exception."}, when=t2)
        elif flow == "changes":
            service.act(ctx("compliance"), sid, {"action": "request_changes", "reason": "Price and tone are off-brand. Please use the suggested fixes."}, when=t1)
        elif flow == "reject":
            service.act(ctx("compliance"), sid, {"action": "comment", "text": "This leaks an unreleased product and an internal code name."}, when=t1)
            service.act(ctx("compliance"), sid, {"action": "reject", "reason": "Confidential information. Cannot be published."}, when=t1)
        elif flow == "pending_review":
            for rid, reason in dismissals:
                for f in cur["findings"]:
                    if f["rule_id"] == rid:
                        db.ex("INSERT INTO decisions(org_id,submission_id,version,finding_key,rule_id,action,by_role,by_name,reason,created_at) "
                              "VALUES(?,?,?,?,?,?,?,?,?,?)", (org, sid, cur["version"], f["key"], rid, "contested", "creator", creator, reason, t0))
