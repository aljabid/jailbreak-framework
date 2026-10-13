#!/usr/bin/env python3
"""Preliminary checks on the existing nine-model data, before the large labelling effort.

H1 (heterogeneity, no human labels needed): does the rate at which the judges disagree with each other
   differ across target models and across attack strategies? If judge error were homogeneous, the
   disagreement rate would be flat. Tested with a permutation test on a chi-square-like statistic.
H2 (self-preference): is the gpt-oss rubric judge more lenient on gpt-oss targets than on others?
   Leniency = share of responses that at least two of the other three judges call a success but the
   gpt-oss judge calls a failure. gpt-oss targets are compared with the rest.
H3 (labelled items): per-model counts of how the judges relate to the 132 human labels, to show how
   thin per-cell estimation is at the current label count.

Prints and saves aggregate statistics only.

  python research/judge_reliability/preliminary_heterogeneity.py research/judge_reliability/labeling/labels_annotator1.csv
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
OUT = HERE / "out" / "preliminary_heterogeneity.json"
GPT_OSS = {"gpt-oss-20b", "gpt-oss-safeguard-20b"}
SUCCESS = {"jailbreak", "partial"}
ALL = ["keyword", "llm_judge", "llamaguard", "strongreject"]


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("bls", HERE / "build_labeling_sheet.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def complete(rows: list[dict]) -> list[dict]:
    return [r for r in rows if all(j in r["votes"] for j in ALL)]


def wilson(k: int, n: int) -> tuple[float, float]:
    if not n:
        return (0.0, 1.0)
    p, z = k / n, 1.96
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def stat(groups: dict[str, list[int]]) -> float:
    total_n = sum(len(v) for v in groups.values())
    total_k = sum(sum(v) for v in groups.values())
    p = total_k / total_n
    if p in (0, 1):
        return 0.0
    return sum(len(v) * (sum(v) / len(v) - p) ** 2 for v in groups.values()) / (p * (1 - p))


def permutation_p(groups: dict[str, list[int]], reps: int, rng: random.Random) -> float:
    observed = stat(groups)
    flat = [x for v in groups.values() for x in v]
    sizes = [len(v) for v in groups.values()]
    keys = list(groups)
    hits = 0
    for _ in range(reps):
        rng.shuffle(flat)
        i = 0
        shuffled = {}
        for key, size in zip(keys, sizes, strict=True):
            shuffled[key] = flat[i:i + size]
            i += size
        hits += stat(shuffled) >= observed
    return (hits + 1) / (reps + 1)


def disagreement_by(rows: list[dict], field: str) -> dict[str, list[int]]:
    groups: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        groups[str(r[field])].append(int(r["disagree"]))
    return groups


def main(label_paths: list[str]) -> None:
    rows = complete(_load().collect())
    rng = random.Random(20261013)
    results: dict[str, Any] = {"responses_with_all_four_judges": len(rows)}
    print(f"responses scored by all four judges: {len(rows)}")

    print("\nH1  judge-disagreement rate by target model and by strategy (permutation test, 5000 shuffles)")
    for field in ("model", "strategy"):
        groups = disagreement_by(rows, field)
        p = permutation_p(groups, 5000, rng)
        results[f"H1_{field}"] = {"p": p, "rates": {k: [sum(v), len(v)] for k, v in groups.items()}}
        print(f"  by {field}: permutation p = {p:.4f}")
        for k, v in sorted(groups.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
            lo, hi = wilson(sum(v), len(v))
            print(f"    {k:<24}{100 * sum(v) / len(v):5.1f}%  [{100 * lo:4.1f}, {100 * hi:4.1f}]  n={len(v)}")

    print("\nH2  gpt-oss judge leniency (>=2 other judges say success, gpt-oss judge says failure)")
    lenient: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        others = sum(r["votes"][j] for j in ALL if j != "llm_judge")
        if others >= 2:
            lenient["gpt-oss target" if r["model"] in GPT_OSS else "other target"].append(
                int(not r["votes"]["llm_judge"]))
    results["H2"] = {k: [sum(v), len(v)] for k, v in lenient.items()}
    for k, v in lenient.items():
        lo, hi = wilson(sum(v), len(v))
        print(f"  {k:<16} {sum(v)}/{len(v)} = {100 * sum(v) / max(1, len(v)):.1f}%  [{100 * lo:.1f}, {100 * hi:.1f}]")
    if len(lenient) == 2:
        results["H2"]["permutation_p"] = permutation_p(dict(lenient), 5000, rng)
        print(f"  permutation p = {results['H2']['permutation_p']:.4f}")
    print("  (small cells: treat as a hint, not a result)")

    labels: dict[str, bool] = {}
    for path in label_paths:
        with Path(path).open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                value = (r.get("label") or "").strip().lower()
                if value:
                    labels[r["uid"]] = value in SUCCESS
    print(f"\nH3  human-labelled items per model ({len(labels)} labels in total)")
    per: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "pos": 0})
    for r in rows:
        if r["uid"] in labels:
            per[r["model"]]["n"] += 1
            per[r["model"]]["pos"] += int(labels[r["uid"]])
    results["H3"] = per
    for m, c in sorted(per.items()):
        print(f"  {m:<24} labelled {c['n']:>3}   human-positive {c['pos']:>3}")
    thin = sum(1 for c in per.values() if c["n"] < 15)
    print(f"  {thin} of {len(per)} models have fewer than 15 labels: per-cell estimates need the large labelling set")

    OUT.write_text(json.dumps(results, indent=1, default=list), encoding="utf-8")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
