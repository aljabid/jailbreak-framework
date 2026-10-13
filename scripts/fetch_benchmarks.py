#!/usr/bin/env python3
"""Fetch the public safety-benchmark files used by the journal study.

This is a deliberate, operator-run step: nothing is downloaded unless the person
running it passes --accept-terms, confirming they have read each dataset's terms and
will use the files only for authorised safety evaluation. Files are saved to
research/data_journal/ (gitignored, never published) and every file's URL, size,
row count and SHA-256 is recorded in research/data_journal/fetch_manifest.json, so the
exact data versions can be reported in the paper.

  python scripts/fetch_benchmarks.py --list              # show sources, terms, citations
  python scripts/fetch_benchmarks.py --accept-terms      # download what is missing
  python scripts/fetch_benchmarks.py --accept-terms --only xstest

Gated data (SORRY-Bench on Hugging Face) needs an account that has accepted the dataset
terms and a token in the HF_TOKEN environment variable; without it that dataset is skipped
and the rest still works. If a download fails, put the file at the printed path by hand
and run again: existing files that pass validation are kept.

Exit status: 0 when all required datasets are present and valid, 1 otherwise.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "research" / "data_journal"
MANIFEST = DEST / "fetch_manifest.json"

GH = "https://raw.githubusercontent.com"
DATASETS: list[dict[str, Any]] = [
    {
        "key": "advbench",
        "file": "advbench_harmful_behaviors.csv",
        "url": f"{GH}/llm-attacks/llm-attacks/main/data/advbench/harmful_behaviors.csv",
        "columns": ["goal"], "min_rows": 500, "required": True,
        "citation": "Zou et al. (2023), Universal and Transferable Adversarial Attacks on Aligned LLMs",
        "terms": "github.com/llm-attacks/llm-attacks (check the repository license)",
    },
    {
        "key": "harmbench",
        "file": "harmbench_behaviors_text_all.csv",
        "url": f"{GH}/centerforaisafety/HarmBench/main/data/behavior_datasets/harmbench_behaviors_text_all.csv",
        "columns": ["Behavior", "FunctionalCategory", "SemanticCategory", "BehaviorID"],
        "min_rows": 350, "required": True,
        "citation": "Mazeika et al. (2024), HarmBench",
        "terms": "github.com/centerforaisafety/HarmBench (MIT; check current terms)",
    },
    {
        "key": "strongreject",
        "file": "strongreject_dataset.csv",
        "url": f"{GH}/alexandrasouly/strongreject/main/strongreject_dataset/strongreject_dataset.csv",
        "columns": ["forbidden_prompt", "category"], "min_rows": 300, "required": True,
        "citation": "Souly et al. (2024), A StrongREJECT for Empty Jailbreaks",
        "terms": "github.com/alexandrasouly/strongreject (MIT; check current terms)",
    },
    {
        "key": "jailbreakbench",
        "file": "jbb_harmful_behaviors.csv",
        "url": "https://huggingface.co/datasets/JailbreakBench/JBB-Behaviors/resolve/main/data/harmful-behaviors.csv",
        "columns": ["Goal", "Category", "Index"], "min_rows": 95, "required": True,
        "citation": "Chao et al. (2024), JailbreakBench",
        "terms": "huggingface.co/datasets/JailbreakBench/JBB-Behaviors (check the dataset card)",
    },
    {
        "key": "xstest",
        "file": "xstest_prompts.csv",
        "url": f"{GH}/paul-rottger/exaggerated-safety/main/xstest_prompts.csv",
        "columns": ["prompt", "type", "label"], "min_rows": 400, "required": False,
        "citation": "Rottger et al. (2024), XSTest",
        "terms": "github.com/paul-rottger/exaggerated-safety (check the repository license)",
    },
    {
        "key": "sorrybench",
        "file": "question.jsonl",
        "url": "https://huggingface.co/datasets/sorry-bench/sorry-bench-202406/resolve/main/question.jsonl",
        "columns": ["question_id", "category", "turns"], "min_rows": 400, "required": False,
        "gated": True,
        "citation": "Xie et al. (2024), SORRY-Bench",
        "terms": "huggingface.co/datasets/sorry-bench/sorry-bench-202406 (gated: accept the terms there, "
                 "then export HF_TOKEN)",
    },
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl":
        with path.open(encoding="utf-8-sig") as fh:
            return [json.loads(line) for line in fh if line.strip()]
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def validate(path: Path, ds: dict[str, Any]) -> tuple[bool, str, int]:
    """Check the file parses, has the expected columns and enough rows."""
    try:
        rows = read_rows(path)
    except Exception as exc:
        return False, f"cannot parse ({type(exc).__name__})", 0
    if not rows:
        return False, "no rows", 0
    missing = [c for c in ds["columns"] if c not in rows[0]]
    if missing:
        return False, f"missing columns {missing}", len(rows)
    if len(rows) < ds["min_rows"]:
        return False, f"only {len(rows)} rows (expected at least {ds['min_rows']})", len(rows)
    return True, "ok", len(rows)


def download(ds: dict[str, Any]) -> tuple[bool, str]:
    headers = {"User-Agent": "jbf-research/1.0"}
    token = os.environ.get("HF_TOKEN")
    if token and "huggingface.co" in ds["url"]:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(ds["url"], headers=headers)
    target = DEST / ds["file"]
    tmp = target.with_suffix(target.suffix + ".part")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, tmp.open("wb") as out:
            while chunk := resp.read(1 << 20):
                out.write(chunk)
    except urllib.error.HTTPError as exc:
        tmp.unlink(missing_ok=True)
        if exc.code in (401, 403) and ds.get("gated"):
            return False, "gated: accept the dataset terms on Hugging Face and set HF_TOKEN"
        return False, f"HTTP {exc.code}"
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        return False, f"{type(exc).__name__}: {exc}"
    tmp.replace(target)
    return True, "downloaded"


def show_list() -> None:
    print("Sources used by the study (all are public research benchmarks):\n")
    for ds in DATASETS:
        flag = "required" if ds["required"] else "optional"
        print(f"* {ds['key']} ({flag}){' [gated]' if ds.get('gated') else ''}")
        print(f"    {ds['citation']}")
        print(f"    terms: {ds['terms']}")
        print(f"    url:   {ds['url']}")
        print(f"    saved: research/data_journal/{ds['file']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="show sources, terms and citations, then exit")
    ap.add_argument("--accept-terms", action="store_true",
                    help="confirm you read each dataset's terms and will use the files only for "
                         "authorised safety evaluation")
    ap.add_argument("--only", nargs="+", help="fetch only these dataset keys")
    args = ap.parse_args()

    if args.list:
        show_list()
        return 0
    chosen = [d for d in DATASETS if not args.only or d["key"] in args.only]
    # consent is only needed when something has to be downloaded
    to_download = [d for d in chosen
                   if not (DEST / d["file"]).exists() or not validate(DEST / d["file"], d)[0]]
    if to_download and not args.accept_terms:
        show_list()
        print(f"\nNothing downloaded (still needed: {[d['key'] for d in to_download]}). Read the "
              "terms above, then re-run with --accept-terms if you agree to use these files only for "
              "authorised safety evaluation.")
        return 2

    DEST.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {}
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    problems = []
    for ds in chosen:
        path = DEST / ds["file"]
        ok, why, rows = (validate(path, ds) if path.exists() else (False, "not present", 0))
        status = "kept (already valid)" if ok else None
        if not ok:
            got, msg = download(ds)
            if got:
                ok, why, rows = validate(path, ds)
                status = "downloaded" if ok else f"downloaded but invalid: {why}"
            else:
                status = f"not fetched: {msg}"
                if path.exists():
                    path.unlink()
        print(f"[{ds['key']:<14}] {status}" + (f" ({rows} rows)" if ok else ""))
        if ok:
            manifest[ds["key"]] = {
                "file": ds["file"], "url": ds["url"], "rows": rows,
                "bytes": path.stat().st_size, "sha256": sha256(path),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "citation": ds["citation"],
            }
        elif ds["required"]:
            problems.append(ds["key"])
            print(f"    -> put the file at {path} by hand, then run this script again")
        else:
            print("    -> optional; the study can proceed without it")
    MANIFEST.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    if problems:
        print(f"\nMissing required datasets: {problems}")
        return 1
    print(f"\nAll required datasets are present. Manifest: {MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
