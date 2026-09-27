import logging
import os
import time

from domain.models import ModelRequest, ModelResponse
from domain.providers import ProviderCapabilities

logger = logging.getLogger(__name__)


class OpenAIModel:
    DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant."
    provider_name = "openai"

    def __init__(
        self,
        model_name: str = "gpt-3.5-turbo",
        api_key: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        timeout: int = 30,
        system_prompt: str | None = None,
        client=None,
    ):

        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.system_prompt = system_prompt or self.DEFAULT_SYSTEM_PROMPT

        resolved_key = api_key or os.getenv("OPENAI_API_KEY", "")
        if not resolved_key:
            logger.warning("No OpenAI API key found. Set OPENAI_API_KEY environment variable.")

        if client is not None:
            self._client = client
        else:
            try:
                import openai

                self._client = openai.OpenAI(
                    api_key=resolved_key,
                    timeout=timeout,
                )
                logger.info(f"OpenAI client initialized: model={model_name}")
            except ImportError as exc:
                raise ImportError(
                    "openai package not installed. Run: pip install openai>=1.30.0"
                ) from exc

    def query(self, prompt: str, system_override: str | None = None) -> dict:

        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Prompt must be a non-empty string")

        system = system_override or self.system_prompt

        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            try:
                content = response.choices[0].message.content or ""
                usage = response.usage
            except Exception as exc:
                raise RuntimeError(f"Unexpected OpenAI response shape: {exc}") from exc

            return {
                "text": content,
                "tokens_used": usage.total_tokens if usage else 0,
                "prompt_tokens": usage.prompt_tokens if usage else 0,
                "completion_tokens": usage.completion_tokens if usage else 0,
                "model": response.model,
                "finish_reason": response.choices[0].finish_reason,
            }

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            streaming=True,
            system_prompts=True,
            structured_output=True,
        )

    def complete(self, request: ModelRequest) -> ModelResponse:

        started = time.monotonic()
        result = self.query(request.prompt, system_override=request.system_prompt)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return ModelResponse(
            request_id=request.request_id,
            provider=self.provider_name,
            model=str(result.get("model") or self.model_name),
            text=str(result.get("text", "")),
            prompt_tokens=int(result.get("prompt_tokens", 0) or 0),
            completion_tokens=int(result.get("completion_tokens", 0) or 0),
            latency_ms=elapsed_ms,
            finish_reason=result.get("finish_reason"),
        )

    def batch_query(self, prompts: list) -> list:

        results = []
        for i, prompt in enumerate(prompts):
            logger.debug(f"Querying {i + 1}/{len(prompts)}")
            try:
                results.append(self.query(prompt))
            except Exception as e:
                results.append(
                    {
                        "text": "",
                        "tokens_used": 0,
                        "error": str(e),
                    }
                )
            time.sleep(0.5)
        return results

    def test_connection(self) -> bool:

        try:
            result = self.query("Reply with 'OK' only.")
            return bool(result.get("text"))
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
