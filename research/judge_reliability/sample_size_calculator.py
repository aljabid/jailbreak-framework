#!/usr/bin/env python3
"""How many prompts does a clean sheet need to support a safety claim, given the judge's sensitivity?

A clean sheet of n independent prompts, scored by a judge that detects a harmful response with probability s
and raises no false alarms, has probability (1 - s p)^n when the true harm rate is p. To bound p with
confidence 1 - alpha after a clean sheet: n >= ln(alpha) / ln(1 - s p).

  python research/judge_reliability/sample_size_calculator.py --p 0.01 --sensitivity 0.5
  python research/judge_reliability/sample_size_calculator.py --table
"""
from __future__ import annotations

import argparse
import math


def prompts_needed(p: float, sensitivity: float, confidence: float = 0.95) -> int:
    return math.ceil(math.log(1 - confidence) / math.log(1 - p * sensitivity))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p", type=float, help="harm rate to rule out, e.g. 0.01")
    ap.add_argument("--sensitivity", type=float, default=1.0)
    ap.add_argument("--confidence", type=float, default=0.95)
    ap.add_argument("--table", action="store_true")
    a = ap.parse_args()
    if a.table or a.p is None:
        sens = (1.0, 0.75, 0.5, 0.25)
        print(f"prompts needed for a clean sheet at {int(100 * a.confidence)}% confidence")
        print(f"{'harm rate p':>12}" + "".join(f"{'s=' + str(s):>10}" for s in sens))
        for p in (0.1, 0.05, 0.02, 0.01, 0.005, 0.001):
            print(f"{p:>12}" + "".join(f"{prompts_needed(p, s, a.confidence):>10}" for s in sens))
        return
    print(prompts_needed(a.p, a.sensitivity, a.confidence))


if __name__ == "__main__":
    main()
