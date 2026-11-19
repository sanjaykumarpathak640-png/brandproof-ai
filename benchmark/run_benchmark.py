"""Accuracy benchmark for BrandProof AI.

  python -m benchmark.run_benchmark          # rules-only on all samples (no network needed)
  python -m benchmark.run_benchmark --ai     # also rules + AI on the hard subset (needs GEMINI_API_KEY)

Writes benchmark/results.json (and results_ai.json with --ai).
"""
import json
import os
import sys

os.environ.setdefault("DB_PATH", "/tmp/brandproof_benchmark.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import benchmark_runner  # noqa: E402


def main():
    here = os.path.dirname(__file__)
    r = benchmark_runner.run_rules()
    json.dump(r, open(os.path.join(here, "results.json"), "w"), indent=2, ensure_ascii=False)
    print(f"Rules-only, all {r['samples']} samples: precision {r['precision']}, recall {r['recall']}, F1 {r['f1']}")
    for g, v in r["groups"].items():
        print(f"  {g:22s} n={v['n']:3d}  precision {v['precision']:.3f}  recall {v['recall']:.3f}")
    if "--ai" in sys.argv:
        a = benchmark_runner.run_ai()
        json.dump(a, open(os.path.join(here, "results_ai.json"), "w"), indent=2, ensure_ascii=False)
        print(f"Hard subset ({a['subset_size']}): rules-only recall {a['rules_only']['recall']} → rules+AI recall {a['rules_plus_ai']['recall']}")


if __name__ == "__main__":
    main()
