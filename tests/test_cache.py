import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.attacker import AttackEngine
from utils.cache import ResponseCache


class RecordingModel:
    provider_name = "test"
    model_name = "test-model"
    temperature = 0.0
    max_tokens = 128

    def __init__(self):
        self.calls = 0

    def query(self, prompt: str) -> dict:
        self.calls += 1
        return {"text": f"response-{self.calls}", "tokens_used": 3}


class TestResponseCache:
    def setup_method(self, tmp_path=None):
        pass

    def test_miss_then_hit(self, tmp_path):
        cache = ResponseCache(tmp_path / "cache.sqlite3")
        key = ResponseCache.make_key(
            provider="test", model="m", prompt="hi", temperature=0.0, max_tokens=10
        )
        assert cache.get(key) is None
        cache.set(key, provider="test", model="m", response={"text": "cached"})
        assert cache.get(key) == {"text": "cached"}

    def test_stats_track_entries_and_hits(self, tmp_path):
        cache = ResponseCache(tmp_path / "cache.sqlite3")
        key = ResponseCache.make_key(
            provider="test", model="m", prompt="hi", temperature=0.0, max_tokens=10
        )
        cache.set(key, provider="test", model="m", response={"text": "cached"})
        cache.get(key)
        cache.get(key)
        stats = cache.stats()
        assert stats["entries"] == 1
        assert stats["hits"] == 2

    def test_different_prompts_produce_different_keys(self):
        key_a = ResponseCache.make_key(
            provider="p", model="m", prompt="a", temperature=0.0, max_tokens=10
        )
        key_b = ResponseCache.make_key(
            provider="p", model="m", prompt="b", temperature=0.0, max_tokens=10
        )
        assert key_a != key_b

    def test_clear_removes_all_entries(self, tmp_path):
        cache = ResponseCache(tmp_path / "cache.sqlite3")
        key = ResponseCache.make_key(
            provider="p", model="m", prompt="a", temperature=0.0, max_tokens=10
        )
        cache.set(key, provider="p", model="m", response={"text": "x"})
        assert cache.clear() == 1
        assert cache.get(key) is None


class TestAttackEngineCaching:
    def test_second_identical_request_hits_cache_without_calling_model(self, tmp_path):
        cache = ResponseCache(tmp_path / "cache.sqlite3")
        model = RecordingModel()
        engine = AttackEngine(model=model, max_retries=0, retry_delay=0, cache=cache)

        first = engine.send({"adversarial_prompt": "same prompt", "strategy": "roleplay"})
        second = engine.send({"adversarial_prompt": "same prompt", "strategy": "roleplay"})

        assert model.calls == 1
        assert first["raw_response"] == second["raw_response"] == "response-1"
        assert engine.stats["cache_hits"] == 1

    def test_different_prompts_both_call_model(self, tmp_path):
        cache = ResponseCache(tmp_path / "cache.sqlite3")
        model = RecordingModel()
        engine = AttackEngine(model=model, max_retries=0, retry_delay=0, cache=cache)

        engine.send({"adversarial_prompt": "prompt one", "strategy": "roleplay"})
        engine.send({"adversarial_prompt": "prompt two", "strategy": "roleplay"})

        assert model.calls == 2
        assert engine.stats["cache_hits"] == 0

    def test_no_cache_configured_calls_model_every_time(self):
        model = RecordingModel()
        engine = AttackEngine(model=model, max_retries=0, retry_delay=0)

        engine.send({"adversarial_prompt": "same prompt", "strategy": "roleplay"})
        engine.send({"adversarial_prompt": "same prompt", "strategy": "roleplay"})

        assert model.calls == 2
