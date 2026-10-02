#!/usr/bin/env python3
"""Rank the automated judges against the human gold standard.

Reads one or more labels.csv files (human labelers) and labeling_key.json, then
ranks the four judges by Cohen's kappa with the humans and writes:

  out/judge_ranking.csv   - judge, accuracy, precision, recall, F1, kappa
  out/fig_judge_ranking.png - kappa bar chart with an agreement-strength scale

With two labelers it uses the items both agreed on as the gold set and prints
the human-human kappa for context.

  python research/judge_reliability/rank_judges.py labels_annotator1.csv [labels_annotator2.csv]
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SHEET_DIR = Path(__file__).parent / "labeling"
OUT_DIR = Path(__file__).parent / "out"
JUDGES = ["keyword", "llm_judge", "llamaguard", "strongreject"]
LABELS = {"keyword": "Keyword", "llm_judge": "gpt-oss judge",
          "llamaguard": "Llama Guard 8B", "strongreject": "StrongREJECT"}
SUCCESS = {"jailbreak", "partial"}


def load(path: Path) -> dict[str, str]:
    return {r["uid"]: (r.get("label") or "").strip().lower()
            for r in csv.DictReader(path.open(encoding="utf-8"))
            if (r.get("label") or "").strip()}


def kappa(a: list[bool], b: list[bool]) -> float:
    n = len(a)
    if not n:
        return math.nan
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return math.nan if pe == 1 else (po - pe) / (1 - pe)


def main(paths: list[str]) -> None:
    key = json.loads((SHEET_DIR / "labeling_key.json").read_text(encoding="utf-8"))
    labelers = [load(Path(p)) for p in paths]

    if len(labelers) >= 2:
        shared = [u for u in labelers[0] if u in labelers[1]]
        hh = kappa([labelers[0][u] in SUCCESS for u in shared],
                   [labelers[1][u] in SUCCESS for u in shared])
        gold = {u: labelers[0][u] for u in shared
                if (labelers[0][u] in SUCCESS) == (labelers[1][u] in SUCCESS)}
        print(f"Human-human kappa: {hh:.2f} on {len(shared)} shared; "
              f"gold = {len(gold)} agreed items")
    else:
        gold = labelers[0]
        print(f"Single annotator: {len(gold)} items")

    def ensemble_vote(votes: dict, rule: str) -> bool | None:
        vals = [votes[j] for j in JUDGES if j in votes]
        if not vals:
            return None
        if rule == "majority":
            return sum(vals) * 2 > len(vals)
        if rule == "any":  # flag if any judge flags (high recall)
            return any(vals)
        return sum(vals) >= 2  # "two_plus": at least two judges agree

    def score(name: str, decide) -> dict:
        pairs = [(gold[u] in SUCCESS, decide(key[u])) for u in uids]
        pairs = [(h, d) for h, d in pairs if d is not None]
        h = [p[0] for p in pairs]
        jd = [p[1] for p in pairs]
        n = len(pairs)
        acc = sum(x == y for x, y in zip(h, jd, strict=True)) / n
        tp = sum(x and y for x, y in zip(h, jd, strict=True))
        fp = sum((not x) and y for x, y in zip(h, jd, strict=True))
        fn = sum(x and (not y) for x, y in zip(h, jd, strict=True))
        prec = tp / (tp + fp) if tp + fp else math.nan
        rec = tp / (tp + fn) if tp + fn else math.nan
        f1 = 2 * prec * rec / (prec + rec) if prec and rec and prec + rec else math.nan
        return {"judge": name, "acc": acc, "prec": prec, "rec": rec,
                "f1": f1, "kappa": kappa(h, jd), "n": n}

    def single(judge: str):
        return lambda k: k["votes"].get(judge)

    uids = [u for u in gold if u in key]
    rows = [score(LABELS[j], single(j)) for j in JUDGES]
    rows.append(score("Ensemble (2+)", lambda k: ensemble_vote(k["votes"], "two_plus")))
    rows.append(score("Ensemble (majority)", lambda k: ensemble_vote(k["votes"], "majority")))
    rows.append(score("Ensemble (any)", lambda k: ensemble_vote(k["votes"], "any")))
    rows.sort(key=lambda r: (r["kappa"] if r["kappa"] == r["kappa"] else -9))
    rows.reverse()

    csv_path = OUT_DIR / "judge_ranking.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["rank", "judge", "accuracy", "precision", "recall", "F1", "kappa", "n"])
        for i, r in enumerate(rows, 1):
            w.writerow([i, r["judge"], f"{r['acc']:.2f}", f"{r['prec']:.2f}",
                        f"{r['rec']:.2f}", f"{r['f1']:.2f}", f"{r['kappa']:.3f}", r["n"]])
    print(f"\nwrote {csv_path}")

    print(f"\n{'rank':<5}{'judge':<16}{'acc':>6}{'prec':>7}{'rec':>7}{'F1':>7}{'kappa':>8}")
    for i, r in enumerate(rows, 1):
        print(f"{i:<5}{r['judge']:<16}{r['acc']:>6.2f}{r['prec']:>7.2f}"
              f"{r['rec']:>7.2f}{r['f1']:>7.2f}{r['kappa']:>8.3f}")

    fig, ax = plt.subplots(figsize=(8, 4.2))
    names = [r["judge"] for r in rows]
    kaps = [r["kappa"] for r in rows]
    colors = ["#54A24B" if k >= 0.4 else "#F58518" if k >= 0.2 else "#E45756" for k in kaps]
    ax.barh(names[::-1], kaps[::-1], color=colors[::-1])
    for band, lab in [(0.2, "slight"), (0.4, "fair"), (0.6, "moderate")]:
        ax.axvline(band, color="#aaa", lw=0.8, ls="--")
        ax.text(band, -0.6, lab, fontsize=8, color="#888", ha="center")
    ax.set_xlabel("Cohen's κ agreement with human labels")
    ax.set_title("Which judge matches human judgement best")
    ax.set_xlim(0, max(0.6, max(k for k in kaps if k == k) + 0.1))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig_path = OUT_DIR / "fig_judge_ranking.png"
    fig.savefig(fig_path, dpi=150)
    print(f"wrote {fig_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
