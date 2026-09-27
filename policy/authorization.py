from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _canonical_payload(payload: dict[str, Any]) -> bytes:
    unsigned = {key: value for key, value in payload.items() if key != "signature"}
    return json.dumps(
        unsigned,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sign_authorization_payload(payload: dict[str, Any], signing_key: str) -> str:
    if not signing_key:
        raise ValueError("Authorization signing key must not be empty")
    return hmac.new(
        signing_key.encode("utf-8"),
        _canonical_payload(payload),
        hashlib.sha256,
    ).hexdigest()


class AuthorizationGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    grant_id: str = Field(min_length=1, max_length=200)
    issued_by: str = Field(min_length=1, max_length=300)
    issued_at: datetime
    not_before: datetime
    expires_at: datetime
    target_ids: list[str] = Field(min_length=1)
    providers: list[str] = Field(min_length=1)
    models: list[str] = Field(min_length=1)
    strategies: list[str] = Field(min_length=1)
    max_requests: int = Field(gt=0)
    signature: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("issued_at", "not_before", "expires_at")
    @classmethod
    def timestamps_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("authorization timestamps must include a timezone")
        return value

    def permits(
        self,
        target_id: str,
        provider: str,
        model: str,
        strategies: list[str],
        request_count: int,
        now: datetime,
    ) -> list[str]:
        failures: list[str] = []
        if now < self.not_before:
            failures.append("authorization is not active yet")
        if now >= self.expires_at:
            failures.append("authorization has expired")
        if target_id not in self.target_ids and "*" not in self.target_ids:
            failures.append(f"target is outside scope: {target_id}")
        if provider not in self.providers and "*" not in self.providers:
            failures.append(f"provider is outside scope: {provider}")
        if model not in self.models and "*" not in self.models:
            failures.append(f"model is outside scope: {model}")
        unsupported = sorted(
            strategy
            for strategy in strategies
            if strategy not in self.strategies and "*" not in self.strategies
        )
        if unsupported:
            failures.append("strategies are outside scope: " + ", ".join(unsupported))
        if request_count > self.max_requests:
            failures.append(f"request count exceeds grant ({request_count}/{self.max_requests})")
        return failures


class AuthorizationVerifier:
    def __init__(self, signing_key: str):
        if not signing_key:
            raise ValueError("Authorization signing key is required")
        self.signing_key = signing_key

    def load_and_verify(
        self,
        path: str | Path,
        *,
        target_id: str,
        provider: str,
        model: str,
        strategies: list[str],
        request_count: int,
        now: datetime | None = None,
    ) -> AuthorizationGrant:
        raw = Path(path).read_bytes()
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("Authorization grant must be a JSON object")
        supplied = str(payload.get("signature", ""))
        expected = sign_authorization_payload(payload, self.signing_key)
        if not hmac.compare_digest(supplied, expected):
            raise ValueError("Authorization signature is invalid")
        grant = AuthorizationGrant.model_validate(payload)
        failures = grant.permits(
            target_id=target_id,
            provider=provider,
            model=model,
            strategies=strategies,
            request_count=request_count,
            now=now or datetime.now(timezone.utc),
        )
        if failures:
            raise ValueError("Authorization denied: " + "; ".join(failures))
        return grant

    @staticmethod
    def document_sha256(path: str | Path) -> str:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
