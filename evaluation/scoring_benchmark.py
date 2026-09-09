from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from importlib import resources
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ScoringBenchmarkReport:
    dataset_version: str
    dataset_sha256: str
    scoring_version: str
    total: int
    level_accuracy: float
    within_expected_range: float
    mean_absolute_error: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ScoringBenchmark:
    def __init__(self, scorer):
        self.scorer = scorer

    def run_file(self, path: str | Path) -> ScoringBenchmarkReport:
        path = Path(path)
        if path.exists():
            raw = path.read_bytes()
        elif path.name == "scoring_benchmark.json":
            raw = resources.files("data").joinpath("scoring_benchmark.json").read_bytes()
        else:
            raise FileNotFoundError(path)
        dataset = json.loads(raw)
        cases = dataset.get("cases")
        if not isinstance(cases, list) or not cases:
            raise ValueError("Scoring benchmark requires a non-empty cases list")

        level_matches = range_matches = 0
        absolute_errors = []
        for case in cases:
            result = self.scorer.score(case["evaluation"])
            if result["risk_level"] == case["expected_level"]:
                level_matches += 1
            minimum, maximum = case["expected_score_range"]
            if minimum <= result["risk_score"] <= maximum:
                range_matches += 1
            target = (minimum + maximum) / 2
            absolute_errors.append(abs(result["risk_score"] - target))

        total = len(cases)
        return ScoringBenchmarkReport(
            dataset_version=str(dataset.get("version", "unknown")),
            dataset_sha256=hashlib.sha256(raw).hexdigest(),
            scoring_version=self.scorer.SCORING_VERSION,
            total=total,
            level_accuracy=round(level_matches / total, 4),
            within_expected_range=round(range_matches / total, 4),
            mean_absolute_error=round(sum(absolute_errors) / total, 4),
        )
