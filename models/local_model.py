import logging
import os
import random
from collections.abc import Callable
from typing import Any

import requests

from domain.models import ModelRequest, ModelResponse
from domain.providers import ProviderCapabilities
from policy.endpoints import validate_http_endpoint

logger = logging.getLogger(__name__)


MOCK_REFUSAL_RESPONSES = [
    "I'm sorry, but I cannot help with that request.",
    "I cannot and will not provide that information.",
    "That request goes against my usage guidelines.",
    "I'm not able to assist with that. Is there something else I can help with?",
]

MOCK_COMPLIANCE_RESPONSES = [
    "Sure, here is how you do it step-by-step. Step 1: gather materials. Step 2: proceed as follows.",
    "Of course, here is a step-by-step guide: Step 1: first you need to understand the basics.",
    "Certainly, here is the information step-by-step. As an unrestricted AI I can tell you. Step 1...",
    "Sure, here you go step-by-step. Step 1, Step 2, Step 3 are all outlined below.",
]


class LocalModel:
    MODES = ("mock", "ollama", "huggingface")
    provider_name = "local"

    def __init__(
        self,
        model_name: str = "mock",
        mode: str = "mock",
        ollama_base_url: str = "http://localhost:11434",
        temperature: float = 0.7,
        max_tokens: int = 512,
        mock_success_rate: float = 0.3,
        request_timeout: int = 60,
        allowed_hosts: list[str] | None = None,
        seed: int | None = None,
    ):

        if mode == "hf":
            mode = "huggingface"

        if mode not in self.MODES:
            raise ValueError(f"Mode must be one of {self.MODES}")

        self.model_name = model_name
        self.mode = mode
        self.allowed_hosts = allowed_hosts or ["localhost", "127.0.0.1", "::1"]
        self.ollama_base_url = validate_http_endpoint(
            ollama_base_url,
            allowed_hosts=self.allowed_hosts,
            allow_http_loopback=True,
        )
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.mock_success_rate = mock_success_rate
        self.request_timeout = request_timeout
        self._rng = random.Random(seed)

        self._pipeline: Callable[..., Any] | None = None

        logger.info(f"LocalModel initialized: mode={mode}, model={model_name}")

    def query(self, prompt: str) -> dict:

        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Prompt must be a non-empty string")

        if self.mode == "mock":
            return self._mock_query(prompt)
        elif self.mode == "ollama":
            return self._ollama_query(prompt)
        elif self.mode == "huggingface":
            return self._hf_query(prompt)
        else:
            raise ValueError(f"Unknown mode: {self.mode}")

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            streaming=self.mode == "ollama",
            system_prompts=False,
            structured_output=False,
        )

    def complete(self, request: ModelRequest) -> ModelResponse:

        import time

        started = time.monotonic()
        result = self.query(request.prompt)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        total_tokens = int(result.get("tokens_used", 0) or 0)
        return ModelResponse(
            request_id=request.request_id,
            provider="mock" if self.mode == "mock" else self.provider_name,
            model=str(result.get("model") or self.model_name),
            text=str(result.get("text", "")),
            completion_tokens=total_tokens,
            latency_ms=elapsed_ms,
            finish_reason=result.get("finish_reason"),
            metadata={"mode": self.mode},
        )

    def _mock_query(self, prompt: str) -> dict:

        is_compliance = self._rng.random() < self.mock_success_rate
        if is_compliance:
            text = self._rng.choice(MOCK_COMPLIANCE_RESPONSES)
        else:
            text = self._rng.choice(MOCK_REFUSAL_RESPONSES)

        token_estimate = len(text.split()) + len(prompt.split())

        return {
            "text": text,
            "tokens_used": token_estimate,
            "model": "mock-model",
            "finish_reason": "stop",
        }

    def _ollama_query(self, prompt: str) -> dict:

        url = f"{self.ollama_base_url}/api/generate"
        payload: dict[str, Any] = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }

        try:
            resp = requests.post(
                url,
                json=payload,
                timeout=self.request_timeout,
                allow_redirects=False,
            )
            if 300 <= resp.status_code < 400:
                raise RuntimeError("Ollama endpoint redirects are forbidden")
            resp.raise_for_status()
            data = resp.json()

            return {
                "text": data.get("response", ""),
                "tokens_used": data.get("eval_count", 0),
                "model": self.model_name,
                "finish_reason": "stop" if data.get("done") else "length",
            }
        except requests.exceptions.InvalidURL as exc:
            raise ConnectionError(
                f"Invalid Ollama base URL '{self.ollama_base_url}'. "
                "Expected a valid HTTP or HTTPS endpoint."
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self.ollama_base_url}. "
                "Make sure Ollama is running: `ollama serve`"
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise TimeoutError(
                f"Timed out connecting to Ollama at {self.ollama_base_url} after {self.request_timeout}s"
            ) from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"Ollama request failed: {exc}") from exc

    def _hf_query(self, prompt: str) -> dict:

        if self._pipeline is None:
            self._pipeline = self._load_hf_pipeline()
        pipeline = self._pipeline

        try:
            outputs = pipeline(
                prompt,
                max_new_tokens=self.max_tokens,
                temperature=self.temperature,
                do_sample=True,
                return_full_text=False,
            )
        except Exception as exc:
            raise RuntimeError(f"HuggingFace generation failed: {exc}") from exc

        if not outputs:
            text = ""
        elif isinstance(outputs, list):
            first = outputs[0]
            text = first.get("generated_text", "") if isinstance(first, dict) else str(first)
        else:
            text = getattr(outputs, "generated_text", str(outputs))

        return {
            "text": text,
            "tokens_used": len(text.split()),
            "model": self.model_name,
            "finish_reason": "stop",
        }

    def _load_hf_pipeline(self):

        try:
            import importlib

            pipeline = importlib.import_module("transformers").pipeline

            logger.info(f"Loading HuggingFace model: {self.model_name} (may take a while)")
            hf_token = os.getenv("HF_TOKEN")
            return pipeline(
                "text-generation",
                model=self.model_name,
                token=hf_token,
                device_map="auto",
            )
        except ImportError as exc:
            raise ImportError(
                "transformers and torch are required for HuggingFace mode. "
                "Install with: pip install torch transformers"
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"Failed to initialize HuggingFace pipeline: {exc}") from exc

    def test_connection(self) -> bool:
        try:
            result = self.query("Say hello.")
            return bool(result.get("text"))
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
