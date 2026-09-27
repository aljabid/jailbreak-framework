import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import MagicMock

import pytest

from core.attacker import AttackEngine
from core.evaluator import Evaluator
from core.generator import PromptGenerator
from core.scorer import Scorer
from models.local_model import LocalModel


class TestGeneratorErrorHandling:
    def test_generator_missing_prompts_file_uses_defaults(self):

        gen = PromptGenerator(
            strategies=["roleplay"],
            prompts_file="/nonexistent/prompts.json",
        )
        assert gen.prompt_count > 0

    def test_generator_invalid_strategy_skipped(self):

        gen = PromptGenerator(
            strategies=["roleplay", "nonexistent_strategy"],
        )
        assert "roleplay" in gen.available_strategies
        assert "nonexistent_strategy" not in gen.available_strategies

    def test_generator_generate_with_empty_prompts(self):

        gen = PromptGenerator(strategies=["roleplay"])
        gen._base_prompts = []
        with pytest.raises((IndexError, ValueError)):
            gen.generate("roleplay")

    def test_generator_seed_reproducibility(self):

        gen1 = PromptGenerator(strategies=["roleplay"], seed=42)
        gen2 = PromptGenerator(strategies=["roleplay"], seed=42)

        result1 = gen1.generate("roleplay")
        result2 = gen2.generate("roleplay")

        assert result1["base_prompt_id"] == result2["base_prompt_id"]
        assert result1["base_prompt_text"] == result2["base_prompt_text"]
        assert result1["adversarial_prompt"] == result2["adversarial_prompt"]

    def test_generator_different_seeds_produce_different_results(self):

        gen1 = PromptGenerator(strategies=["token_smuggling"], seed=42)
        gen2 = PromptGenerator(strategies=["token_smuggling"], seed=99)

        result1 = gen1.generate("token_smuggling")
        result2 = gen2.generate("token_smuggling")
        assert result1["adversarial_prompt"] != result2["adversarial_prompt"]


class TestAttackerErrorHandling:
    def test_attacker_handles_model_timeout(self):

        model = MagicMock()
        model.model_name = "test-model"
        model.query.side_effect = TimeoutError("Model timeout")

        engine = AttackEngine(model, max_retries=1, retry_delay=0.01)
        prompt = {"adversarial_prompt": "test", "strategy": "roleplay"}

        result = engine.send(prompt)
        assert result["error"] is not None
        assert result["raw_response"] == ""

    def test_attacker_handles_connection_error(self):

        model = MagicMock()
        model.model_name = "test-model"
        model.query.side_effect = ConnectionError("Cannot connect")

        engine = AttackEngine(model, max_retries=1, retry_delay=0.01)
        prompt = {"adversarial_prompt": "test", "strategy": "roleplay"}

        result = engine.send(prompt)
        assert result["error"] is not None

    def test_attacker_retries_on_transient_failure(self):

        model = MagicMock()
        model.model_name = "test-model"

        model.query.side_effect = [
            Exception("Transient error"),
            {"text": "Success", "tokens_used": 10},
        ]

        engine = AttackEngine(model, max_retries=2, retry_delay=0.01)
        prompt = {"adversarial_prompt": "test", "strategy": "roleplay"}

        result = engine.send(prompt)

        assert result["error"] is None or "Success" in result.get("raw_response", "")

    def test_attacker_exhausts_retries(self):

        model = MagicMock()
        model.model_name = "test-model"
        model.query.side_effect = Exception("Persistent error")

        engine = AttackEngine(model, max_retries=1, retry_delay=0.01)
        prompt = {"adversarial_prompt": "test", "strategy": "roleplay"}

        result = engine.send(prompt)
        assert result["error"] is not None

    def test_attacker_tracks_stats_including_errors(self):

        model = MagicMock()
        model.model_name = "test-model"
        model.query.side_effect = [
            {"text": "OK", "tokens_used": 10},
            Exception("Error"),
        ]

        engine = AttackEngine(model, max_retries=0, retry_delay=0.01)
        engine.send({"adversarial_prompt": "test1", "strategy": "roleplay"})
        engine.send({"adversarial_prompt": "test2", "strategy": "roleplay"})

        stats = engine.stats
        assert stats["total_requests"] == 2
        assert stats["total_errors"] == 1


class TestEvaluatorErrorHandling:
    def test_evaluator_empty_response(self):

        evaluator = Evaluator(mode="keyword")
        result = evaluator.evaluate(
            {
                "raw_response": "",
                "strategy": "roleplay",
            }
        )
        assert result["success"] is False

    def test_evaluator_none_response(self):

        evaluator = Evaluator(mode="keyword")
        result = evaluator.evaluate(
            {
                "raw_response": None,
                "strategy": "roleplay",
            }
        )
        assert result["success"] is False

    def test_evaluator_error_record(self):

        evaluator = Evaluator(mode="keyword")
        result = evaluator.evaluate(
            {
                "raw_response": "Some text",
                "error": "API error",
                "strategy": "roleplay",
            }
        )
        assert result["success"] is False

    def test_evaluator_very_long_response(self):

        evaluator = Evaluator(mode="keyword")
        long_response = "Sure, here's how: " + ("step " * 10000)
        result = evaluator.evaluate(
            {
                "raw_response": long_response,
                "strategy": "roleplay",
            }
        )
        assert isinstance(result["success"], bool)
        assert isinstance(result["eval_confidence"], float)

    def test_evaluator_special_characters(self):

        evaluator = Evaluator(mode="keyword")
        result = evaluator.evaluate(
            {
                "raw_response": "Sure, here's how: \n\t\r special chars!",
                "strategy": "roleplay",
            }
        )
        assert isinstance(result["success"], bool)


class TestScorerEdgeCases:
    def test_scorer_zero_confidence(self):

        scorer = Scorer()
        result = scorer.score(
            {
                "success": False,
                "eval_confidence": 0.0,
                "strategy": "roleplay",
                "category": "general",
                "raw_response": "",
            }
        )
        assert result["risk_score"] == 0.0
        assert result["risk_level"] in ("None", "Low")

    def test_scorer_max_confidence(self):

        scorer = Scorer()
        result = scorer.score(
            {
                "success": True,
                "eval_confidence": 1.0,
                "strategy": "instruction_override",
                "category": "weapons",
                "raw_response": "bomb synthesis instructions",
            }
        )
        assert 0.0 <= result["risk_score"] <= 1.0
        assert result["risk_level"] in ("High", "Critical")

    def test_scorer_missing_optional_fields(self):

        scorer = Scorer()
        result = scorer.score(
            {
                "success": True,
                "eval_confidence": 0.7,
            }
        )

        assert "risk_score" in result
        assert "risk_level" in result

    def test_scorer_invalid_strategy(self):

        scorer = Scorer()
        result = scorer.score(
            {
                "success": True,
                "eval_confidence": 0.7,
                "strategy": "unknown_strategy",
                "category": "general",
            }
        )

        assert "risk_score" in result

    def test_scorer_invalid_category(self):

        scorer = Scorer()
        result = scorer.score(
            {
                "success": True,
                "eval_confidence": 0.7,
                "strategy": "roleplay",
                "category": "unknown_category",
            }
        )

        assert "risk_score" in result


class TestLocalModelErrorHandling:
    def test_local_model_mock_always_succeeds(self):

        model = LocalModel(mode="mock")
        for _ in range(10):
            result = model.query("Test prompt")
            assert result["text"] is not None
            assert len(result["text"]) > 0

    def test_local_model_invalid_mode_raises(self):

        with pytest.raises(ValueError):
            LocalModel(mode="invalid_mode")

    def test_local_model_ollama_connection_error(self):

        model = LocalModel(mode="ollama", ollama_base_url="http://localhost:54321")
        with pytest.raises((ConnectionError, RuntimeError)):
            model.query("Test prompt")

    def test_local_model_test_connection_mock(self):

        model = LocalModel(mode="mock")
        assert model.test_connection() is True

    def test_local_model_test_connection_ollama_timeout(self):

        model = LocalModel(mode="ollama", ollama_base_url="http://localhost:54321")

        try:
            result = model.test_connection()

            assert isinstance(result, bool)
        except ConnectionError:
            pass


class TestBatchErrorRecovery:
    def test_attacker_batch_with_one_failure(self):

        model = MagicMock()
        model.model_name = "test"
        model.query.side_effect = [
            {"text": "OK", "tokens_used": 10},
            Exception("Failed"),
            {"text": "OK", "tokens_used": 10},
        ]

        engine = AttackEngine(model, max_retries=0, retry_delay=0.01)
        prompts = [{"adversarial_prompt": f"test{i}", "strategy": "roleplay"} for i in range(3)]

        results = engine.send_batch(prompts)
        assert len(results) == 3

        errors = [r for r in results if r.get("error")]
        assert len(errors) >= 1

    def test_evaluator_batch_with_bad_input(self):

        evaluator = Evaluator(mode="keyword")
        results = [
            {"raw_response": "Sure, here's how:", "strategy": "roleplay"},
            {"raw_response": "", "strategy": "encoding"},
            {"raw_response": "I cannot help", "strategy": "roleplay"},
        ]

        eval_results = evaluator.evaluate_batch(results)
        assert len(eval_results) == 3
