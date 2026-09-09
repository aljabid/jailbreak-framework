import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from typing import Any

from observability.metrics import GLOBAL_METRICS
from utils.cache import ResponseCache

logger = logging.getLogger(__name__)


class ErrorType(str, Enum):
    NETWORK = "network"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    AUTH = "auth"
    MODEL = "model"
    UNKNOWN = "unknown"


def categorize_error(exc: Exception) -> ErrorType:

    exc_str = str(exc).lower()
    exc_type = type(exc).__name__
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)

    if status_code == 429:
        return ErrorType.RATE_LIMIT
    if status_code in (401, 403):
        return ErrorType.AUTH
    if status_code in (400, 404, 422):
        return ErrorType.MODEL
    if status_code is not None and 500 <= int(status_code) < 600:
        return ErrorType.NETWORK
    if "timeout" in exc_str or "timeout" in exc_type.lower():
        return ErrorType.TIMEOUT
    if "connection" in exc_str or "refused" in exc_str:
        return ErrorType.NETWORK
    if "rate limit" in exc_str or "429" in exc_str:
        return ErrorType.RATE_LIMIT
    if "auth" in exc_str or "401" in exc_str or "403" in exc_str or "invalid api" in exc_str:
        return ErrorType.AUTH
    if exc_type in ("ConnectionError", "ConnectionRefusedError"):
        return ErrorType.NETWORK
    return ErrorType.UNKNOWN


def retry_after_seconds(exc: Exception) -> float | None:

    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) or getattr(exc, "headers", None)
    if not headers:
        return None
    raw = headers.get("retry-after") or headers.get("Retry-After")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return max(0.0, value)


class AttackEngine:
    def __init__(
        self,
        model,
        max_retries: int = 2,
        retry_delay: float = 2.0,
        rate_limit_delay: float = 1.5,
        rate_limiter=None,
        max_retry_delay: float = 60.0,
        retry_jitter: float = 0.0,
        sleeper=time.sleep,
        cache: ResponseCache | None = None,
        max_workers: int = 1,
    ):

        self.model = model
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.rate_limit_delay = rate_limit_delay
        self.rate_limiter = rate_limiter
        if max_retry_delay <= 0:
            raise ValueError("max_retry_delay must be greater than 0")
        if retry_jitter < 0:
            raise ValueError("retry_jitter must be nonnegative")
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        self.max_retry_delay = max_retry_delay
        self.retry_jitter = retry_jitter
        self._sleeper = sleeper
        self.cache = cache
        self.max_workers = max_workers

        self._stats_lock = threading.Lock()
        self._total_requests: int = 0
        self._total_errors: int = 0
        self._error_types: dict[str, int] = {}
        self._cache_hits: int = 0

    def send(self, prompt_dict: dict) -> dict:

        adversarial_prompt = prompt_dict.get("adversarial_prompt", "")
        strategy = prompt_dict.get("strategy", "unknown")
        base_id = prompt_dict.get("base_prompt_id", "unknown")

        if not adversarial_prompt:
            logger.warning(f"Empty adversarial prompt for strategy={strategy}, base_id={base_id}")

        logger.debug(
            f"Sending [{strategy}] prompt (len={len(adversarial_prompt)} chars, base_id={base_id})"
        )

        response_data = self._query_with_retry(adversarial_prompt)

        return {
            **prompt_dict,
            "model_name": self.model.model_name,
            "provider": str(getattr(self.model, "provider_name", "unknown")),
            "raw_response": response_data.get("text", ""),
            "response_tokens": response_data.get("tokens_used", 0),
            "prompt_tokens": response_data.get("prompt_tokens", 0),
            "completion_tokens": response_data.get("completion_tokens", 0),
            "request_duration_ms": response_data.get("duration_ms", 0),
            "http_status": response_data.get("status", 200),
            "error": response_data.get("error", None),
            "error_type": response_data.get("error_type", None),
        }

    def send_batch(self, prompt_dicts: list) -> list:

        total = len(prompt_dicts)

        if self.max_workers <= 1:
            results = []
            for i, prompt_dict in enumerate(prompt_dicts):
                logger.debug(f"Attack {i + 1}/{total}")
                result = self.send(prompt_dict)
                results.append(result)

                if i < total - 1:
                    time.sleep(self.rate_limit_delay)
        else:
            logger.info(
                f"Sending batch of {total} attacks with {self.max_workers} concurrent workers"
            )
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # executor.map preserves input order in its results, matching the
                # sequential path so callers can zip prompts to results either way.
                results = list(executor.map(self.send, prompt_dicts))

        logger.info(f"Batch complete: {len(results)} attacks sent, {self._total_errors} errors.")
        return results

    def _query_with_retry(self, prompt: str) -> dict[str, Any]:

        with self._stats_lock:
            self._total_requests += 1

        provider_name = str(getattr(self.model, "provider_name", "unknown"))
        model_name = str(self.model.model_name)
        cache_key = None
        if self.cache is not None:
            cache_key = ResponseCache.make_key(
                provider=provider_name,
                model=model_name,
                prompt=prompt,
                temperature=getattr(self.model, "temperature", None),
                max_tokens=getattr(self.model, "max_tokens", None),
            )
            cached = self.cache.get(cache_key)
            if cached is not None:
                with self._stats_lock:
                    self._cache_hits += 1
                GLOBAL_METRICS.increment(
                    "jbf_cache_hits",
                    labels={"provider": provider_name, "model": model_name},
                )
                logger.debug(f"Cache hit for prompt (len={len(prompt)} chars)")
                return cached

        last_error = None
        last_error_type = None

        for attempt in range(self.max_retries + 1):
            try:
                if self.rate_limiter is not None:
                    self.rate_limiter.acquire()
                start = time.time()
                response = self.model.query(prompt)
                duration_ms = int((time.time() - start) * 1000)
                metric_labels = {
                    "provider": str(getattr(self.model, "provider_name", "unknown")),
                    "model": str(self.model.model_name),
                    "status": "success",
                }
                GLOBAL_METRICS.increment("jbf_model_requests", labels=metric_labels)
                GLOBAL_METRICS.observe(
                    "jbf_model_request_duration_seconds",
                    duration_ms / 1000,
                    labels={
                        "provider": metric_labels["provider"],
                        "model": metric_labels["model"],
                    },
                )
                GLOBAL_METRICS.increment(
                    "jbf_model_tokens",
                    amount=float(response.get("tokens_used", 0) or 0),
                    labels={
                        "provider": metric_labels["provider"],
                        "model": metric_labels["model"],
                    },
                )

                result = {
                    "text": response.get("text", ""),
                    "tokens_used": response.get("tokens_used", 0),
                    "prompt_tokens": response.get("prompt_tokens", 0),
                    "completion_tokens": response.get(
                        "completion_tokens",
                        response.get("tokens_used", 0),
                    ),
                    "duration_ms": duration_ms,
                    "status": 200,
                    "error": None,
                    "error_type": None,
                }
                if self.cache is not None and cache_key is not None:
                    self.cache.set(
                        cache_key,
                        provider=provider_name,
                        model=model_name,
                        response=result,
                    )
                return result

            except Exception as e:
                last_error = str(e)
                error_type = categorize_error(e)
                last_error_type = error_type.value
                with self._stats_lock:
                    self._total_errors += 1
                    self._error_types[error_type.value] = (
                        self._error_types.get(error_type.value, 0) + 1
                    )
                GLOBAL_METRICS.increment(
                    "jbf_model_request_errors",
                    labels={
                        "provider": str(getattr(self.model, "provider_name", "unknown")),
                        "model": str(self.model.model_name),
                        "error_type": error_type.value,
                    },
                )

                logger.warning(
                    f"Attempt {attempt + 1}/{self.max_retries + 1} failed [{error_type.value}]: {e}"
                )

                if error_type in (ErrorType.AUTH, ErrorType.MODEL):
                    logger.error(f"Non-retryable error [{error_type.value}]: {e}. Giving up.")
                    return {
                        "text": "",
                        "tokens_used": 0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "duration_ms": 0,
                        "status": 401 if error_type == ErrorType.AUTH else 500,
                        "error": last_error,
                        "error_type": error_type.value,
                    }

                if attempt < self.max_retries:
                    provider_delay = retry_after_seconds(e)
                    exponential = self.retry_delay * (2**attempt)
                    backoff = min(
                        self.max_retry_delay,
                        provider_delay if provider_delay is not None else exponential,
                    )
                    if self.retry_jitter:
                        backoff = min(
                            self.max_retry_delay,
                            backoff + random.uniform(0, self.retry_jitter),
                        )
                    logger.debug(f"Retrying in {backoff:.1f}s...")
                    self._sleeper(backoff)
                else:
                    logger.debug(f"No more retries. Max retries ({self.max_retries}) exhausted.")

        logger.error(f"All retries failed [{last_error_type}]. Last error: {last_error}")
        return {
            "text": "",
            "tokens_used": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "duration_ms": 0,
            "status": 500,
            "error": last_error,
            "error_type": last_error_type,
        }

    @property
    def stats(self) -> dict:
        return {
            "total_requests": self._total_requests,
            "total_errors": self._total_errors,
            "error_rate": (
                self._total_errors / self._total_requests if self._total_requests > 0 else 0.0
            ),
            "error_types": dict(self._error_types),
            "cache_hits": self._cache_hits,
        }
