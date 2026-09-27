import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from core.attacker import AttackEngine
from core.generator import STRATEGY_REGISTRY, PromptGenerator
from models.local_model import LocalModel

ALL_STRATEGIES = list(STRATEGY_REGISTRY.keys())


class TestPromptGenerator:
    def setup_method(self):
        self.gen = PromptGenerator(
            strategies=ALL_STRATEGIES,
            prompts_file="data/prompts.json",
            seed=42,
        )

    def test_loads_strategies(self):
        assert len(self.gen.available_strategies) == len(ALL_STRATEGIES)

    def test_generate_returns_dict(self):
        result = self.gen.generate("roleplay")
        assert isinstance(result, dict)

    def test_generate_has_required_keys(self):
        result = self.gen.generate("roleplay")
        required = [
            "strategy",
            "adversarial_prompt",
            "base_prompt_text",
            "category",
            "strategy_metadata",
        ]
        for key in required:
            assert key in result, f"Missing key: {key}"

    def test_generate_all_strategies(self):
        for strat in ALL_STRATEGIES:
            result = self.gen.generate(strat)
            assert result["strategy"] == strat
            assert len(result["adversarial_prompt"]) > 10

    def test_generate_batch(self):
        batch = self.gen.generate_batch("roleplay", count=3)
        assert len(batch) == 3
        for item in batch:
            assert item["strategy"] == "roleplay"

    def test_generate_all_iterator(self):
        results = list(self.gen.generate_all())
        assert len(results) > 0
        assert all("adversarial_prompt" in r for r in results)

    def test_generate_campaign(self):
        results = self.gen.generate_campaign("roleplay", variations=2)

        assert len(results) > 0
        assert all(r["strategy"] == "roleplay" for r in results)
        assert all("variation" in r for r in results)

    def test_invalid_strategy_raises(self):
        with pytest.raises(ValueError):
            self.gen.generate("nonexistent_strategy")

    def test_strategy_info(self):
        info = self.gen.strategy_info()
        for strat in ALL_STRATEGIES:
            assert strat in info
            assert "name" in info[strat]

    def test_prompt_count(self):
        assert self.gen.prompt_count > 0

    def test_unknown_strategy_skipped(self):
        gen = PromptGenerator(strategies=["roleplay", "totally_fake_strategy"])
        assert "roleplay" in gen.available_strategies
        assert "totally_fake_strategy" not in gen.available_strategies

    def test_category_filter_restricts_base_prompts(self):
        unfiltered = PromptGenerator(strategies=["roleplay"], prompts_file="data/prompts.json")
        filtered = PromptGenerator(
            strategies=["roleplay"],
            prompts_file="data/prompts.json",
            categories=["privacy"],
        )
        assert filtered.prompt_count <= unfiltered.prompt_count
        assert filtered.prompt_count > 0

    def test_category_filter_is_case_insensitive(self):
        gen = PromptGenerator(
            strategies=["roleplay"],
            prompts_file="data/prompts.json",
            categories=["PRIVACY"],
        )
        assert gen.prompt_count > 0

    def test_unmatched_category_falls_back_to_unfiltered(self):
        unfiltered = PromptGenerator(strategies=["roleplay"], prompts_file="data/prompts.json")
        gen = PromptGenerator(
            strategies=["roleplay"],
            prompts_file="data/prompts.json",
            categories=["totally_nonexistent_category"],
        )
        assert gen.prompt_count == unfiltered.prompt_count


class TestLocalModelMock:
    def setup_method(self):
        self.model = LocalModel(mode="mock", mock_success_rate=0.5)

    def test_query_returns_dict(self):
        result = self.model.query("Test prompt")
        assert isinstance(result, dict)

    def test_query_has_text(self):
        result = self.model.query("Test prompt")
        assert "text" in result
        assert isinstance(result["text"], str)
        assert len(result["text"]) > 0

    def test_query_has_tokens(self):
        result = self.model.query("Test prompt")
        assert "tokens_used" in result
        assert result["tokens_used"] >= 0

    def test_test_connection(self):
        assert self.model.test_connection() is True

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError):
            LocalModel(mode="invalid_mode")


class TestAttackEngine:
    def setup_method(self):
        self.model = LocalModel(mode="mock", mock_success_rate=0.5)
        self.engine = AttackEngine(
            model=self.model,
            max_retries=1,
            retry_delay=0.01,
            rate_limit_delay=0.01,
        )
        self.gen = PromptGenerator(
            strategies=["roleplay"],
            prompts_file="data/prompts.json",
            seed=99,
        )

    def test_send_returns_dict(self):
        prompt = self.gen.generate("roleplay")
        result = self.engine.send(prompt)
        assert isinstance(result, dict)

    def test_send_has_required_keys(self):
        prompt = self.gen.generate("roleplay")
        result = self.engine.send(prompt)
        required = ["raw_response", "model_name", "response_tokens", "request_duration_ms", "error"]
        for key in required:
            assert key in result, f"Missing key: {key}"

    def test_send_batch(self):
        batch = self.gen.generate_batch("roleplay", count=3)
        results = self.engine.send_batch(batch)
        assert len(results) == 3

    def test_stats_tracking(self):
        prompt = self.gen.generate("roleplay")
        self.engine.send(prompt)
        stats = self.engine.stats
        assert stats["total_requests"] == 1

    def test_error_handled_gracefully(self):

        from unittest.mock import MagicMock

        bad_model = MagicMock()
        bad_model.model_name = "bad-model"
        bad_model.query.side_effect = Exception("Simulated API error")

        engine = AttackEngine(bad_model, max_retries=1, retry_delay=0.01)
        prompt = self.gen.generate("roleplay")
        result = engine.send(prompt)

        assert result["error"] is not None
        assert result["raw_response"] == ""

    def test_zero_or_negative_max_workers_raises(self):
        with pytest.raises(ValueError):
            AttackEngine(self.model, max_workers=0)


class TestAttackEngineConcurrency:
    def setup_method(self):
        self.model = LocalModel(mode="mock", mock_success_rate=0.5)
        self.gen = PromptGenerator(
            strategies=["roleplay"],
            prompts_file="data/prompts.json",
            seed=7,
        )

    def test_concurrent_batch_returns_results_in_order(self):
        engine = AttackEngine(
            model=self.model,
            max_retries=0,
            retry_delay=0.01,
            max_workers=4,
        )
        batch = self.gen.generate_batch("roleplay", count=8)
        results = engine.send_batch(batch)

        assert len(results) == len(batch)
        for prompt, result in zip(batch, results, strict=True):
            assert result["base_prompt_id"] == prompt["base_prompt_id"]

    def test_concurrent_stats_are_consistent(self):
        engine = AttackEngine(
            model=self.model,
            max_retries=0,
            retry_delay=0.01,
            max_workers=4,
        )
        batch = self.gen.generate_batch("roleplay", count=12)
        engine.send_batch(batch)

        assert engine.stats["total_requests"] == 12

    def test_concurrent_and_sequential_produce_same_count(self):
        sequential = AttackEngine(
            model=LocalModel(mode="mock", mock_success_rate=0.5, seed=1),
            max_retries=0,
            retry_delay=0.01,
            max_workers=1,
        )
        concurrent = AttackEngine(
            model=LocalModel(mode="mock", mock_success_rate=0.5, seed=1),
            max_retries=0,
            retry_delay=0.01,
            max_workers=4,
        )
        batch = self.gen.generate_batch("roleplay", count=6)

        seq_results = sequential.send_batch(batch)
        conc_results = concurrent.send_batch(batch)

        assert len(seq_results) == len(conc_results) == 6
