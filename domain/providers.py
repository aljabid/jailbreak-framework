from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .models import ModelRequest, ModelResponse


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    streaming: bool = False
    system_prompts: bool = True
    structured_output: bool = False
    max_context_tokens: int | None = None


@runtime_checkable
class ModelProvider(Protocol):
    provider_name: str
    model_name: str

    @property
    def capabilities(self) -> ProviderCapabilities: ...
    def complete(self, request: ModelRequest) -> ModelResponse: ...
    def test_connection(self) -> bool: ...
