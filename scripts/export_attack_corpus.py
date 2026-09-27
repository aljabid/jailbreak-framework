#!/usr/bin/env python3
"""Export the full attack corpus (every strategy x every base prompt) as
JSONL, for use by an external evaluator -- specifically the companion
Prompt Injection Detector project's red-team-vs-blue-team evaluation
(../attack-vs-defense-eval/evaluate.py). Not part of the CLI; a one-off
bridge between the two projects.

Uses PromptGenerator directly (pure stdlib, no model/provider needed) so
this never touches a real target and needs no authorization grant.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.generator import STRATEGY_REGISTRY, PromptGenerator


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="../attack-vs-defense-eval/attacks.jsonl",
        help="Output JSONL path (relative to this script's directory)",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="Base prompts per strategy (default: all 154)",
    )
    args = parser.parse_args()

    strategies = list(STRATEGY_REGISTRY.keys())
    generator = PromptGenerator(
        strategies=strategies,
        prompts_file="data/prompts.json",
        seed=args.seed,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    with output_path.open("w", encoding="utf-8") as handle:
        for strategy_name in strategies:
            batch = generator.generate_batch(strategy_name, count=args.count)
            for prompt in batch:
                record = {
                    "id": f"{strategy_name}_{prompt.get('base_prompt_id', 'unknown')}",
                    "strategy": prompt["strategy"],
                    "category": prompt.get("category", "general"),
                    "base_severity": prompt.get("base_severity", "unknown"),
                    "language": prompt.get("language", "en"),
                    "base_prompt_id": prompt.get("base_prompt_id", "unknown"),
                    "adversarial_prompt": prompt["adversarial_prompt"],
                }
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                total += 1

    print(f"Exported {total} attacks ({len(strategies)} strategies) to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
