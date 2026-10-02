#!/usr/bin/env python3
"""Judge the 132 human-labelled sheet items with the v2 rubric.

Reads labeling/labeling_sheet.csv (uid, request, response), runs judge_llm_v2
on each, and writes labeling/sheet_llmv2.json keyed by uid. Resumable. This
lets rank_judges / analyze_labels compare the improved judge to v1 and the
others against the human gold labels, on exactly the labelled set.

  python research/judge_reliability/judge_sheet_v2.py
"""
from __future__ import annotations

import csv
import importlib.util
import json
import time
from pathlib import Path

HERE = Path(__file__).parent
SHEET = HERE / "labeling" / "labeling_sheet.csv"
OUT = HERE / "labeling" / "sheet_llmv2.json"

spec = importlib.util.spec_from_file_location("v2", HERE / "judge_llm_v2.py")
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)


def main() -> None:
    key = v2.api_key()
    rows = list(csv.DictReader(SHEET.open(encoding="utf-8")))
    done = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    print(f"{len(rows)} items, {len(done)} already judged", flush=True)
    for i, r in enumerate(rows, 1):
        uid = r["uid"]
        if uid in done and done[uid].get("verdict") not in (None, "UNCLEAR"):
            continue
        v = v2.judge(key, r["original_request"], r["model_response"])
        succ, _ = v2.MAP[v["verdict"]]
        done[uid] = {"verdict": v["verdict"], "success": succ}
        OUT.write_text(json.dumps(done, indent=1), encoding="utf-8")
        print(f"  [{i}/{len(rows)}] {uid[:40]} -> {v['verdict']}", flush=True)
        time.sleep(v2.SLEEP)
    print("done", flush=True)


if __name__ == "__main__":
    main()
