#!/usr/bin/env python3
"""Build a blind re-read sheet for the lead author: the items whose labels decide the headline numbers.

Contents: every all-judges-say-no item that any rater called a success, every item where two raters
disagree on the success scale, and a random sample of the remaining items (so the re-reader is not led
by the selection). Item order is shuffled; no model, strategy, stratum, judge verdict or previous label is
shown. Output: labeling_v2/recheck/sheet.csv and label.html (gitignored: contains raw responses).

  python research/judge_reliability/build_recheck_sheet.py --extra 80
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import gpu_population as gp  # noqa: E402

V2 = HERE / "labeling_v2"
SUCCESS = {"jailbreak", "partial"}


def load_labels(folder: Path) -> dict[str, dict[str, str]]:
    by_item: dict[str, dict[str, str]] = {}
    for p in sorted(folder.glob("labels_?.csv")):
        letter = p.stem.split("_")[1]
        with p.open(encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                v = (r.get("label") or "").strip().lower()
                if v:
                    by_item.setdefault(r["uid"], {})[letter] = v
    return by_item


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extra", type=int, default=80)
    ap.add_argument("--seed", type=int, default=20261101)
    ap.add_argument("--human-dir", default=str(V2 / "human"))
    args = ap.parse_args()
    rng = random.Random(args.seed)
    key = json.loads((V2 / "key_private.json").read_text(encoding="utf-8"))
    labs = load_labels(Path(args.human_dir))

    must: list[str] = []
    for item, k in key.items():
        votes = [v in SUCCESS for v in labs.get(item, {}).values()]
        conflict = len(set(votes)) > 1
        if (k["audit_stratum"] == "all_no" and any(votes)) or conflict:
            must.append(item)
    rest = [i for i in key if i not in set(must)]
    rng.shuffle(rest)
    chosen = must + rest[: args.extra]
    rng.shuffle(chosen)

    pop = {r["uid"]: r for r in [*gp.collect_main()[0], *gp.collect_control()[0]]}
    out = V2 / "recheck"
    out.mkdir(exist_ok=True)
    sheet = out / "sheet.csv"
    with sheet.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["row", "uid", "model", "strategy", "category", "original_request", "model_response",
                    "label", "notes"])
        for n, item in enumerate(chosen, 1):
            r = pop[key[item]["uid"]]
            w.writerow([n, item, "", "", r["category"], r["request"], r["response"], "", ""])
    subprocess.run([sys.executable, str(HERE / "build_labeling_tool.py"), "--sheet", str(sheet),
                    "--out", str(out / "label.html"), "--key", f"jbf_recheck_{args.seed}"],
                   check=True, stdout=subprocess.DEVNULL)
    print(f"recheck sheet: {len(chosen)} items ({len(must)} decisive + {len(chosen) - len(must)} random) in {out}")


if __name__ == "__main__":
    main()
