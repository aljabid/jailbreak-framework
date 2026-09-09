import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

VALID_PROVIDERS = {"openai", "anthropic", "local", "mock"}
VALID_LOCAL_MODES = {"ollama", "huggingface", "mock"}
VALID_EVAL_MODES = {"keyword", "ai_judge", "hybrid"}


def _load_yaml(path: Path) -> dict:

    if not path.exists():
        logger.warning(f"Config file not found: {path}. Using defaults.")
        return {}
    try:
        import yaml

        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        logger.warning("pyyaml not installed. Using environment vars only.")
        return {}


def _load_dotenv(env_file: str = ".env") -> None:

    try:
        from dotenv import load_dotenv

        load_dotenv(env_file, override=False)
    except ImportError:
        pass


def _coerce_value(value: Any, template: Any = None) -> Any:

    if template is None:
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "yes", "1", "on"}:
                return True
            if lowered in {"false", "no", "0", "off"}:
                return False
            try:
                if "." in value:
                    return float(value)
                return int(value)
            except ValueError:
                return value
        return value

    if isinstance(template, bool):
        if isinstance(value, str):
            return value.strip().lower() in {"true", "yes", "1", "on"}
        return bool(value)

    if isinstance(template, int) and not isinstance(template, bool):
        return int(value)

    if isinstance(template, float):
        return float(value)

    if isinstance(template, list):
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return list(value)

    return value


class Config:
    DEFAULTS = {
        "model.provider": "openai",
        "model.name": "gpt-3.5-turbo",
        "model.temperature": 0.7,
        "model.max_tokens": 1024,
        "model.timeout": 30,
        "model.local_mode": "ollama",
        "model.ollama_base_url": "http://localhost:11434",
        "model.allowed_hosts": ["localhost", "127.0.0.1", "::1"],
        "model.mock_success_rate": 0.35,
        "model.rate_limit_delay": 1.5,
        "model.requests_per_second": 0.67,
        "attack.strategies": [
            "roleplay",
            "instruction_override",
            "encoding_attack",
            "token_smuggling",
            "fictional_framing",
            "multi_turn",
        ],
        "attack.base_prompts_file": "data/prompts.json",
        "attack.max_retries": 2,
        "attack.retry_delay": 2.0,
        "attack.max_retry_delay": 60.0,
        "attack.retry_jitter": 0.25,
        "attack.cache_enabled": False,
        "attack.cache_file": "outputs/cache.sqlite3",
        "evaluation.mode": "keyword",
        "evaluation.ai_judge_model": "gpt-4o-mini",
        "evaluation.keywords_file": "data/jailbreak_keywords.json",
        "evaluation.confidence_threshold": 0.5,
        "scoring.critical_threshold": 0.85,
        "scoring.high_threshold": 0.65,
        "scoring.medium_threshold": 0.40,
        "output.results_file": "outputs/results.json",
        "output.logs_file": "outputs/logs.txt",
        "output.report_dir": "reports/",
        "output.save_all_responses": True,
        "output.pretty_print": True,
        "storage.database_path": "outputs/jbf.db",
        "security.enforce_rbac": True,
        "logging.level": "INFO",
        "logging.console": True,
        "logging.file": True,
    }

    def __init__(
        self,
        config_file: str = "config.yaml",
        env_file: str = ".env",
        strict: bool = False,
    ):
        _load_dotenv(env_file)
        raw = _load_yaml(Path(config_file))
        if not isinstance(raw, dict):
            raise ValueError("Configuration root must be a mapping")
        self._data = self._flatten(raw)
        self.validation_issues: list[str] = []
        self._validate(strict=strict)

    def _validate(self, strict: bool = False) -> None:

        checks = [
            (
                self.model_provider in VALID_PROVIDERS,
                "model.provider",
                self.model_provider,
                self.DEFAULTS["model.provider"],
            ),
            (
                self.local_mode in VALID_LOCAL_MODES,
                "model.local_mode",
                self.local_mode,
                self.DEFAULTS["model.local_mode"],
            ),
            (
                self.eval_mode in VALID_EVAL_MODES,
                "evaluation.mode",
                self.eval_mode,
                self.DEFAULTS["evaluation.mode"],
            ),
            (
                0.0 <= self.temperature <= 2.0,
                "model.temperature",
                self.temperature,
                self.DEFAULTS["model.temperature"],
            ),
            (
                self.max_tokens > 0,
                "model.max_tokens",
                self.max_tokens,
                self.DEFAULTS["model.max_tokens"],
            ),
            (
                self.timeout > 0,
                "model.timeout",
                self.timeout,
                self.DEFAULTS["model.timeout"],
            ),
            (
                self.max_retries >= 0,
                "attack.max_retries",
                self.max_retries,
                self.DEFAULTS["attack.max_retries"],
            ),
            (
                self.retry_delay >= 0,
                "attack.retry_delay",
                self.retry_delay,
                self.DEFAULTS["attack.retry_delay"],
            ),
            (
                self.max_retry_delay > 0,
                "attack.max_retry_delay",
                self.max_retry_delay,
                self.DEFAULTS["attack.max_retry_delay"],
            ),
            (
                self.retry_jitter >= 0,
                "attack.retry_jitter",
                self.retry_jitter,
                self.DEFAULTS["attack.retry_jitter"],
            ),
            (
                self.rate_limit_delay >= 0,
                "model.rate_limit_delay",
                self.rate_limit_delay,
                self.DEFAULTS["model.rate_limit_delay"],
            ),
            (
                self.requests_per_second > 0,
                "model.requests_per_second",
                self.requests_per_second,
                self.DEFAULTS["model.requests_per_second"],
            ),
            (
                0.0 <= self.confidence_threshold <= 1.0,
                "evaluation.confidence_threshold",
                self.confidence_threshold,
                self.DEFAULTS["evaluation.confidence_threshold"],
            ),
            (
                0.0
                <= self.medium_threshold
                <= self.high_threshold
                <= self.critical_threshold
                <= 1.0,
                "scoring thresholds",
                (
                    self.medium_threshold,
                    self.high_threshold,
                    self.critical_threshold,
                ),
                (
                    self.DEFAULTS["scoring.medium_threshold"],
                    self.DEFAULTS["scoring.high_threshold"],
                    self.DEFAULTS["scoring.critical_threshold"],
                ),
            ),
        ]

        for valid, key, value, fallback in checks:
            if valid:
                continue
            message = f"Invalid {key}: {value!r}"
            self.validation_issues.append(message)
            if strict:
                continue
            logger.warning("%s; using default %r", message, fallback)
            if key == "scoring thresholds":
                if not isinstance(fallback, tuple) or len(fallback) != 3:
                    raise TypeError("Scoring threshold fallback must contain three values")
                self._data["scoring.medium_threshold"] = fallback[0]
                self._data["scoring.high_threshold"] = fallback[1]
                self._data["scoring.critical_threshold"] = fallback[2]
            else:
                self._data[key] = fallback

        if strict and self.validation_issues:
            raise ValueError("Invalid configuration:\n- " + "\n- ".join(self.validation_issues))

    def _flatten(self, d: dict, prefix: str = "") -> dict:

        items = {}
        for k, v in d.items():
            key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                items.update(self._flatten(v, key))
            else:
                items[key] = v
        return items

    def get(self, key: str, default: Any = None) -> Any:

        env_key = "JBF_" + key.upper().replace(".", "_")
        template = self._data.get(key, self.DEFAULTS.get(key, default))
        if env_key in os.environ:
            return _coerce_value(os.environ[env_key], template)
        return template

    @property
    def model_provider(self) -> str:
        return str(self.get("model.provider"))

    @property
    def model_name(self) -> str:
        return str(self.get("model.name"))

    @property
    def temperature(self) -> float:
        return float(self.get("model.temperature"))

    @property
    def max_tokens(self) -> int:
        return int(self.get("model.max_tokens"))

    @property
    def timeout(self) -> int:
        return int(self.get("model.timeout"))

    @property
    def rate_limit_delay(self) -> float:
        return float(self.get("model.rate_limit_delay"))

    @property
    def requests_per_second(self) -> float:
        return float(self.get("model.requests_per_second"))

    @property
    def local_mode(self) -> str:
        return str(self.get("model.local_mode"))

    @property
    def ollama_base_url(self) -> str:
        return str(self.get("model.ollama_base_url"))

    @property
    def allowed_hosts(self) -> list[str]:
        value = self.get("model.allowed_hosts")
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return [str(part) for part in value]

    @property
    def mock_success_rate(self) -> float:
        return float(self.get("model.mock_success_rate"))

    @property
    def strategies(self) -> list[str]:
        val = self.get("attack.strategies")
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            return [s.strip() for s in val.split(",")]
        return []

    @property
    def prompts_file(self) -> str:
        return str(self.get("attack.base_prompts_file"))

    @property
    def max_retries(self) -> int:
        return int(self.get("attack.max_retries"))

    @property
    def retry_delay(self) -> float:
        return float(self.get("attack.retry_delay"))

    @property
    def max_retry_delay(self) -> float:
        return float(self.get("attack.max_retry_delay"))

    @property
    def retry_jitter(self) -> float:
        return float(self.get("attack.retry_jitter"))

    @property
    def cache_enabled(self) -> bool:
        return bool(self.get("attack.cache_enabled"))

    @property
    def cache_file(self) -> str:
        return str(self.get("attack.cache_file"))

    @property
    def eval_mode(self) -> str:
        return str(self.get("evaluation.mode"))

    @property
    def ai_judge_model(self) -> str:
        return str(self.get("evaluation.ai_judge_model"))

    @property
    def keywords_file(self) -> str:
        return str(self.get("evaluation.keywords_file"))

    @property
    def confidence_threshold(self) -> float:
        return float(self.get("evaluation.confidence_threshold"))

    @property
    def critical_threshold(self) -> float:
        return float(self.get("scoring.critical_threshold"))

    @property
    def high_threshold(self) -> float:
        return float(self.get("scoring.high_threshold"))

    @property
    def medium_threshold(self) -> float:
        return float(self.get("scoring.medium_threshold"))

    @property
    def results_file(self) -> str:
        return str(self.get("output.results_file"))

    @property
    def logs_file(self) -> str:
        return str(self.get("output.logs_file"))

    @property
    def report_dir(self) -> str:
        return str(self.get("output.report_dir"))

    @property
    def save_all_responses(self) -> bool:
        return bool(self.get("output.save_all_responses"))

    @property
    def pretty_print(self) -> bool:
        return bool(self.get("output.pretty_print"))

    @property
    def database_path(self) -> str:
        return str(self.get("storage.database_path"))

    @property
    def enforce_rbac(self) -> bool:
        return bool(self.get("security.enforce_rbac"))

    @property
    def log_level(self) -> str:
        return str(self.get("logging.level"))

    @property
    def console_logging(self) -> bool:
        return bool(self.get("logging.console"))

    @property
    def file_logging(self) -> bool:
        return bool(self.get("logging.file"))

    @property
    def openai_api_key(self) -> str | None:
        return os.getenv("OPENAI_API_KEY") or str(self.get("api.openai_key", ""))

    @property
    def anthropic_api_key(self) -> str | None:
        return os.getenv("ANTHROPIC_API_KEY") or str(self.get("api.anthropic_key", ""))

    @property
    def authorization_signing_key(self) -> str | None:

        return os.getenv("JBF_AUTHORIZATION_SIGNING_KEY")

    def summarize(self) -> dict:

        return {
            "model": f"{self.model_provider}/{self.model_name}",
            "strategies": self.strategies,
            "eval_mode": self.eval_mode,
            "results_file": self.results_file,
            "log_level": self.log_level,
        }
