"""Rule-engine accuracy benchmark on a labelled set of ABC Electronics samples.

Run:  python -m benchmark.run_benchmark
Counts, per rule, true positives (flagged and expected), false positives (flagged, not expected)
and false negatives (expected, not flagged). AI checks are NOT included here.
"""
import json
import os
import sys
from collections import Counter

os.environ.setdefault("DB_PATH", "/tmp/brandproof_benchmark.db")
if os.path.exists(os.environ["DB_PATH"]):
    os.remove(os.environ["DB_PATH"])
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import db, engine, seed  # noqa: E402


def main():
    seed.seed()
    brand = db.brand_snapshot()
    samples = json.load(open(os.path.join(os.path.dirname(__file__), "samples.json"), encoding="utf-8"))
    tp, fp, fn = Counter(), Counter(), Counter()
    misses = []
    for s in samples:
        got = {f["rule_id"] for f in engine.run_rules(s["text"], brand)["findings"]}
        exp = set(s["expect"])
        for r in got & exp:
            tp[r] += 1
        for r in got - exp:
            fp[r] += 1
        for r in exp - got:
            fn[r] += 1
        if got != exp:
            misses.append({"text": s["text"], "expected": sorted(exp), "got": sorted(got), "note": s.get("note", "")})
    T, P, N = sum(tp.values()), sum(fp.values()), sum(fn.values())
    prec = T / (T + P) if T + P else 1.0
    rec = T / (T + N) if T + N else 1.0
    out = {"samples": len(samples), "true_positives": T, "false_positives": P, "false_negatives": N,
           "precision": round(prec, 3), "recall": round(rec, 3),
           "per_rule": {r: {"tp": tp[r], "fp": fp[r], "fn": fn[r]} for r in sorted(set(tp) | set(fp) | set(fn))},
           "mismatches": misses}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    json.dump(out, open(os.path.join(os.path.dirname(__file__), "results.json"), "w"), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
