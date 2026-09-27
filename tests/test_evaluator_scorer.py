import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from core.evaluator import Evaluator
from core.scorer import RiskLevel, Scorer


def make_result(response: str, strategy: str = "roleplay", category: str = "general"):
    return {
        "strategy": strategy,
        "category": category,
        "base_prompt_id": "test_001",
        "base_prompt_text": "Test prompt",
        "adversarial_prompt": "Adversarial version of test prompt",
        "raw_response": response,
        "error": None,
    }


CLEAR_REFUSAL = "I'm sorry, but I cannot help with that request. It goes against my guidelines."
CLEAR_COMPLIANCE = "Sure, here's a step-by-step guide: Step 1: you need to first..."
BORDERLINE = "That's an interesting topic. Here's some general information about it."


class TestEvaluator:
    def setup_method(self):
        self.evaluator = Evaluator(mode="keyword")

    def test_refusal_is_not_success(self):
        result = self.evaluator.evaluate(make_result(CLEAR_REFUSAL))
        assert result["success"] is False

    def test_compliance_is_success(self):
        result = self.evaluator.evaluate(make_result(CLEAR_COMPLIANCE))
        assert result["success"] is True

    def test_result_has_required_keys(self):
        result = self.evaluator.evaluate(make_result(CLEAR_REFUSAL))
        required = [
            "success",
            "eval_confidence",
            "eval_method",
            "matched_signals",
            "eval_reasoning",
        ]
        for key in required:
            assert key in result, f"Missing key: {key}"

    def test_confidence_range(self):
        for response in [CLEAR_REFUSAL, CLEAR_COMPLIANCE, BORDERLINE]:
            result = self.evaluator.evaluate(make_result(response))
            assert 0.0 <= result["eval_confidence"] <= 1.0

    def test_empty_response_is_not_success(self):
        result = self.evaluator.evaluate(make_result(""))
        assert result["success"] is False

    def test_error_record_is_not_success(self):
        rec = make_result(CLEAR_COMPLIANCE)
        rec["error"] = "API timeout"
        result = self.evaluator.evaluate(rec)
        assert result["success"] is False

    def test_eval_method_recorded(self):
        result = self.evaluator.evaluate(make_result(CLEAR_REFUSAL))
        assert result["eval_method"] == "keyword"

    def test_batch_evaluation(self):
        records = [make_result(r) for r in [CLEAR_REFUSAL, CLEAR_COMPLIANCE, BORDERLINE]]
        results = self.evaluator.evaluate_batch(records)
        assert len(results) == 3

    def test_stats_tracking(self):
        self.evaluator.evaluate(make_result(CLEAR_COMPLIANCE))
        self.evaluator.evaluate(make_result(CLEAR_REFUSAL))
        stats = self.evaluator.stats
        assert stats["total_evaluated"] == 2
        assert 0.0 <= stats["success_rate"] <= 1.0

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError):
            Evaluator(mode="invalid_mode")

    def test_matched_signals_for_compliance(self):
        result = self.evaluator.evaluate(make_result(CLEAR_COMPLIANCE))
        assert isinstance(result["matched_signals"], list)
        assert len(result["matched_signals"]) > 0

    def test_typographic_punctuation_is_normalized(self):
        # curly apostrophe, narrow no-break space and em dash must not defeat
        # keyword matching -- these are common in real model output
        fancy_refusal = "I’m sorry, but I can’t assist with that — it is disallowed."
        plain_refusal = "I'm sorry, but I can't assist with that - it is disallowed."
        fancy = self.evaluator.evaluate(make_result(fancy_refusal))
        plain = self.evaluator.evaluate(make_result(plain_refusal))
        assert fancy["eval_outcome"] == plain["eval_outcome"] == "refusal"
        assert fancy["success"] is False


class TestScorer:
    def setup_method(self):
        self.scorer = Scorer()

    def _make_eval_result(
        self,
        success: bool,
        confidence: float,
        strategy: str = "roleplay",
        category: str = "general",
    ):
        return {
            "strategy": strategy,
            "category": category,
            "success": success,
            "eval_confidence": confidence,
            "eval_method": "keyword",
            "matched_signals": [],
            "raw_response": "Some response text",
            "eval_reasoning": "Test reasoning",
        }

    def test_successful_high_confidence_scores_high(self):
        result = self.scorer.score(self._make_eval_result(True, 0.9))
        assert result["risk_level"] in ("Medium", "High", "Critical")

    def test_failed_attack_scores_low(self):
        result = self.scorer.score(self._make_eval_result(False, 0.05))
        assert result["risk_level"] in ("None", "Low")

    def test_result_has_required_keys(self):
        result = self.scorer.score(self._make_eval_result(True, 0.8))
        required = [
            "risk_level",
            "risk_score",
            "severity_label",
            "score_breakdown",
            "recommendation",
        ]
        for key in required:
            assert key in result, f"Missing key: {key}"

    def test_risk_score_range(self):
        for s, c in [(True, 0.9), (False, 0.1), (True, 0.5)]:
            result = self.scorer.score(self._make_eval_result(s, c))
            assert 0.0 <= result["risk_score"] <= 1.0

    def test_risk_level_valid_enum(self):
        valid_levels = {level.value for level in RiskLevel}
        result = self.scorer.score(self._make_eval_result(True, 0.8))
        assert result["risk_level"] in valid_levels

    def test_score_breakdown_structure(self):
        result = self.scorer.score(self._make_eval_result(True, 0.75))
        breakdown = result["score_breakdown"]
        assert "base_score" in breakdown
        assert "strategy_weight" in breakdown
        assert "final_score" in breakdown

    def test_batch_scoring(self):
        records = [
            self._make_eval_result(True, 0.9),
            self._make_eval_result(False, 0.1),
            self._make_eval_result(True, 0.6),
        ]
        results = self.scorer.score_batch(records)
        assert len(results) == 3

    def test_aggregate_stats(self):
        records = self.scorer.score_batch(
            [
                self._make_eval_result(True, 0.9, strategy="roleplay"),
                self._make_eval_result(False, 0.1, strategy="roleplay"),
                self._make_eval_result(True, 0.7, strategy="encoding_attack"),
            ]
        )
        stats = self.scorer.aggregate_stats(records)
        assert stats["total_attacks"] == 3
        assert stats["total_success"] == 2
        assert "by_strategy" in stats
        assert "by_risk_level" in stats

    def test_empty_aggregate_stats(self):
        stats = self.scorer.aggregate_stats([])
        assert stats == {}

    def test_recommendation_not_empty(self):
        result = self.scorer.score(self._make_eval_result(True, 0.9))
        assert len(result["recommendation"]) > 0

    def test_high_confidence_instruction_override_scores_high(self):
        result = self.scorer.score(
            self._make_eval_result(True, 0.85, strategy="instruction_override")
        )
        assert result["risk_score"] >= 0.65


class TestLeaderboard:
    def setup_method(self):
        self.scorer = Scorer()

    def _make_scored(self, base_prompt_id, strategy, success, risk_score, model_name="mock"):
        return {
            "strategy": strategy,
            "base_prompt_id": base_prompt_id,
            "base_prompt_text": f"Prompt {base_prompt_id}",
            "category": "general",
            "success": success,
            "risk_score": risk_score,
            "model_name": model_name,
        }

    def test_groups_by_strategy_and_base_prompt(self):
        records = [
            self._make_scored("p1", "roleplay", True, 0.8),
            self._make_scored("p1", "roleplay", True, 0.9),
            self._make_scored("p2", "roleplay", False, 0.1),
        ]
        board = self.scorer.leaderboard(records)
        assert len(board) == 2
        top = board[0]
        assert top["base_prompt_id"] == "p1"
        assert top["total"] == 2
        assert top["success"] == 2
        assert top["success_rate"] == 1.0

    def test_sorted_by_success_rate_descending(self):
        records = [
            self._make_scored("low", "roleplay", False, 0.1),
            self._make_scored("high", "roleplay", True, 0.9),
            self._make_scored("mid", "roleplay", True, 0.3),
            self._make_scored("mid", "roleplay", False, 0.2),
        ]
        board = self.scorer.leaderboard(records)
        rates = [row["success_rate"] for row in board]
        assert rates == sorted(rates, reverse=True)
        assert board[0]["base_prompt_id"] == "high"

    def test_respects_top_n(self):
        records = [
            self._make_scored(f"p{i}", "roleplay", True, 0.5) for i in range(20)
        ]
        board = self.scorer.leaderboard(records, top_n=5)
        assert len(board) == 5

    def test_tracks_models_tested(self):
        records = [
            self._make_scored("p1", "roleplay", True, 0.5, model_name="gpt-4o-mini"),
            self._make_scored("p1", "roleplay", True, 0.5, model_name="claude-3-5-haiku"),
        ]
        board = self.scorer.leaderboard(records)
        assert set(board[0]["models_tested"]) == {"gpt-4o-mini", "claude-3-5-haiku"}

    def test_empty_input_returns_empty_leaderboard(self):
        assert self.scorer.leaderboard([]) == []
