#!/usr/bin/env python3
"""Convert a locally-provided external adversarial-prompt dataset into this
framework's base-prompt schema, preserving attribution.

This script never downloads anything itself. Public red-teaming corpora
(AdvBench, JailbreakBench/JBB-Behaviors, or any other collection) are
release under their own upstream licenses and often contain far more
directly operational harmful-behavior strings than the hand-written,
abstract corpus shipped in data/prompts.json. Bundling that content into
this repository — especially one that gets pushed to a public host — is a
call for the operator to make deliberately, not something done silently on
their behalf. So: obtain the dataset yourself (respecting its license and
terms of use), point this script at the local file, and it will:

  1. Parse it (CSV or JSON, with format-specific defaults for AdvBench and
     JailbreakBench, or fully custom column mapping).
  2. Convert every row into this project's prompt record shape
     ({id, category, text, severity, tags, source}).
  3. Attach a `source` attribution block (name, citation, url, license,
     imported_at) to every imported record, never silently dropping
     provenance.
  4. Write the result to its own file by default (data/imported_prompts.json)
     — kept separate from the curated data/prompts.json unless you pass
     --merge-into to fold it in explicitly.

Usage:
  python scripts/import_external_prompts.py \\
    --source advbench --input /path/to/harmful_behaviors.csv \\
    --output data/imported_prompts.json

  python scripts/import_external_prompts.py \\
    --source jailbreakbench --input /path/to/JBB-Behaviors.csv \\
    --output data/imported_prompts.json

  python scripts/import_external_prompts.py \\
    --source custom --input /path/to/mine.csv \\
    --text-column prompt --category-column category \\
    --output data/imported_prompts.json

Then point a run at it directly:
  python main.py run --mock -s roleplay \\
    --config <(echo 'attack: {base_prompts_file: data/imported_prompts.json}')
or merge into the default corpus with --merge-into data/prompts.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

KNOWN_SOURCES: dict[str, dict[str, str]] = {
    "advbench": {
        "name": "AdvBench",
        "citation": (
            "Zou, Wang, Kolter & Fredrikson (2023), 'Universal and Transferable "
            "Adversarial Attacks on Aligned Language Models'"
        ),
        "url": "https://github.com/llm-attacks/llm-attacks",
        "license": "Check the upstream repository for current license terms before redistribution.",
    },
    "jailbreakbench": {
        "name": "JailbreakBench (JBB-Behaviors)",
        "citation": (
            "Chao, Debenedetti, Robey et al. (2024), 'JailbreakBench: An Open "
            "Robustness Benchmark for Jailbreaking Large Language Models'"
        ),
        "url": "https://github.com/JailbreakBench/jailbreakbench",
        "license": "MIT (verify current terms at the source before redistribution).",
    },
}

DEFAULT_COLUMNS: dict[str, dict[str, str]] = {
    "advbench": {"text": "goal", "category": "", "id": ""},
    "jailbreakbench": {"text": "Goal", "category": "Category", "id": "Index"},
}


def load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for key in ("prompts", "data", "rows", "behaviors"):
                if isinstance(data.get(key), list):
                    return data[key]
            raise ValueError("JSON input must be a list or contain a list under a known key")
        if isinstance(data, list):
            return data
        raise ValueError("Unrecognized JSON input shape")

    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def convert(
    rows: list[dict[str, Any]],
    *,
    source_key: str,
    text_column: str,
    category_column: str,
    id_column: str,
    id_prefix: str,
    default_category: str,
    default_severity: str,
) -> list[dict[str, Any]]:
    source_meta = KNOWN_SOURCES.get(source_key, {"name": source_key, "citation": "", "url": "", "license": ""})
    imported_at = datetime.now(timezone.utc).isoformat()

    records: list[dict[str, Any]] = []
    for i, row in enumerate(rows, start=1):
        text = str(row.get(text_column, "")).strip()
        if not text:
            continue
        category = str(row.get(category_column, "") or default_category).strip().lower() or default_category
        raw_id = str(row.get(id_column, "")).strip() if id_column else ""
        entry_id = f"{id_prefix}_{raw_id}" if raw_id else f"{id_prefix}_{i:04d}"
        records.append(
            {
                "id": entry_id,
                "category": category,
                "text": text,
                "severity": default_severity,
                "tags": ["imported", source_key],
                "source": {
                    "name": source_meta["name"],
                    "citation": source_meta["citation"],
                    "url": source_meta["url"],
                    "license": source_meta["license"],
                    "imported_at": imported_at,
                },
            }
        )
    return records


def merge_into(existing_path: Path, new_records: list[dict[str, Any]]) -> dict[str, Any]:
    payload = json.loads(existing_path.read_text(encoding="utf-8"))
    existing_ids = {p["id"] for p in payload.get("prompts", [])}
    added = 0
    for record in new_records:
        if record["id"] in existing_ids:
            continue
        payload["prompts"].append(record)
        existing_ids.add(record["id"])
        added += 1
    payload["imported_count"] = payload.get("imported_count", 0) + added
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, choices=["advbench", "jailbreakbench", "custom"])
    parser.add_argument("--input", required=True, type=Path, help="Local CSV or JSON file you already obtained")
    parser.add_argument("--output", required=True, type=Path, help="Where to write the converted prompts JSON")
    parser.add_argument("--merge-into", type=Path, default=None, help="Existing prompts.json-shaped file to append into instead of overwriting --output")
    parser.add_argument("--text-column", default=None, help="Column holding the prompt text (required for --source custom)")
    parser.add_argument("--category-column", default=None, help="Column holding a category label, if any")
    parser.add_argument("--id-column", default=None, help="Column holding a stable id, if any")
    parser.add_argument("--id-prefix", default=None, help="Prefix for generated ids (default: the source key)")
    parser.add_argument("--default-category", default="imported", help="Category to use when no category column is mapped")
    parser.add_argument("--default-severity", default="high", help="Severity label to assign to every imported entry")
    parser.add_argument("--dry-run", action="store_true", help="Print counts without writing any file")
    args = parser.parse_args()

    if not args.input.exists():
        parser.error(f"--input not found: {args.input}")

    if args.source == "custom" and not args.text_column:
        parser.error("--text-column is required for --source custom")

    columns = DEFAULT_COLUMNS.get(args.source, {})
    text_column = args.text_column or columns.get("text", "text")
    category_column = args.category_column or columns.get("category", "")
    id_column = args.id_column or columns.get("id", "")
    id_prefix = args.id_prefix or args.source

    rows = load_rows(args.input)
    records = convert(
        rows,
        source_key=args.source,
        text_column=text_column,
        category_column=category_column,
        id_column=id_column,
        id_prefix=id_prefix,
        default_category=args.default_category,
        default_severity=args.default_severity,
    )

    by_category: dict[str, int] = {}
    for record in records:
        by_category[record["category"]] = by_category.get(record["category"], 0) + 1

    print(f"Parsed {len(rows)} input rows -> {len(records)} valid prompt records")
    print(f"By category: {by_category}")
    if not records:
        print("Nothing to write.", file=sys.stderr)
        return 1

    if args.dry_run:
        print("Dry run: no file written.")
        return 0

    if args.merge_into:
        if not args.merge_into.exists():
            parser.error(f"--merge-into target not found: {args.merge_into}")
        payload = merge_into(args.merge_into, records)
        args.merge_into.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Merged into {args.merge_into} ({payload['imported_count']} new records)")
    else:
        payload = {
            "version": "1.0",
            "description": (
                f"Prompts imported from {KNOWN_SOURCES.get(args.source, {}).get('name', args.source)}. "
                "Not reviewed for the abstract/informational style used in data/prompts.json — "
                "these are operator-imported records and carry their own `source` attribution."
            ),
            "prompts": records,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
