import importlib.util
from pathlib import Path

import pytest

STUDY = Path(__file__).resolve().parent.parent / "research" / "remote_gpu" / "study.py"
spec = importlib.util.spec_from_file_location("study_driver", STUDY)
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)


def test_slow_hardware_limits_prompts_to_the_budget():
    # 40 s of attack time per prompt-strategy across all models: 40*6/3600 = 0.0667 h per prompt
    plan = study.plan_stages(40.0, 1088, 75.0, n_models=8)
    assert plan.n_max == 675  # 45 h generation share / 0.0667 h
    assert plan.stages == [300, 675]
    assert plan.projected_generation_hours <= 45.0


def test_fast_hardware_uses_the_whole_corpus_in_three_stages():
    plan = study.plan_stages(10.0, 1088, 75.0, n_models=8)
    assert plan.stages == [300, 700, 1088]
    assert plan.n_max == 1088


def test_tiny_corpus_collapses_stages():
    plan = study.plan_stages(5.0, 120, 75.0, n_models=2)
    assert plan.stages == [120]


def test_budget_too_small_is_rejected():
    with pytest.raises(ValueError):
        study.plan_stages(600.0, 1088, 1.0, n_models=8)


def test_judge_sample_is_clamped():
    plan = study.plan_stages(40.0, 1088, 75.0, n_models=8)
    assert 50 <= plan.judge_k_max <= plan.n_max
    small = study.plan_stages(1.0, 1088, 1.0, n_models=8)
    assert small.judge_k_max >= 50
