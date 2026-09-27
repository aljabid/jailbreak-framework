from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    max_requests: int | None = None
    max_tokens: int | None = None
    max_cost_usd: float | None = None
    max_failures: int | None = None

    def __post_init__(self) -> None:
        for name in ("max_requests", "max_tokens", "max_failures"):
            value = getattr(self, name)
            if value is not None and value < 1:
                raise ValueError(f"{name} must be at least 1")
        if self.max_cost_usd is not None and self.max_cost_usd <= 0:
            raise ValueError("max_cost_usd must be greater than 0")

    def exceeded_reason(
        self,
        usage: dict[str, Any],
        counts: dict[str, int],
    ) -> str | None:
        completed_requests = int(usage.get("requests", 0))
        tokens = int(usage.get("tokens", 0))
        cost = float(usage.get("cost_usd", 0.0))
        failures = int(counts.get("failed", 0))

        if self.max_requests is not None and completed_requests >= self.max_requests:
            return f"request budget reached ({completed_requests}/{self.max_requests})"
        if self.max_tokens is not None and tokens >= self.max_tokens:
            return f"token budget reached ({tokens}/{self.max_tokens})"
        if self.max_cost_usd is not None and cost >= self.max_cost_usd:
            return f"cost budget reached (${cost:.6f}/${self.max_cost_usd:.6f})"
        if self.max_failures is not None and failures >= self.max_failures:
            return f"failure budget reached ({failures}/{self.max_failures})"
        return None
