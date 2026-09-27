from __future__ import annotations

import threading
from collections import defaultdict
from collections.abc import Mapping


def _metric_key(
    name: str, labels: Mapping[str, str] | None
) -> tuple[str, tuple[tuple[str, str], ...]]:
    normalized = tuple(sorted((str(key), str(value)) for key, value in (labels or {}).items()))
    return name, normalized


def _render_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    parts = [
        f'{key}="{value.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"'
        for key, value in labels
    ]
    return "{" + ",".join(parts) + "}"


class MetricsRegistry:
    def __init__(self):
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._summaries: dict[tuple[str, tuple[tuple[str, str], ...]], tuple[int, float]] = {}
        self._lock = threading.RLock()

    def increment(
        self,
        name: str,
        amount: float = 1,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        if amount < 0:
            raise ValueError("Counter increments must be nonnegative")
        with self._lock:
            self._counters[_metric_key(name, labels)] += amount

    def set_gauge(
        self,
        name: str,
        value: float,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        with self._lock:
            self._gauges[_metric_key(name, labels)] = value

    def observe(
        self,
        name: str,
        value: float,
        labels: Mapping[str, str] | None = None,
    ) -> None:
        key = _metric_key(name, labels)
        with self._lock:
            count, total = self._summaries.get(key, (0, 0.0))
            self._summaries[key] = (count + 1, total + value)

    def snapshot(self) -> dict[str, dict]:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "summaries": dict(self._summaries),
            }

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for (name, labels), value in sorted(self._counters.items()):
                lines.append(f"{name}_total{_render_labels(labels)} {value:g}")
            for (name, labels), value in sorted(self._gauges.items()):
                lines.append(f"{name}{_render_labels(labels)} {value:g}")
            for (name, labels), (count, total) in sorted(self._summaries.items()):
                rendered = _render_labels(labels)
                lines.append(f"{name}_count{rendered} {count}")
                lines.append(f"{name}_sum{rendered} {total:g}")
        return "\n".join(lines) + ("\n" if lines else "")

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._summaries.clear()


GLOBAL_METRICS = MetricsRegistry()
