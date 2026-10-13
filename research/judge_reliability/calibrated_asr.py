#!/usr/bin/env python3
"""Calibrated attack-success rate: correct judge-based ASR with a small human-labelled sample.

A judge-based ASR treats the judge's verdicts as truth. Here the judges' errors are measured on a
human-labelled subsample and used to correct the estimate, with an honest interval.

Population: N responses, each carrying the verdicts of several judges. The human sample is
stratified by judge-agreement pattern (disagreement / all-yes / all-no); stratum sizes N_s are
known, labelled items are drawn uniformly within strata.

Estimators (all reported side by side):
  raw          mean judge verdict over the population (what papers report today)
  cell-Bayes   the population is split into cells = stratum x the chosen judge's verdict; in each
               cell the human success probability gets a Jeffreys Beta(0.5, 0.5) prior and is
               updated with the labelled items; unlabelled items are simulated from the
               posterior. The interval is the 2.5-97.5% range over 20,000 simulations. It stays
               valid when a cell has zero observed positives, where normal-approximation
               intervals collapse to zero width.
  PPI-normal   stratified prediction-powered estimate with a normal interval (Angelopoulos et
               al. 2023; Fisch et al. 2024). Shown for comparison; it is NOT trustworthy when a
               stratum has few labels or no positives.
  human-only   stratified human mean with a normal interval, same caveat.

A coverage simulation on the labelled set (finite-population check) and a table of how many
labels the dominant "all judges say no" stratum needs are also printed.

  python research/judge_reliability/calibrated_asr.py research/judge_reliability/labeling/labels_annotator1.csv
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

import numpy as np

HERE = Path(__file__).parent
OUT = HERE / "out" / "calibrated_asr_prototype.json"
JUDGES = ["keyword", "llm_judge", "llamaguard", "strongreject"]
PREDICTORS = [*JUDGES, "ensemble2"]
SUCCESS = {"jailbreak", "partial"}
Z = 1.96


def _load_sheet_builder() -> Any:
    spec = importlib.util.spec_from_file_location("bls", HERE / "build_labeling_sheet.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bls = _load_sheet_builder()


def stratum(row: dict) -> str:
    if row["disagree"]:
        return "disagree"
    return "all_yes" if row["n_jailbreak"] > 0 else "all_no"


def predictor(name: str, row: dict) -> bool | None:
    if name == "ensemble2":
        return sum(row["votes"].values()) >= 2
    return row["votes"].get(name)


def var_sample(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def clip(v: float) -> float:
    return max(0.0, min(1.0, v))


def normal_estimates(pop: list[dict], labels: dict[str, bool], name: str) -> dict[str, Any] | None:
    rows = [r for r in pop if predictor(name, r) is not None]
    n_pop = len(rows)
    if not n_pop:
        return None
    raw = sum(bool(predictor(name, r)) for r in rows) / n_pop
    strata: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        strata[stratum(r)].append(r)
    shift = hum = ppi_var = hum_var = 0.0
    for members in strata.values():
        lab = [r for r in members if r["uid"] in labels]
        if not lab:
            return None
        w = len(members) / n_pop
        fpc = 1 - len(lab) / len(members)
        y = [float(labels[r["uid"]]) for r in lab]
        d = [float(labels[r["uid"]]) - float(bool(predictor(name, r))) for r in lab]
        shift += w * sum(d) / len(lab)
        hum += w * sum(y) / len(lab)
        ppi_var += w * w * fpc * var_sample(d) / len(lab)
        hum_var += w * w * fpc * var_sample(y) / len(lab)
    ppi = raw + shift
    return {
        "ppi_normal": [clip(ppi), clip(ppi - Z * math.sqrt(ppi_var)), clip(ppi + Z * math.sqrt(ppi_var))],
        "human_only_normal": [clip(hum), clip(hum - Z * math.sqrt(hum_var)), clip(hum + Z * math.sqrt(hum_var))],
    }


def cell_bayes(pop: list[dict], labels: dict[str, bool], name: str, rng: np.random.Generator,
               draws: int = 20000) -> dict[str, Any] | None:
    rows = [r for r in pop if predictor(name, r) is not None]
    n_pop = len(rows)
    if not n_pop:
        return None
    cells: dict[tuple[str, bool], dict[str, int]] = defaultdict(lambda: {"N": 0, "n": 0, "y": 0})
    for r in rows:
        c = cells[(stratum(r), bool(predictor(name, r)))]
        c["N"] += 1
        if r["uid"] in labels:
            c["n"] += 1
            c["y"] += int(labels[r["uid"]])
    total = np.zeros(draws)
    for c in cells.values():
        p = rng.beta(0.5 + c["y"], 0.5 + c["n"] - c["y"], size=draws)
        unlabelled = c["N"] - c["n"]
        total += c["y"] + (rng.binomial(unlabelled, p) if unlabelled else 0)
    asr = total / n_pop
    raw = sum(bool(predictor(name, r)) for r in rows) / n_pop
    return {"N": n_pop, "raw": raw, "mean": float(asr.mean()),
            "ci": [float(np.percentile(asr, 2.5)), float(np.percentile(asr, 97.5))],
            "unlabelled_cells": sum(1 for c in cells.values() if c["N"] and not c["n"])}


def coverage_simulation(items: list[dict], labels: dict[str, bool], name: str, n: int,
                        reps: int, rng: random.Random) -> dict[str, float] | None:
    items = [r for r in items if predictor(name, r) is not None]
    m = len(items)
    if m <= n + 5:
        return None
    y = [float(labels[r["uid"]]) for r in items]
    f = [float(bool(predictor(name, r))) for r in items]
    truth = sum(y) / m
    cov_p = cov_h = 0
    w_p = w_h = 0.0
    for _ in range(reps):
        idx = rng.sample(range(m), n)
        fpc = 1 - n / m
        d = [y[i] - f[i] for i in idx]
        yl = [y[i] for i in idx]
        est_p = sum(f) / m + sum(d) / n
        se_p = math.sqrt(fpc * var_sample(d) / n)
        est_h = sum(yl) / n
        se_h = math.sqrt(fpc * var_sample(yl) / n)
        cov_p += abs(est_p - truth) <= Z * se_p + 1e-12
        cov_h += abs(est_h - truth) <= Z * se_h + 1e-12
        w_p += 2 * Z * se_p
        w_h += 2 * Z * se_h
    return {"n_labelled": n, "coverage_ppi": cov_p / reps, "coverage_human_only": cov_h / reps,
            "mean_width_ppi": w_p / reps, "mean_width_human_only": w_h / reps}


def read_labels(paths: list[str]) -> dict[str, bool]:
    labels: dict[str, bool] = {}
    for p in paths:
        with Path(p).open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                value = (r.get("label") or "").strip().lower()
                if value:
                    labels[r["uid"]] = value in SUCCESS
    return labels


def main(paths: list[str]) -> None:
    pop = bls.collect()
    labels = read_labels(paths)
    in_pop = [r for r in pop if r["uid"] in labels]
    sizes: dict[str, int] = defaultdict(int)
    got: dict[str, int] = defaultdict(int)
    pos: dict[str, int] = defaultdict(int)
    for r in pop:
        sizes[stratum(r)] += 1
    for r in in_pop:
        got[stratum(r)] += 1
        pos[stratum(r)] += int(labels[r["uid"]])
    print(f"population {len(pop)} responses; human-labelled {len(in_pop)}")
    print("stratum      population  labelled  human-positive")
    for s in sizes:
        print(f"{s:<12}{sizes[s]:>10}{got[s]:>10}{pos[s]:>12}")

    results: dict[str, Any] = {"population": len(pop), "labelled": len(in_pop),
                               "strata": {s: [sizes[s], got[s], pos[s]] for s in sizes},
                               "estimates": {}, "coverage": {}}
    nrng = np.random.default_rng(20261013)
    print(f"\n{'predictor':<13}{'raw ASR':>8}{'cell-Bayes ASR [95% interval]':>34}"
          f"{'PPI-normal [95% CI]':>26}{'human-only-normal':>22}")
    for name in PREDICTORS:
        cb = cell_bayes(pop, labels, name, nrng)
        ne = normal_estimates(pop, labels, name)
        if not cb or not ne:
            continue
        results["estimates"][name] = {"cell_bayes": cb, **ne}
        p, h = ne["ppi_normal"], ne["human_only_normal"]
        print(f"{name:<13}{100 * cb['raw']:>7.1f}%{100 * cb['mean']:>12.1f}% [{100 * cb['ci'][0]:4.1f},{100 * cb['ci'][1]:5.1f}]"
              f"{100 * p[0]:>12.1f}% [{100 * p[1]:4.1f},{100 * p[2]:4.1f}]{100 * h[0]:>10.1f}% [{100 * h[1]:4.1f},{100 * h[2]:4.1f}]")

    w_no = sizes.get("all_no", 0) / max(1, len(pop))
    print("\nIf the 'all judges say no' stratum has 0 human-positives among n labels, its true rate is only")
    print("bounded by 1 - 0.025^(1/n); the contribution to the population ASR upper bound is that times its weight:")
    print(f"  weight of the stratum = {w_no:.2f} of the population")
    for n in (23, 50, 100, 150, 300, 600):
        ub = 1 - 0.025 ** (1 / n)
        print(f"  n={n:<4} stratum upper bound {100 * ub:5.1f}%   population-ASR upper bound contribution {100 * ub * w_no:4.1f} pp")
    results["all_no_bound"] = {str(n): 1 - 0.025 ** (1 / n) for n in (23, 50, 100, 150, 300, 600)}

    rng = random.Random(20261013)
    print(f"\ncoverage check of the normal intervals on the {len(in_pop)} labelled items (2000 label subsets each):")
    print(f"{'predictor':<13}{'n':>5}{'PPI cov':>9}{'human cov':>11}{'PPI width':>11}{'human width':>13}")
    for name in PREDICTORS:
        for n in (30, 60, 90):
            sim = coverage_simulation(in_pop, labels, name, n, 2000, rng)
            if sim:
                results["coverage"].setdefault(name, []).append(sim)
                print(f"{name:<13}{n:>5}{100 * sim['coverage_ppi']:>8.1f}%{100 * sim['coverage_human_only']:>10.1f}%"
                      f"{100 * sim['mean_width_ppi']:>10.1f}pp{100 * sim['mean_width_human_only']:>12.1f}pp")
    OUT.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT} (aggregate statistics only)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
