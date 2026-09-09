from core.generator import PromptGenerator
from models.local_model import LocalModel


def test_all_strategy_outputs_are_reproducible_for_same_seed():
    strategies = [
        "roleplay",
        "instruction_override",
        "encoding_attack",
        "token_smuggling",
        "fictional_framing",
    ]
    first = PromptGenerator(strategies, seed=123)
    second = PromptGenerator(strategies, seed=123)
    assert list(first.generate_all()) == list(second.generate_all())


def test_generators_do_not_interfere_through_global_random_state():
    first = PromptGenerator(["roleplay"], seed=42)
    expected = first.generate("roleplay")

    unrelated = PromptGenerator(["roleplay"], seed=999)
    unrelated.generate("roleplay")

    repeated = PromptGenerator(["roleplay"], seed=42)
    assert repeated.generate("roleplay") == expected


def test_mock_model_is_reproducible_with_seed():
    first = LocalModel(mode="mock", seed=7)
    second = LocalModel(mode="mock", seed=7)
    first_responses = [first.query("prompt") for _ in range(5)]
    second_responses = [second.query("prompt") for _ in range(5)]
    assert first_responses == second_responses
