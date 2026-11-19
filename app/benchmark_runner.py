"""Accuracy benchmark: rules-only on every sample, and rules + AI on the hard subset.

Used by `python -m benchmark.run_benchmark` (CLI) and by the in-app Accuracy page.
A dedicated 'benchmark' workspace with the ABC Electronics demo brand is used, so results
never depend on anyone's edits to their own Brand Memory.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import Counter, defaultdict

from . import ai, db, engine

SAMPLES_PATH = os.path.join(os.path.dirname(__file__), "..", "benchmark", "samples.json")
_rules_cache: dict = {}
_running = threading.Event()
PROGRESS = {"done": 0, "total": 0}
COOLDOWN_HOURS = 6


def samples() -> list[dict]:
    return json.load(open(SAMPLES_PATH, encoding="utf-8"))


def bench_org() -> int:
    from . import seed
    o = db.one("SELECT id FROM orgs WHERE kind='benchmark' ORDER BY id LIMIT 1")
    if o:
        return o["id"]
    org = db.ex("INSERT INTO orgs(name,kind,created_at,last_active) VALUES(?,?,?,?)", ("Benchmark (ABC Electronics)", "benchmark", db.now(), db.now()))
    seed.seed_org(org, with_history=False, starter=True)
    return org


def hard_subset(items: list[dict]) -> list[dict]:
    """Base (un-prefixed) samples that are non-English, written in words, paraphrased or AI-only, plus some clean ones."""
    seen, out = set(), []
    for s in items:
        key = s["text"]
        if key in seen:
            continue
        hard = s["ai_only"] or s["lang"] != "en" or s["form"] in ("words", "paraphrase") or not s["expect"]
        if hard and not any(s["text"].startswith(p) for p in ("This Diwali, ", "Weekend special: ", "Is Diwali, ", "Naye saal par: ", "इस दिवाली, ", "नए साल पर: ")):
            seen.add(key)
            out.append(s)
    return out


def score(results: list[tuple[dict, set]]) -> dict:
    tp, fp, fn = Counter(), Counter(), Counter()
    groups = defaultdict(lambda: Counter())
    mism = []
    for s, got in results:
        exp = set(s["expect"])
        for r in got & exp:
            tp[r] += 1
        for r in got - exp:
            fp[r] += 1
        for r in exp - got:
            fn[r] += 1
        for gname in (f"lang:{s['lang']}", f"form:{s['form']}", "ai_only" if s["ai_only"] else "rule_detectable"):
            g = groups[gname]
            g["tp"] += len(got & exp)
            g["fp"] += len(got - exp)
            g["fn"] += len(exp - got)
            g["n"] += 1
        if got != exp:
            mism.append({"text": s["text"], "expected": sorted(exp), "got": sorted(got), "lang": s["lang"], "form": s["form"], "ai_only": s["ai_only"]})

    def pr(t, p, n):
        return (round(t / (t + p), 3) if t + p else 1.0, round(t / (t + n), 3) if t + n else 1.0)
    T, P, N = sum(tp.values()), sum(fp.values()), sum(fn.values())
    prec, rec = pr(T, P, N)
    return {
        "samples": len(results), "true_positives": T, "false_positives": P, "false_negatives": N,
        "precision": prec, "recall": rec,
        "f1": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0,
        "groups": {k: {"n": v["n"], "precision": pr(v["tp"], v["fp"], v["fn"])[0], "recall": pr(v["tp"], v["fp"], v["fn"])[1]} for k, v in sorted(groups.items())},
        "per_rule": {r: {"tp": tp[r], "fp": fp[r], "fn": fn[r]} for r in sorted(set(tp) | set(fp) | set(fn))},
        "mismatches": mism,
    }


def run_rules(items: list[dict] | None = None) -> dict:
    items = items or samples()
    brand = db.brand_snapshot(bench_org())
    res = [(s, {f["rule_id"] for f in engine.run_rules(s["text"], brand)["findings"]}) for s in items]
    return score(res)


def run_ai(delay: float = 5.5) -> dict:
    """Rules + AI on the hard subset, and rules-only on the same subset for a fair comparison."""
    items = hard_subset(samples())
    brand = db.brand_snapshot(bench_org())
    rules_only, with_ai, errors = [], [], 0
    ai.USED.clear()
    PROGRESS.update(done=0, total=len(items))
    for s in items:
        rf = engine.run_rules(s["text"], brand)["findings"]
        got_rules = {f["rule_id"] for f in rf}
        info = ai.ai_review(s["text"], brand, rf)
        if info.get("error") and "quota" not in str(info["error"]).lower():
            time.sleep(20)  # the AI service was busy: wait and try once more
            info = ai.ai_review(s["text"], brand, rf)
        if info.get("error"):
            errors += 1
        PROGRESS["done"] += 1
        got_ai = got_rules | {f["rule_id"] for f in info.get("findings", [])}
        rules_only.append((s, got_rules))
        with_ai.append((s, got_ai))
        if not info.get("cached"):
            time.sleep(delay)
    return {"subset_size": len(items), "ai_errors": errors, "model": ai.model_name(), "models_used": dict(ai.USED),
            "rules_only": score(rules_only), "rules_plus_ai": score(with_ai)}


def latest() -> dict:
    n = len(samples())
    if _rules_cache.get("n") != n:
        _rules_cache.update(n=n, result=run_rules())
    r = db.one("SELECT * FROM benchmark_runs WHERE mode='ai' AND status='done' ORDER BY id DESC LIMIT 1")
    running = db.one("SELECT created_at FROM benchmark_runs WHERE mode='ai' AND status='running' ORDER BY id DESC LIMIT 1")
    return {"rules_all": _rules_cache["result"], "ai_run": json.loads(r["result"]) if r else None,
            "ai_run_at": r["finished_at"] if r else None, "ai_running": bool(running and _running.is_set()),
            "progress": dict(PROGRESS) if _running.is_set() else None, "ai_available": ai.available()}


def run_ai_async(force: bool = False) -> dict:
    if _running.is_set():
        return {"started": False, "message": "A benchmark run is already in progress."}
    if not ai.available():
        return {"started": False, "message": "No AI key configured."}
    last = db.one("SELECT finished_at FROM benchmark_runs WHERE mode='ai' AND status='done' ORDER BY id DESC LIMIT 1")
    if not force and last and last["finished_at"]:
        from datetime import datetime, timedelta
        try:
            if datetime.fromisoformat(last["finished_at"]) > datetime.fromisoformat(db.now()) - timedelta(hours=COOLDOWN_HOURS):
                return {"started": False, "message": f"The AI comparison ran recently. It can be re-run every {COOLDOWN_HOURS} hours."}
        except ValueError:
            pass
    rid = db.ex("INSERT INTO benchmark_runs(mode,status,created_at) VALUES(?,?,?)", ("ai", "running", db.now()))
    _running.set()

    def work():
        try:
            out = run_ai()
            db.ex("UPDATE benchmark_runs SET status='done', result=?, finished_at=? WHERE id=?", (json.dumps(out), db.now(), rid))
        except Exception as e:  # noqa: BLE001
            db.ex("UPDATE benchmark_runs SET status='failed', result=?, finished_at=? WHERE id=?", (json.dumps({"error": str(e)}), db.now(), rid))
        finally:
            _running.clear()
    threading.Thread(target=work, daemon=True).start()
    return {"started": True, "run_id": rid, "subset": len(hard_subset(samples()))}
