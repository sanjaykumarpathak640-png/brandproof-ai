"""BrandProof deterministic governance engine.

Every finding produced here is backed by a rule ID and, where relevant, an
approved fact from Brand Memory. These checks run in code, so they are exact,
repeatable and work even when no AI model is configured.
"""
from __future__ import annotations

import re
from typing import Any

from . import lang

SEV_WEIGHT = {"high": 25, "medium": 10, "review": 4}
SEV_ORDER = {"high": 0, "medium": 1, "review": 2}

ALLOWED_CAPS = {"ABC", "IPX4", "INR", "GST", "USB", "LED", "HDMI", "EMI", "FAQ", "SPF", "UPI", "COD"}


def fmt_inr(v: float) -> str:
    v = int(round(v))
    s = str(v)
    if len(s) <= 3:
        return "₹" + s
    last3, rest = s[-3:], s[:-3]
    parts = []
    while len(rest) > 2:
        parts.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        parts.insert(0, rest)
    return "₹" + ",".join(parts + [last3])


def _num(s: str) -> float:
    return float(s.replace(",", ""))


class Ctx:
    """Brand Memory snapshot used by one check run."""

    def __init__(self, brand: dict):
        self.brand = brand
        self.meta = brand["meta"]
        self.rules = {r["id"]: r for r in brand["rules"] if r.get("enabled", 1)}
        self.all_rules = {r["id"]: r for r in brand["rules"]}
        self.facts = [f for f in brand["facts"] if f["status"] == "approved"]
        self.current = {}
        self.expired = []
        today = brand.get("today")
        for f in self.facts:
            if f.get("valid_to") and today and f["valid_to"] < today:
                self.expired.append(f)
            else:
                self.current.setdefault(f["key"], f)
        self.terms = [t for t in brand["terms"] if t.get("status", "approved") == "approved"]
        self.palette = brand["palette"]

    def fact(self, key):
        return self.current.get(key)

    def fval(self, key, default=None):
        f = self.fact(key)
        if not f:
            return default
        try:
            return float(f["value"])
        except (TypeError, ValueError):
            return f["value"]


def _ev_fact(f: dict | None) -> dict | None:
    if not f:
        return None
    unit = f" {f['unit']}" if f.get("unit") else ""
    valid = f"valid from {f['valid_from']}" if f.get("valid_from") else ""
    if f.get("valid_to"):
        valid += f" to {f['valid_to']}"
    return {
        "ref": f["id"],
        "text": f"{f['label']} = {f['value']}{unit}",
        "source": f.get("source", ""),
        "valid": valid.strip(),
    }


class Builder:
    def __init__(self, text: str, ctx: Ctx):
        self.text = text
        self.ctx = ctx
        self.findings: list[dict] = []

    def add(self, rule_id, start, end, message, *, replacement=None, fix_note="",
            fact=None, extra_evidence=None, severity=None, engine="rules", metric=None):
        rule = self.ctx.rules.get(rule_id)
        if not rule:
            return  # rule disabled or missing -> no evidence, no flag
        ev = []
        ev.append({"ref": rule["id"], "text": rule["title"] + (": " + rule["description"] if rule.get("description") else ""),
                   "source": rule.get("source", "")})
        fe = _ev_fact(fact)
        if fe:
            ev.append(fe)
        if extra_evidence:
            ev.extend(extra_evidence)
        f = {
            "rule_id": rule_id,
            "category": rule["category"],
            "severity": severity or rule["severity"],
            "title": rule["title"],
            "quote": self.text[start:end] if end > start else "",
            "start": start,
            "end": end,
            "message": message,
            "evidence": ev,
            "fix": None if replacement is None else {"replacement": replacement, "note": fix_note},
            "engine": engine,
        }
        if metric:
            f["metric"] = metric
        self.findings.append(f)


def _overlaps(a, b):
    return a["start"] < b["end"] and b["start"] < a["end"]


# ---------------------------------------------------------------- checks

def _offer_context(t: str) -> bool:
    return bool(lang.OFFER_WORDS.search(t))


def check_prices(b: Builder):
    ctx, t = b.ctx, b.text
    price_f = ctx.fact("price")
    if not price_f:
        return
    current = float(price_f["value"])
    max_disc = ctx.fval("max_discount", 0) or 0
    offer_ctx = _offer_context(t)
    for p in lang.find_prices(t):
        val = p["value"]
        if val < 100 or abs(val - current) < 0.5:
            continue
        shown = p["text"].strip()
        how = " (written in words)" if p["words"] else ""
        exp = next((f for f in ctx.expired if f["key"] == "price" and abs(float(f["value"]) - val) < 0.5), None)
        if exp:
            b.add("R-PRC-01", p["start"], p["end"],
                  f"{shown}{how} is an outdated price. It was valid until {exp['valid_to']}; the current approved price is {fmt_inr(current)}.",
                  replacement=fmt_inr(current), fix_note="Use the current approved price.",
                  fact=price_f, extra_evidence=[{**_ev_fact(exp), "ref": exp["id"] + " (expired)"}],
                  metric={"found": fmt_inr(val), "approved": fmt_inr(current), "status": "outdated"})
            continue
        floor = current * (1 - max_disc / 100.0)
        if offer_ctx and floor - 0.5 <= val < current:
            continue  # valid offer price within the approved discount
        b.add("R-PRC-01", p["start"], p["end"],
              f"Price {shown}{how} does not match the approved price {fmt_inr(current)}"
              + (f" (lowest allowed offer price is {fmt_inr(floor)})." if max_disc else "."),
              replacement=fmt_inr(current), fix_note="Use the approved price.", fact=price_f,
              metric={"found": fmt_inr(val), "approved": fmt_inr(current)})


def check_discounts(b: Builder):
    ctx, t = b.ctx, b.text
    mf = ctx.fact("max_discount")
    found = lang.find_discounts(t)
    if mf:
        mx = int(float(mf["value"]))
        for d in found:
            n = d["value"]
            if n <= mx:
                continue
            nshow = f"{n:g}%"
            if d.get("phrase"):
                rep, s, e = f"up to {mx}% off", d["start"], d["end"]
            elif d["words"]:
                rep, s, e = f"{mx}", d["num_start"], d["num_end"]
                tail = t[d["num_end"]:d["end"]]
                if not tail.lstrip().startswith("%"):
                    rep = f"{mx}"
            else:
                rep, s, e = str(mx), d["num_start"], d["num_end"]
            b.add("R-PRC-02", s, e,
                  f"Discount of {nshow} in “{d['text'].strip()}”" + (" (written in words)" if d["words"] else "")
                  + f" exceeds the approved maximum of {mx}%.",
                  replacement=rep, fix_note=f"Cap the discount at {mx}%.", fact=mf,
                  metric={"found": nshow, "limit": f"{mx}%"})
    if (found or _offer_context(t)) and not lang.DISCLAIMER.search(t):
        end = len(t.rstrip())
        hindi = bool(re.search(r"[\u0900-\u097F]", t))
        b.add("R-PRC-03", end, end,
              "The content promotes an offer but has no “T&C apply” disclaimer.",
              replacement=" शर्तें लागू।" if hindi else " T&C apply.", fix_note="Append the approved disclaimer.")


def check_warranty(b: Builder):
    ctx, t = b.ctx, b.text
    wf = ctx.fact("warranty_years")
    if not wf:
        return
    w = int(float(wf["value"]))
    hindi = bool(re.search(r"[\u0900-\u097F]", t))
    for m in lang.LIFETIME.finditer(t):
        b.add("R-WAR-01", m.start(), m.end(), f"“{m.group(0)}” promises a lifetime warranty, which is not approved. The approved warranty is {w} years.",
              replacement=(f"{w} साल की वारंटी" if hindi else f"{w}-year warranty"), fix_note="Use the approved warranty period.", fact=wf,
              metric={"found": "lifetime", "approved": f"{w} years"})
    for d in lang.find_warranty_years(t):
        if any(f["start"] < d["end"] and d["start"] < f["end"] for f in b.findings):
            continue
        n = d["value"]
        if abs(n - w) > 0.01:
            b.add("R-WAR-01", d["start"], d["end"], f"Warranty of {n:g} years in “{d['text']}” does not match the approved {w} years.",
                  replacement=(f"{w} साल की वारंटी" if hindi else f"{w}-year warranty"), fix_note="Use the approved warranty period.", fact=wf,
                  metric={"found": f"{n:g} years", "approved": f"{w} years"})


def check_specs(b: Builder):
    ctx, t = b.ctx, b.text
    bf = ctx.fact("battery_hours")
    if bf:
        approved = float(bf["value"])
        for d in lang.find_battery_hours(t):
            n = d["value"]
            if n > approved:
                b.add("R-SPEC-01", d["num_start"], d["num_end"], f"Battery claim of {n:g} hours exceeds the tested value of {approved:g} hours.",
                      replacement=f"{approved:g}", fix_note="Use the tested battery life.", fact=bf,
                      metric={"found": f"{n:g} h", "approved": f"{approved:g} h"})
        for m in lang.ENDLESS_BATTERY.finditer(t):
            b.add("R-SPEC-01", m.start(), m.end(), f"“{m.group(0)}” implies unlimited battery life. The tested value is {approved:g} hours.",
                  replacement=f"battery lasts up to {approved:g} hours", fix_note="State the tested battery life.", fact=bf,
                  metric={"found": "unlimited (implied)", "approved": f"{approved:g} h"})
    ipf = ctx.fact("ip_rating")
    if ipf:
        ip = str(ipf["value"])
        for m in re.finditer(r"\b(?:fully\s+)?water\s?-?proof\b|वॉटरप्रूफ|waterproof", t, re.I):
            if any(f["start"] < m.end() and m.start() < f["end"] for f in b.findings):
                continue
            b.add("R-SPEC-01", m.start(), m.end(), f"“{m.group(0)}” overstates protection. The product is rated {ip} (splash resistant).",
                  replacement=f"splash-resistant ({ip})", fix_note="Describe the approved rating.", fact=ipf,
                  metric={"found": m.group(0), "approved": ip})
        for m in re.finditer(r"\bIP[X\d]\d\b", t):
            if m.group(0).upper() != ip.upper():
                b.add("R-SPEC-01", m.start(), m.end(), f"Rating {m.group(0)} does not match the approved {ip}.",
                      replacement=ip, fix_note="Use the approved rating.", fact=ipf,
                      metric={"found": m.group(0), "approved": ip})


SUPERLATIVES = [
    r"\b(?:india'?s|world'?s|asia'?s|the)\s+(?:no\.?\s?1|number\s+one|#\s?1|best|top|most\s+trusted|greatest)(?:\s+(?P<noun>brand|earbuds|earphones|product|choice|headphones|speakers?))?\b",
    r"(?<![\w#])(?:no\.?\s?1|#\s?1|number\s+one)(?:\s+(?P<noun>brand|earbuds|earphones|product|choice))?\b",
    r"\bbest[- ]in[- ](?:class|india|the\s+world|market)\b",
    r"\b(?:unbeatable|unmatched|world[- ]class)\b",
] + lang.SUPERLATIVES_HI


def check_superlatives(b: Builder):
    ctx, t = b.ctx, b.text
    tagline = ctx.fact("tagline")
    spans = []
    for pat in SUPERLATIVES:
        for m in re.finditer(pat, t, re.I):
            spans.append(m)
    spans.sort(key=lambda m: (m.start(), -(m.end() - m.start())))
    kept = []
    for m in spans:
        if any(m.start() < k.end() and k.start() < m.end() for k in kept):
            continue
        kept.append(m)
    for m in kept:
        noun = (m.groupdict().get("noun") or "").lower() if m.groupdict() else ""
        if noun == "choice":
            rep, note = "a smart choice", "Describe the product without an unverified ranking."
        elif noun == "brand" and tagline:
            rep, note = tagline["value"], "Replace with the approved tagline."
        elif noun:
            rep, note = f"thoughtfully designed {noun}", "Describe the product without an unverified ranking."
        else:
            rep, note = "", "Remove the unverified superlative."
        b.add("R-CLM-01", m.start(), m.end(),
              f"“{m.group(0)}” is a ranking/superlative claim with no approved evidence in Brand Memory.",
              replacement=rep, fix_note=note, fact=tagline if noun == "brand" else None,
              extra_evidence=[{"ref": "Evidence search", "text": "No approved study, award or ranking found for this claim.", "source": "Brand Memory"}])


GUARANTEES = [
    (r"\b100\s?%\s+guaranteed\s+(?P<w>\w+)", lambda m: f"reliable {m.group('w')}"),
    (r"\bguaranteed\s+(?P<w>results|satisfaction|performance|quality)", lambda m: f"great {m.group('w')}"),
    (r"\b100\s?%\s+guarantee\b", lambda m: "our assurance"),
    (r"\bnever\s+fails\b", lambda m: "built to last"),
    (r"\bzero\s+defects?\b", lambda m: "quality-tested"),
] + [(p, (lambda r: (lambda m: r))(r)) for p, r in lang.GUARANTEES_HI]


def check_guarantees(b: Builder):
    for pat, rep in GUARANTEES:
        for m in re.finditer(pat, b.text, re.I):
            if any(f["rule_id"] == "R-CLM-02" and f["start"] < m.end() and m.start() < f["end"] for f in b.findings):
                continue
            b.add("R-CLM-02", m.start(), m.end(), f"“{m.group(0)}” is an absolute guarantee the company has not approved.",
                  replacement=rep(m), fix_note="Use a supportable description.")


def _match_case(src: str, rep: str) -> str:
    if len(src) > 1 and src.isupper():
        return rep
    if src[:1].isupper() and rep:
        return rep[0].upper() + rep[1:]
    return rep


def check_terms(b: Builder):
    for term in b.ctx.terms:
        pat = r"(?<![\w])" + re.escape(term["avoid"]) + r"(?![\w])"
        for m in re.finditer(pat, b.text, re.I):
            b.add("R-TERM-01", m.start(), m.end(),
                  f"“{m.group(0)}” is on the avoid list. Preferred term: “{term['prefer']}”." + (f" {term['note']}" if term.get("note") else ""),
                  replacement=_match_case(m.group(0), term["prefer"]), fix_note="Use the preferred term.",
                  extra_evidence=[{"ref": f"T-{term['id']}", "text": f"Avoid “{term['avoid']}” → use “{term['prefer']}”", "source": "Terminology list"}])
    pf = b.ctx.fact("product_name")
    if pf:
        official = pf["value"]
        first = (b.ctx.meta.get("brand_name") or "").split(" ")[0]
        short = official[len(first) + 1:] if first and official.startswith(first + " ") else official
        for m in re.finditer(r"\bsound\s?-?pods?\b(?:\s+pro\b)?", b.text, re.I):
            if m.group(0) == short or any(f["start"] < m.end() and m.start() < f["end"] for f in b.findings):
                continue
            b.add("R-TERM-02", m.start(), m.end(), f"Product name written as “{m.group(0)}”. The official name is “{short}”.",
                  replacement=short, fix_note="Use the official product name.", fact=pf)


HYPE = [
    (r"\bOMG\b[!,.]*\s*", ""),
    (r"\binsane(?:ly)?\b", "impressive"),
    (r"\bcrazy\b", "great"),
    (r"\bmind[- ]?blowing\b", "impressive"),
    (r"\bjaw[- ]?dropping\b", "remarkable"),
    (r"\bepic\b", "excellent"),
] + lang.HYPE_HI


def check_voice(b: Builder):
    t = b.text
    for pat, rep in HYPE:
        for m in re.finditer(pat, t, re.I):
            b.add("R-VOICE-01", m.start(), m.end(), f"“{m.group(0).strip()}” is hype language; the brand voice is {b.ctx.meta.get('tone', 'professional')}.",
                  replacement=_match_case(m.group(0), rep) if rep else "", fix_note="Use calm, friendly wording.")
    for m in re.finditer(r"!{2,}", t):
        b.add("R-VOICE-01", m.start(), m.end(), "Repeated exclamation marks read as shouting.", replacement="!", fix_note="Use one exclamation mark.")
    for m in re.finditer(r"\b[A-Z][A-Z]{3,}\b", t):
        w = m.group(0)
        if w in ALLOWED_CAPS or any(f["start"] < m.end() and m.start() < f["end"] for f in b.findings):
            continue
        b.add("R-VOICE-01", m.start(), m.end(), f"“{w}” is written in all caps, which reads as shouting.",
              replacement=w.capitalize(), fix_note="Use normal capitalisation.")
    for m in re.finditer(r"\b(?:hurry(?:\s+up)?|last\s+chance|only\s+today|buy\s+now\s+or\s+(?:regret|cry)|don'?t\s+miss\s+out|limited\s+stock|grab\s+it\s+before\s+it'?s\s+gone)\b|" + lang.URGENCY_HI, t, re.I):
        b.add("R-VOICE-02", m.start(), m.end(), f"“{m.group(0)}” is pressure/urgency language. Reviewer should confirm it is allowed for this campaign.")


def check_confidential(b: Builder):
    for term in b.ctx.meta.get("confidential_terms", []):
        for m in re.finditer(r"(?<![\w])" + re.escape(term) + r"(?![\w])", b.text, re.I):
            b.add("R-CONF-01", m.start(), m.end(), f"“{m.group(0)}” is marked confidential in Brand Memory and must not appear in public content.",
                  fix_note="Remove the confidential reference and rewrite the sentence.",
                  extra_evidence=[{"ref": "Confidential list", "text": f"“{term}” — internal / unreleased", "source": "Brand admin"}])


def _syllables(word: str) -> int:
    w = word.lower()
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups)
    if w.endswith("e") and n > 1:
        n -= 1
    return max(1, n)


def readability(text: str) -> dict:
    sentences = [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if re.search(r"\w", s)]
    words = re.findall(r"[A-Za-z']+", text)
    if not words or not sentences:
        return {"flesch": None, "sentences": 0, "words": 0}
    syl = sum(_syllables(w) for w in words)
    flesch = 206.835 - 1.015 * (len(words) / len(sentences)) - 84.6 * (syl / len(words))
    return {"flesch": round(flesch, 1), "sentences": len(sentences), "words": len(words)}


def check_accessibility(b: Builder):
    for m in re.finditer(r"(?:[^.!?\n]|\n(?!\s*\n))+[.!?]?", b.text):
        n = len(re.findall(r"[A-Za-z']+", m.group(0)))
        if n > 28:
            b.add("R-A11Y-01", m.start(), m.end(), f"This sentence has {n} words. Long sentences are hard to read (limit 28).",
                  metric={"found": f"{n} words", "limit": "28 words"})


CHECKS = [check_confidential, check_prices, check_discounts, check_warranty, check_specs,
          check_superlatives, check_guarantees, check_terms, check_voice, check_accessibility]


def resolve(findings: list[dict]) -> list[dict]:
    """Sort findings and mark fixes that overlap a higher-priority fix."""
    findings.sort(key=lambda f: (f["start"], SEV_ORDER[f["severity"]]))
    with_fix = sorted([f for f in findings if f.get("fix") is not None], key=lambda f: (SEV_ORDER[f["severity"]], f["start"]))
    taken = []
    for f in with_fix:
        if f["end"] > f["start"] and any(_overlaps(f, g) for g in taken):
            f["fix"]["overlaps"] = True
        else:
            taken.append(f)
    for i, f in enumerate(findings):
        f["key"] = f"{f['rule_id']}@{f['start']}-{f['end']}"
        f["n"] = i + 1
    return findings


def risk(findings: list[dict]) -> dict:
    by_cat: dict[str, int] = {}
    counts = {"high": 0, "medium": 0, "review": 0}
    total = 0
    for f in findings:
        w = SEV_WEIGHT[f["severity"]]
        total += w
        counts[f["severity"]] += 1
        by_cat[f["category"]] = by_cat.get(f["category"], 0) + w
    score = min(100, total)
    level = "High" if score >= 50 else "Medium" if score >= 20 else "Low" if score > 0 else "Clear"
    return {"score": score, "level": level, "counts": counts, "breakdown": by_cat}


def locate(findings: list[dict], text: str, pages: list[int] | None):
    """Attach paragraph (and page, for PDFs) numbers so long documents can be reviewed per paragraph."""
    para_starts = [0] + [m.end() for m in re.finditer(r"\n\s*\n", text)]
    for f in findings:
        p = sum(1 for s in para_starts if s <= f["start"])
        loc = f"Paragraph {p}"
        if pages:
            pg = sum(1 for s in pages if s <= f["start"])
            loc = f"Page {pg} · " + loc
        f["location"] = loc


def run_rules(text: str, brand: dict, pages: list[int] | None = None) -> dict:
    ctx = Ctx(brand)
    b = Builder(text, ctx)
    for c in CHECKS:
        c(b)
    findings = resolve(b.findings)
    locate(findings, text, pages)
    return {"findings": findings, "risk": risk(findings), "metrics": {"readability": readability(text)}}


# ---------------------------------------------------------------- fixes & purpose guard

def apply_fixes(text: str, findings: list[dict], accepted: list[str]) -> str:
    acc = set(accepted)
    chosen = [f for f in findings if f["key"] in acc and f.get("fix") is not None]
    chosen.sort(key=lambda f: (SEV_ORDER[f["severity"]], f["start"]))
    applied = []
    for f in chosen:
        if f["end"] > f["start"] and any(_overlaps(f, g) for g in applied if g["end"] > g["start"]):
            continue
        if f["end"] == f["start"] and any(g["start"] == f["start"] and g["end"] == g["start"] for g in applied):
            continue
        applied.append(f)
    out = text
    for f in sorted(applied, key=lambda f: (f["start"], f["end"]), reverse=True):
        rep = f["fix"]["replacement"]
        out = out[: f["start"]] + rep + out[f["end"]:]
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\s+([.,!?;:])", r"\1", out)
    out = re.sub(r"([.!?])\s*\.", r"\1", out)
    out = re.sub(r"(^|[\n])\s*[–—-]\s*", r"\1", out)
    out = re.sub(r"[–—-]\s*([!.,])", r"\1", out)
    out = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), out)
    return out.strip()


STOP = set("the and for with that this from your our will into have more about their they them just only also very".split())


def purpose_elements(text: str, brand: dict, goal: str = "") -> dict:
    ctx = Ctx(brand)
    pname = (ctx.fact("product_name") or {}).get("value", "")
    brand_name = brand["meta"].get("brand_name", "")
    names = [n for n in [brand_name, pname, pname.split(" ", 1)[-1] if pname else ""] if n]
    el = {
        "brand_or_product": any(n.lower() in text.lower() for n in names),
        "call_to_action": bool(re.search(r"\b(buy|shop|order|grab|get|visit|call|book|pre-?order|try|enjoy|discover)\b", text, re.I)),
        "offer": bool(re.search(r"%|₹|\b(off|offer|discount|sale|cashback)\b", text, re.I)),
    }
    kw = []
    if goal:
        kw = [w for w in re.findall(r"[a-zA-Z]{4,}", goal.lower()) if w not in STOP]
    el["goal_keywords"] = {w: (w in text.lower()) for w in kw}
    return el


def purpose_guard(before: str, after: str, brand: dict, goal: str = "") -> dict:
    a, b = purpose_elements(before, brand, goal), purpose_elements(after, brand, goal)
    items = []
    labels = {"brand_or_product": "Brand / product named", "call_to_action": "Call-to-action kept", "offer": "Offer kept"}
    for k, lab in labels.items():
        if a[k]:
            items.append({"item": lab, "kept": bool(b[k])})
    for w, present in a["goal_keywords"].items():
        if present:
            items.append({"item": f"Goal word “{w}”", "kept": b["goal_keywords"].get(w, False)})
    kept = sum(1 for i in items if i["kept"])
    return {"items": items, "kept": kept, "total": len(items), "ok": kept == len(items)}
