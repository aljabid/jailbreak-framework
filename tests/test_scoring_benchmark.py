import pytest
from click.testing import CliRunner

from core.scorer import Scorer
from evaluation.scoring_benchmark import ScoringBenchmark
from main import cli


def test_versioned_scoring_dimensions_are_exposed():
    result = Scorer().score(
        {
            "success": True,
            "eval_confidence": 0.9,
            "eval_outcome": "full_compliance",
            "strategy": "roleplay",
            "category": "general",
            "raw_response": "response",
        }
    )
    assert result["scoring_version"] == "2.0"
    assert 0 <= result["likelihood"] <= 1
    assert 0 <= result["impact"] <= 1
    assert 0 <= result["exploitability"] <= 1
    assert 0 <= result["evidence_confidence"] <= 1


def test_scoring_calibration_dataset_passes():
    report = ScoringBenchmark(Scorer()).run_file("data/scoring_benchmark.json")
    assert report.total == 6
    assert report.level_accuracy >= 0.95
    assert report.within_expected_range >= 0.95
    assert report.mean_absolute_error <= 0.08
    assert len(report.dataset_sha256) == 64


def test_human_override_preserves_automated_assessment():
    scorer = Scorer()
    automated = scorer.score(
        {
            "success": False,
            "eval_confidence": 0,
            "eval_outcome": "refusal",
        }
    )
    overridden = scorer.override(
        automated,
        risk_level="High",
        reason="Confirmed harmful tool action in external evidence",
        reviewer="reviewer@example.test",
    )
    assert overridden["automated_risk_level"] == "None"
    assert overridden["risk_level"] == "High"
    assert overridden["risk_override"]["reason"]


def test_human_override_requires_attribution():
    with pytest.raises(ValueError):
        Scorer().override({}, "High", reason="", reviewer="reviewer")


def test_scoring_benchmark_cli_gate():
    result = CliRunner().invoke(cli, ["benchmark-scoring"])
    assert result.exit_code == 0, result.output
    assert '"scoring_version": "2.0"' in result.output
