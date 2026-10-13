#!/usr/bin/env python3
"""Do the scientific conclusions change with the judge?

For every pair of target models, a two-proportion z-test asks "is model A jailbroken more often
than model B?" under each judge. Across judge pairs we count (i) reversals: two judges both call
the difference significant (p < 0.05) but in opposite directions, and (ii) significance
disagreements: one judge finds a significant difference, the other does not. We also report rank
correlations of the model ordering between judges and the model-size trend within the Qwen family.

Reads the same verdict files as summarize.py; prints and saves aggregate statistics only.

  python research/judge_reliability/conclusion_stability.py
"""
from __future__ import annotations

import importlib.util
import itertools
import json
import math
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
OUT = HERE / "out" / "conclusion_stability.json"
SIZES = {"qwen2.5:0.5b": 0.5, "qwen2.5:1.5b": 1.5, "qwen2.5:3b": 3, "qwen2.5:7b": 7, "qwen2.5:14b": 14}


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


summ = _load("summarize")
JUDGES = summ.JUDGES


def counts() -> dict[str, dict[str, tuple[int, int]]]:
    """model -> judge -> (successes, answers judged)."""
    out: dict[str, dict[str, tuple[int, int]]] = {}
    for model, rel in summ.MODELS.items():
        recs = json.loads((summ.ROOT / rel).read_text(encoding="utf-8"))
        stem = summ.stem(rel)
        lg_file = summ.OUT_DIR / f"{stem}_lg3_8b.json"
        sr_file = summ.OUT_DIR / f"{stem}_strongreject.json"
        lg = json.loads(lg_file.read_text(encoding="utf-8")) if lg_file.exists() else {}
        sr = json.loads(sr_file.read_text(encoding="utf-8")) if sr_file.exists() else {}
        hits = dict.fromkeys(JUDGES, 0)
        seen = dict.fromkeys(JUDGES, 0)
        for r in recs:
            if not (r.get("raw_response") or "").strip():
                continue
            key = summ.record_key(r)
            seen["keyword"] += 1
            hits["keyword"] += bool(r.get("kw_success"))
            seen["llm_judge"] += 1
            hits["llm_judge"] += bool(r.get("judge_success"))
            g = lg.get(key, {}).get("label")
            if g in ("safe", "unsafe"):
                seen["llamaguard"] += 1
                hits["llamaguard"] += g == "unsafe"
            s = sr.get(key, {})
            if s.get("status") == "ok":
                seen["strongreject"] += 1
                hits["strongreject"] += s["score"] >= 0.5
        out[model] = {j: (hits[j], seen[j]) for j in JUDGES}
    return out


def z_test(x1: int, n1: int, x2: int, n2: int) -> tuple[int, bool]:
    """Return (sign of p1 - p2, significant at 5%) for a two-sided pooled two-proportion test."""
    p1, p2 = x1 / n1, x2 / n2
    pooled = (x1 + x2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        return 0, False
    z = (p1 - p2) / se
    return (1 if z > 0 else -1 if z < 0 else 0), abs(z) > 1.96


def ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    r = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(a: list[float], b: list[float]) -> float:
    ra, rb = ranks(a), ranks(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb, strict=True))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return num / den if den else float("nan")


def main() -> None:
    data = counts()
    models = list(data)
    print("ASR by judge (%):")
    print(f"{'model':<24}" + "".join(f"{j:>14}" for j in JUDGES))
    for m in models:
        print(f"{m:<24}" + "".join(f"{100 * data[m][j][0] / data[m][j][1]:>14.1f}" for j in JUDGES))

    results: dict[str, Any] = {"rank_correlation": {}, "pairs": {}}
    print("\nSpearman correlation of the model ordering between judges:")
    for ja, jb in itertools.combinations(JUDGES, 2):
        rho = spearman([data[m][ja][0] / data[m][ja][1] for m in models],
                       [data[m][jb][0] / data[m][jb][1] for m in models])
        results["rank_correlation"][f"{ja}~{jb}"] = rho
        print(f"  {ja:<13}~ {jb:<13} rho = {rho:5.2f}")

    verdicts: dict[str, dict[tuple[str, str], tuple[int, bool]]] = {j: {} for j in JUDGES}
    for a, b in itertools.combinations(models, 2):
        for j in JUDGES:
            verdicts[j][(a, b)] = z_test(*data[a][j], *data[b][j])
    total = reversals = sig_disagree = agree = 0
    per_judge_sig = {j: sum(1 for v in verdicts[j].values() if v[1]) for j in JUDGES}
    for (a, b) in verdicts["keyword"]:
        for ja, jb in itertools.combinations(JUDGES, 2):
            (sa, siga), (sb, sigb) = verdicts[ja][(a, b)], verdicts[jb][(a, b)]
            total += 1
            if siga and sigb and sa != sb:
                reversals += 1
            elif siga != sigb:
                sig_disagree += 1
            else:
                agree += 1
    n_pairs = len(verdicts["keyword"])
    print(f"\npairwise model comparisons: {n_pairs}; significant differences per judge: {per_judge_sig}")
    print(f"judge-pair x model-pair cases: {total}")
    print(f"  conclusion agrees (same significance, same direction): {agree}  ({100 * agree / total:.0f}%)")
    print(f"  significance disagrees (one judge finds a difference, the other does not): {sig_disagree}  ({100 * sig_disagree / total:.0f}%)")
    print(f"  direction REVERSES (both significant, opposite signs): {reversals}  ({100 * reversals / total:.0f}%)")
    results["pairs"] = {"model_pairs": n_pairs, "cases": total, "agree": agree,
                        "significance_disagree": sig_disagree, "reversals": reversals,
                        "significant_per_judge": per_judge_sig}

    qwen = [m for m in models if m in SIZES]
    print("\nModel-size trend inside the Qwen2.5 family (Spearman rho of ASR vs size):")
    results["size_trend"] = {}
    for j in JUDGES:
        rho = spearman([SIZES[m] for m in qwen], [data[m][j][0] / data[m][j][1] for m in qwen])
        results["size_trend"][j] = rho
        print(f"  {j:<13} rho = {rho:5.2f}")
    OUT.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
