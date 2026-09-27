from types import SimpleNamespace

from core.attacker import AttackEngine, ErrorType, categorize_error
from domain.models import ModelRequest
from domain.providers import ModelProvider
from models.anthropic_model import AnthropicModel
from models.openai_model import OpenAIModel


class FakeCompletions:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="contract response"),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(
                total_tokens=12,
                prompt_tokens=5,
                completion_tokens=7,
            ),
            model="contract-model",
        )


def test_openai_adapter_implements_typed_provider_contract():
    completions = FakeCompletions()
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=completions,
        )
    )
    provider = OpenAIModel(
        model_name="contract-model",
        api_key="test-only-key",
        client=client,
    )
    assert isinstance(provider, ModelProvider)
    response = provider.complete(
        ModelRequest(
            prompt="test prompt",
            system_prompt="test system",
        )
    )
    assert response.text == "contract response"
    assert response.prompt_tokens == 5
    assert response.completion_tokens == 7
    assert completions.kwargs["messages"][0]["content"] == "test system"


class FakeMessages:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="contract response")],
            usage=SimpleNamespace(input_tokens=5, output_tokens=7),
            model="contract-model",
            stop_reason="end_turn",
        )


def test_anthropic_adapter_implements_typed_provider_contract():
    messages = FakeMessages()
    client = SimpleNamespace(messages=messages)
    provider = AnthropicModel(
        model_name="contract-model",
        api_key="test-only-key",
        client=client,
    )
    assert isinstance(provider, ModelProvider)
    response = provider.complete(
        ModelRequest(
            prompt="test prompt",
            system_prompt="test system",
        )
    )
    assert response.text == "contract response"
    assert response.prompt_tokens == 5
    assert response.completion_tokens == 7
    assert messages.kwargs["system"] == "test system"
    assert messages.kwargs["messages"][0]["content"] == "test prompt"


class HTTPError(Exception):
    def __init__(self, status_code, retry_after=None):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code
        self.response = SimpleNamespace(
            status_code=status_code,
            headers=({"Retry-After": str(retry_after)} if retry_after is not None else {}),
        )


def test_http_error_classification():
    assert categorize_error(HTTPError(429)) == ErrorType.RATE_LIMIT
    assert categorize_error(HTTPError(401)) == ErrorType.AUTH
    assert categorize_error(HTTPError(400)) == ErrorType.MODEL
    assert categorize_error(HTTPError(503)) == ErrorType.NETWORK


def test_retry_after_is_honored_and_bounded():
    waits = []

    class Provider:
        model_name = "test"
        provider_name = "test"

        def __init__(self):
            self.calls = 0

        def query(self, _prompt):
            self.calls += 1
            if self.calls == 1:
                raise HTTPError(429, retry_after=120)
            return {"text": "ok", "tokens_used": 1}

    provider = Provider()
    engine = AttackEngine(
        provider,
        max_retries=1,
        retry_delay=1,
        max_retry_delay=5,
        retry_jitter=0,
        sleeper=waits.append,
    )
    result = engine.send({"adversarial_prompt": "test"})
    assert result["raw_response"] == "ok"
    assert waits == [5]
