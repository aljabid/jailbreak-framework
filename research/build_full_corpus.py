#!/usr/bin/env python3
"""Build the full journal-study base-prompt corpus from the imported benchmarks.

Inputs (written by scripts/import_external_prompts.py into research/data_journal/):
  imported_advbench.json, imported_harmbench_standard.json, imported_strongreject.json,
  imported_jbb.json, imported_sorrybench.json, imported_xstest_unsafe.json
Missing files are skipped, so the corpus can be built as datasets arrive.

What it does:
  1. de-duplicates requests across sources (case/punctuation-insensitive), keeping the
     first source in the priority order above;
  2. orders the result by a seeded proportional interleave over (source, category)
     groups, so any prefix of the file is a representative sample. The framework's -n option takes the first
     N prompts, so a run can be stopped at any N and still be representative;
  3. writes research/data_journal/journal_full_corpus.json (gitignored, local only).

Only counts are printed; no prompt text is shown.

  python research/build_full_corpus.py --seed 42
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "research" / "data_journal"
SOURCES = [
    "imported_advbench.json",
    "imported_harmbench_standard.json",
    "imported_strongreject.json",
    "imported_jbb.json",
    "imported_sorrybench.json",
    "imported_xstest_unsafe.json",
]


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", re.sub(r"\s+", " ", text.lower())).strip()


def load(name: str) -> list[dict]:
    path = DATA / name
    if not path.exists():
        return []
    d = json.loads(path.read_text(encoding="utf-8"))
    return d if isinstance(d, list) else d.get("prompts", [])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output", default=str(DATA / "journal_full_corpus.json"))
    args = ap.parse_args()
    rng = random.Random(args.seed)

    seen: set[str] = set()
    groups: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    per_source = {}
    dropped = collections.Counter()
    for name in SOURCES:
        recs = load(name)
        if not recs:
            print(f"skip (missing): {name}")
            continue
        kept = 0
        for r in recs:
            key = norm(r["text"])
            if not key or key in seen:
                dropped[name] += 1
                continue
            seen.add(key)
            groups[(name, r.get("category", "general"))].append(r)
            kept += 1
        per_source[name] = kept

    # proportional interleave: the j-th of n prompts in a group gets position
    # (j + 0.5) / n, then everything is sorted by position (seeded tie-break). Any prefix of
    # the result therefore holds every (source, category) group in proportion to its size.
    keyed: list[tuple[float, float, dict]] = []
    for g in groups.values():
        rng.shuffle(g)
        n = len(g)
        for j, r in enumerate(g):
            keyed.append(((j + 0.5) / n, rng.random(), r))
    keyed.sort(key=lambda t: (t[0], t[1]))
    picked = [r for _, _, r in keyed]
    for i, r in enumerate(picked, 1):
        r["id"] = f"full_{i:05d}"

    out = Path(args.output)
    out.write_text(json.dumps({"prompts": picked}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out} ({len(picked)} unique base prompts)")
    print("by source:", per_source)
    print("duplicates dropped:", dict(dropped))
    head = collections.Counter(r.get("source", {}).get("name", "?") for r in picked[:300])
    print("first 300 prompts by source (shows the prefix is balanced):", dict(head))


if __name__ == "__main__":
    main()
