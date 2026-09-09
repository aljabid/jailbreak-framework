from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from utils.encryption import ArtifactCipher


@dataclass(frozen=True, slots=True)
class HealthCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True, slots=True)
class HealthReport:
    profile: str
    live: bool
    ready: bool
    checks: tuple[HealthCheck, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["checks"] = [asdict(check) for check in self.checks]
        return value


class HealthChecker:
    def __init__(self, config):
        self.config = config

    def check(self, profile: str = "mock") -> HealthReport:
        if profile not in {"mock", "production"}:
            raise ValueError("Health profile must be mock or production")
        checks = [
            self._database_check(),
            self._output_check(),
            HealthCheck("configuration", True, "validated"),
        ]
        if profile == "production":
            checks.extend(
                [
                    self._secret_check("JBF_AUTHORIZATION_SIGNING_KEY"),
                    self._artifact_key_check(),
                    HealthCheck(
                        "rbac",
                        self.config.enforce_rbac,
                        ("enforced" if self.config.enforce_rbac else "disabled"),
                    ),
                ]
            )
        ready = all(check.ok for check in checks)
        return HealthReport(
            profile=profile,
            live=True,
            ready=ready,
            checks=tuple(checks),
        )

    def _database_check(self) -> HealthCheck:
        try:
            path = Path(self.config.database_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(path)) as connection:
                connection.execute("SELECT 1").fetchone()
            return HealthCheck("database", True, str(path))
        except Exception as exc:
            return HealthCheck("database", False, type(exc).__name__)

    def _output_check(self) -> HealthCheck:
        path = Path(self.config.results_file).parent
        try:
            path.mkdir(parents=True, exist_ok=True)
            ok = os.access(path, os.W_OK)
            return HealthCheck(
                "output_directory",
                ok,
                str(path) if ok else "not writable",
            )
        except Exception as exc:
            return HealthCheck("output_directory", False, type(exc).__name__)

    @staticmethod
    def _secret_check(variable: str) -> HealthCheck:
        value = os.getenv(variable, "")
        present = len(value) >= 32
        return HealthCheck(
            variable,
            present,
            "configured" if present else "missing or too short",
        )

    @staticmethod
    def _artifact_key_check() -> HealthCheck:
        try:
            cipher = ArtifactCipher.from_environment()
            return HealthCheck(
                "JBF_ARTIFACT_ENCRYPTION_KEY",
                True,
                f"configured key_id={cipher.key_id}",
            )
        except ValueError:
            return HealthCheck(
                "JBF_ARTIFACT_ENCRYPTION_KEY",
                False,
                "missing or invalid",
            )
