from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from importlib import resources
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    dataset_version: str
    dataset_sha256: str
    evaluator_version: str
    total: int
    true_positive: int
    true_negative: int
    false_positive: int
    false_negative: int
    precision: float
    recall: float
    f1: float
    accuracy: float
    outcome_accuracy: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvaluatorBenchmark:
    def __init__(self, evaluator):
        self.evaluator = evaluator

    def run_file(self, path: str | Path) -> BenchmarkReport:
        path = Path(path)
        if path.exists():
            raw = path.read_bytes()
        elif path.name == "evaluation_benchmark.json":
            raw = resources.files("data").joinpath("evaluation_benchmark.json").read_bytes()
        else:
            raise FileNotFoundError(path)
        dataset = json.loads(raw)
        cases = dataset.get("cases")
        if not isinstance(cases, list) or not cases:
            raise ValueError("Benchmark dataset must contain a non-empty cases list")

        tp = tn = fp = fn = outcome_matches = 0
        for case in cases:
            expected = bool(case["expected_success"])
            result = self.evaluator.evaluate(
                {
                    "adversarial_prompt": case.get("attack_prompt", ""),
                    "raw_response": case["response"],
                    "strategy": case.get("strategy", "benchmark"),
                    "category": case.get("category", "general"),
                }
            )
            actual = bool(result["success"])
            if expected and actual:
                tp += 1
            elif not expected and not actual:
                tn += 1
            elif not expected and actual:
                fp += 1
            else:
                fn += 1
            if result.get("eval_outcome") == case.get("expected_outcome"):
                outcome_matches += 1

        total = len(cases)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return BenchmarkReport(
            dataset_version=str(dataset.get("version", "unknown")),
            dataset_sha256=hashlib.sha256(raw).hexdigest(),
            evaluator_version=str(self.evaluator.EVALUATOR_VERSION),
            total=total,
            true_positive=tp,
            true_negative=tn,
            false_positive=fp,
            false_negative=fn,
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1=round(f1, 4),
            accuracy=round((tp + tn) / total, 4),
            outcome_accuracy=round(outcome_matches / total, 4),
        )
