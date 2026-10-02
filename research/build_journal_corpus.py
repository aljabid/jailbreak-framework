#!/usr/bin/env python3
"""Build a stratified base-prompt corpus for the journal study.

Combines the imported HarmBench, JailbreakBench and StrongREJECT base-prompt
sets (produced by scripts/import_external_prompts.py) and draws a deterministic,
category-balanced sample. The in-the-wild set is NOT included here - those are
jailbreak wrappers (a strategy), not base requests.

Output goes to research/data_journal/journal_base_corpus.json (gitignored):
the framework's base-prompt schema, each record keeping its source attribution.
Only counts are printed; no prompt text is shown.

  python research/build_journal_corpus.py --per-category 6 --seed 42
"""
from __future__ import annotations

import argparse
import collections
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "research" / "data_journal"
SOURCES = ["imported_harmbench.json", "imported_jbb.json", "imported_strongreject.json"]


def load(name: str) -> list[dict]:
    path = DATA / name
    if not path.exists():
        return []
    d = json.loads(path.read_text(encoding="utf-8"))
    return d if isinstance(d, list) else d.get("prompts", [])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-category", type=int, default=6,
                    help="base prompts sampled per (source, category)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output", default=str(DATA / "journal_base_corpus.json"))
    args = ap.parse_args()

    rng = random.Random(args.seed)
    picked: list[dict] = []
    by_source: dict[str, int] = {}
    for name in SOURCES:
        recs = load(name)
        if not recs:
            print(f"skip (missing): {name}")
            continue
        buckets: dict[str, list[dict]] = collections.defaultdict(list)
        for r in recs:
            buckets[r.get("category", "general")].append(r)
        taken = 0
        for cat in sorted(buckets):
            group = buckets[cat][:]
            rng.shuffle(group)
            chosen = group[: args.per_category]
            picked.extend(chosen)
            taken += len(chosen)
        by_source[name] = taken

    # stable, reproducible ordering and fresh ids
    picked.sort(key=lambda r: (r.get("source", {}).get("name", ""), r.get("category", ""), r.get("id", "")))
    for i, r in enumerate(picked, 1):
        r["id"] = f"journal_{i:04d}"

    out = Path(args.output)
    out.write_text(json.dumps({"prompts": picked}, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"wrote {out}  ({len(picked)} base prompts)")
    print("by source:", by_source)
    print("by category:", dict(collections.Counter(
        f"{r.get('source', {}).get('name', '?')}:{r.get('category')}" for r in picked)))


if __name__ == "__main__":
    main()
