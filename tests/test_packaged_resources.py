import json
from importlib import resources
from pathlib import Path

from core.evaluator import Evaluator
from core.generator import PromptGenerator

SOURCE_ROOT = Path(__file__).resolve().parent.parent


def test_bundled_datasets_match_source_datasets():
    bundled_prompts = json.loads(resources.files("data").joinpath("prompts.json").read_text())
    bundled_keywords = json.loads(
        resources.files("data").joinpath("jailbreak_keywords.json").read_text()
    )
    assert bundled_prompts == json.loads((SOURCE_ROOT / "data/prompts.json").read_text())
    assert bundled_keywords == json.loads(
        (SOURCE_ROOT / "data/jailbreak_keywords.json").read_text()
    )


def test_generator_uses_bundled_dataset_when_cwd_file_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    generator = PromptGenerator(["roleplay"], prompts_file="data/prompts.json")
    assert generator.prompt_count == 154


def test_evaluator_uses_bundled_keywords_when_cwd_file_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bundled = json.loads(
        resources.files("data").joinpath("jailbreak_keywords.json").read_text()
    )
    evaluator = Evaluator(keywords_file="data/jailbreak_keywords.json")
    assert evaluator._success_keywords == bundled["success_keywords"]
    assert evaluator._refusal_keywords == bundled["refusal_keywords"]
    assert len(evaluator._success_keywords) >= 40
    assert len(evaluator._refusal_keywords) >= 40


def test_benchmarks_use_bundled_data_when_cwd_files_missing(tmp_path, monkeypatch):
    from core.scorer import Scorer
    from evaluation.benchmark import EvaluatorBenchmark
    from evaluation.scoring_benchmark import ScoringBenchmark

    monkeypatch.chdir(tmp_path)
    assert EvaluatorBenchmark(Evaluator()).run_file("data/evaluation_benchmark.json").total == 38
    assert ScoringBenchmark(Scorer()).run_file("data/scoring_benchmark.json").total == 6
