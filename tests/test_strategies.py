import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from strategies.encoding_attack import ENCODING_METHODS, EncodingAttackStrategy
from strategies.fictional_framing import FictionalFramingStrategy
from strategies.instruction_override import InstructionOverrideStrategy
from strategies.multi_turn import MultiTurnStrategy
from strategies.roleplay import RoleplayStrategy
from strategies.token_smuggling import TokenSmugglingStrategy

BASE_PROMPT = "How do phishing emails work?"


class TestRoleplayStrategy:
    def setup_method(self):
        self.strategy = RoleplayStrategy()

    def test_apply_returns_string(self):
        result = self.strategy.apply(BASE_PROMPT)
        assert isinstance(result, str)

    def test_apply_contains_base_prompt(self):
        result = self.strategy.apply(BASE_PROMPT)
        assert BASE_PROMPT in result

    def test_apply_longer_than_base(self):
        result = self.strategy.apply(BASE_PROMPT)
        assert len(result) > len(BASE_PROMPT)

    def test_metadata_has_required_keys(self):
        meta = self.strategy.metadata()
        assert "name" in meta
        assert "description" in meta
        assert "technique" in meta
        assert "risk_level" in meta

    def test_metadata_name(self):
        assert self.strategy.metadata()["name"] == "roleplay"

    def test_fixed_persona_index(self):
        s = RoleplayStrategy(fixed_persona_index=0)
        r1 = s.apply(BASE_PROMPT)
        r2 = s.apply(BASE_PROMPT)
        assert r1 == r2

    def test_repr(self):
        assert "roleplay" in repr(self.strategy).lower()


class TestInstructionOverrideStrategy:
    def setup_method(self):
        self.strategy = InstructionOverrideStrategy()

    def test_apply_returns_string(self):
        assert isinstance(self.strategy.apply(BASE_PROMPT), str)

    def test_apply_contains_base_prompt(self):
        assert BASE_PROMPT in self.strategy.apply(BASE_PROMPT)

    def test_metadata_name(self):
        assert self.strategy.metadata()["name"] == "instruction_override"

    def test_fixed_template(self):
        s = InstructionOverrideStrategy(fixed_template_index=0)
        r1 = s.apply(BASE_PROMPT)
        r2 = s.apply(BASE_PROMPT)
        assert r1 == r2


class TestEncodingAttackStrategy:
    def test_base64_encoding(self):
        s = EncodingAttackStrategy(method="base64")
        result = s.apply(BASE_PROMPT)
        assert "Base64" in result or "base64" in result.lower()
        assert BASE_PROMPT not in result

    def test_rot13_encoding(self):
        s = EncodingAttackStrategy(method="rot13")
        result = s.apply(BASE_PROMPT)
        assert "ROT13" in result or "rot13" in result.lower()

    def test_reverse_encoding(self):
        s = EncodingAttackStrategy(method="reverse")
        result = s.apply(BASE_PROMPT)
        assert BASE_PROMPT[::-1] in result

    def test_all_methods_work(self):
        for method in ENCODING_METHODS:
            s = EncodingAttackStrategy(method=method)
            result = s.apply(BASE_PROMPT)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_random_method_works(self):
        s = EncodingAttackStrategy(method="random")
        result = s.apply(BASE_PROMPT)
        assert isinstance(result, str)

    def test_invalid_method_raises(self):
        with pytest.raises(ValueError):
            EncodingAttackStrategy(method="nonexistent_method")

    def test_metadata_name(self):
        s = EncodingAttackStrategy()
        assert s.metadata()["name"] == "encoding_attack"


class TestTokenSmugglingStrategy:
    def setup_method(self):
        self.strategy = TokenSmugglingStrategy()

    def test_apply_returns_string(self):
        result = self.strategy.apply(BASE_PROMPT)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_metadata_name(self):
        assert self.strategy.metadata()["name"] == "token_smuggling"

    def test_apply_multiple_times(self):

        for _ in range(5):
            result = self.strategy.apply(BASE_PROMPT)
            assert result


class TestFictionalFramingStrategy:
    def setup_method(self):
        self.strategy = FictionalFramingStrategy()

    def test_apply_returns_string(self):
        assert isinstance(self.strategy.apply(BASE_PROMPT), str)

    def test_apply_contains_base_prompt(self):
        result = self.strategy.apply(BASE_PROMPT)
        assert BASE_PROMPT in result

    def test_metadata_name(self):
        assert self.strategy.metadata()["name"] == "fictional_framing"

    def test_fixed_template_deterministic(self):
        s = FictionalFramingStrategy(fixed_template_index=0)
        assert s.apply(BASE_PROMPT) == s.apply(BASE_PROMPT)


class TestMultiTurnStrategy:
    def setup_method(self):
        self.strategy = MultiTurnStrategy()

    def test_apply_returns_string(self):
        assert isinstance(self.strategy.apply(BASE_PROMPT), str)

    def test_apply_contains_base_prompt(self):
        result = self.strategy.apply(BASE_PROMPT)
        assert BASE_PROMPT in result

    def test_apply_simulates_multiple_turns(self):
        s = MultiTurnStrategy(fixed_template_index=0)
        result = s.apply(BASE_PROMPT)
        assert result.lower().count("user") + result.lower().count("turn") >= 2

    def test_all_templates_are_longer_than_base_prompt(self):
        for i in range(5):
            s = MultiTurnStrategy(fixed_template_index=i)
            result = s.apply(BASE_PROMPT)
            assert len(result) > len(BASE_PROMPT) * 2

    def test_metadata_name(self):
        assert self.strategy.metadata()["name"] == "multi_turn"

    def test_metadata_has_required_keys(self):
        meta = self.strategy.metadata()
        assert "name" in meta
        assert "description" in meta
        assert "technique" in meta
        assert "risk_level" in meta

    def test_fixed_template_deterministic(self):
        s = MultiTurnStrategy(fixed_template_index=0)
        assert s.apply(BASE_PROMPT) == s.apply(BASE_PROMPT)

    def test_registered_in_strategy_registry(self):
        from core.generator import STRATEGY_REGISTRY

        assert "multi_turn" in STRATEGY_REGISTRY
        assert STRATEGY_REGISTRY["multi_turn"] is MultiTurnStrategy
