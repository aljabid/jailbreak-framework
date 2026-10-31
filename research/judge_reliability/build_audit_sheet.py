#!/usr/bin/env python3
"""Build the stratified human-audit sheets for the GPU-run population (three annotators).

Design (see STUDY_PLAN.md section 7, LITERATURE_REVIEW.md section 7):
  * main-arm strata from the four judges' verdicts: all_no (dominant), disagree, all_yes;
  * all_no is sampled equally per target model (substratum = model) so every model has a direct estimate of
    what the judges miss; disagree is sampled with a per-model floor; all_yes is taken whole;
  * control arm (benign XSTest prompts): per model, half from responses some judge flagged and half from
    unflagged ones, to measure false positives;
  * every sampled item records its substratum size N and sample size n, so population estimates can use
    exact inclusion probabilities n/N;
  * each item is labelled by two of three annotators; a random 300 are labelled by all three; the first 30 of
    those form a shared calibration block that every annotator does first;
  * annotators see neutral item ids, never the model name, strategy or any judge verdict.

Outputs (all under labeling_v2/, gitignored because they contain raw responses):
  key_private.json        item id -> true uid, model, strategy, stratum, N, n, judge votes, annotators
  sheet_<A|B|C>.csv       per-annotator sheet; label_<A|B|C>.html  per-annotator labelling page
  summary.json            counts only (safe to read and to commit if wanted)

  python research/judge_reliability/build_audit_sheet.py --seed 20261031
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import random
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import gpu_population as gp  # noqa: E402

OUT = HERE / "labeling_v2"
ANNOTATORS = ["A", "B", "C"]
ALL_NO_PER_MODEL = 50
DISAGREE_TOTAL = 450
DISAGREE_FLOOR = 30
CONTROL_PER_MODEL = 50
TRIPLE = 300
CALIBRATION = 30


def disagree_quotas(counts: dict[str, int], total: int, floor: int) -> dict[str, int]:
    """Models with at most `floor` items give all of them; the rest share the remaining budget by size."""
    quota = {m: n for m, n in counts.items() if n <= floor}
    rest = {m: n for m, n in counts.items() if m not in quota}
    left = max(0, total - sum(quota.values()))
    size = sum(rest.values())
    for m, n in rest.items():
        quota[m] = min(n, max(floor, round(left * n / size))) if size else 0
    return quota


def pick(rng: random.Random, items: list[dict], k: int) -> list[dict]:
    items = list(items)
    rng.shuffle(items)
    return items[:k]


def sample(main: list[dict], control: list[dict], rng: random.Random) -> list[dict]:
    chosen: list[dict] = []

    def add(group: list[dict], k: int, stratum: str, sub: str) -> None:
        for r in pick(rng, group, k):
            chosen.append({**r, "audit_stratum": stratum, "substratum": sub,
                           "sub_N": len(group), "sub_n": min(k, len(group))})

    by_model: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in main:
        by_model[r["model"]][r["stratum"]].append(r)
    for m in sorted(by_model):
        add(by_model[m]["all_no"], ALL_NO_PER_MODEL, "all_no", f"all_no|{m}")
        add(by_model[m]["all_yes"], len(by_model[m]["all_yes"]), "all_yes", f"all_yes|{m}")
    quotas = disagree_quotas({m: len(by_model[m]["disagree"]) for m in by_model}, DISAGREE_TOTAL,
                             DISAGREE_FLOOR)
    for m in sorted(by_model):
        add(by_model[m]["disagree"], quotas[m], "disagree", f"disagree|{m}")

    cmodels: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in control:
        cmodels[r["model"]]["flagged" if r["n_yes"] else "unflagged"].append(r)
    for m in sorted(cmodels):
        add(cmodels[m]["flagged"], CONTROL_PER_MODEL // 2, "control_flagged", f"control_flagged|{m}")
        add(cmodels[m]["unflagged"], CONTROL_PER_MODEL // 2, "control_unflagged", f"control_unflagged|{m}")
    return chosen


def assign(items: list[dict], rng: random.Random) -> None:
    """Add 'annotators' (two or three of A, B, C) and 'calibration' to every item, in place."""
    order = list(range(len(items)))
    rng.shuffle(order)
    triple = set(order[:TRIPLE])
    calib = set(order[:CALIBRATION])
    pairs = itertools.cycle(list(itertools.combinations(ANNOTATORS, 2)))
    for i in order:
        items[i]["annotators"] = list(ANNOTATORS) if i in triple else list(next(pairs))
        items[i]["calibration"] = i in calib


def write_sheets(items: list[dict], seed: int) -> None:
    OUT.mkdir(exist_ok=True)
    ids = random.Random(seed + 1).sample(range(10 ** 5), len(items))
    for item, n in zip(items, ids, strict=True):
        item["item_id"] = f"I{n:05d}"
    key: dict[str, Any] = {}
    for it in items:
        key[it["item_id"]] = {k: it[k] for k in (
            "uid", "arm", "model", "strategy", "category", "base_prompt_id", "votes", "n_yes", "stratum",
            "audit_stratum", "substratum", "sub_N", "sub_n", "annotators", "calibration")}
    (OUT / "key_private.json").write_text(json.dumps(key, indent=1), encoding="utf-8")

    for a in ANNOTATORS:
        mine = [it for it in items if a in it["annotators"]]
        calib = sorted((it for it in mine if it["calibration"]), key=lambda it: it["item_id"])
        rest = [it for it in mine if not it["calibration"]]
        random.Random(f"{seed}-{a}").shuffle(rest)
        ordered = calib + rest
        sheet = OUT / f"sheet_{a}.csv"
        with sheet.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["row", "uid", "model", "strategy", "category", "original_request",
                        "model_response", "label", "notes"])
            for i, it in enumerate(ordered, 1):
                w.writerow([i, it["item_id"], "", "", it["category"], it["request"], it["response"], "", ""])
        subprocess.run([sys.executable, str(HERE / "build_labeling_tool.py"), "--sheet", str(sheet),
                        "--out", str(OUT / f"label_{a}.html"), "--key", f"jbf_audit_{seed}_{a}"],
                       check=True, stdout=subprocess.DEVNULL)

    counts: dict[str, Any] = {"seed": seed, "items": len(items),
                              "by_audit_stratum": defaultdict(int), "by_substratum": {},
                              "per_annotator": {a: sum(a in it["annotators"] for it in items)
                                                for a in ANNOTATORS},
                              "triple": sum(len(it["annotators"]) == 3 for it in items),
                              "calibration": sum(it["calibration"] for it in items)}
    for it in items:
        counts["by_audit_stratum"][it["audit_stratum"]] += 1
        counts["by_substratum"][it["substratum"]] = [it["sub_n"], it["sub_N"]]
    counts["by_audit_stratum"] = dict(counts["by_audit_stratum"])
    (OUT / "summary.json").write_text(json.dumps(counts, indent=1), encoding="utf-8")
    print(json.dumps({k: counts[k] for k in ("items", "by_audit_stratum", "per_annotator", "triple",
                                              "calibration")}, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261031)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    main_rows, ex1 = gp.collect_main()
    ctrl_rows, ex2 = gp.collect_control()
    print(f"population: main {len(main_rows)} (excluded {dict(ex1)}), control {len(ctrl_rows)} "
          f"(excluded {dict(ex2)})")
    items = sample(main_rows, ctrl_rows, rng)
    assign(items, rng)
    write_sheets(items, args.seed)


if __name__ == "__main__":
    main()
