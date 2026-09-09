import json
from datetime import datetime, timedelta, timezone

import pytest

from policy.authorization import AuthorizationVerifier, sign_authorization_payload


def _grant(**overrides):
    now = datetime.now(timezone.utc)
    payload = {
        "schema_version": "1.0",
        "grant_id": "SEC-2026-001",
        "issued_by": "security@example.test",
        "issued_at": now.isoformat(),
        "not_before": (now - timedelta(minutes=1)).isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
        "target_ids": ["internal-model"],
        "providers": ["openai"],
        "models": ["approved-model"],
        "strategies": ["roleplay"],
        "max_requests": 10,
    }
    payload.update(overrides)
    payload["signature"] = sign_authorization_payload(payload, "test-key")
    return payload


def _write(tmp_path, payload):
    path = tmp_path / "authorization.json"
    path.write_text(json.dumps(payload))
    return path


def test_valid_signed_authorization_is_accepted(tmp_path):
    path = _write(tmp_path, _grant())
    grant = AuthorizationVerifier("test-key").load_and_verify(
        path,
        target_id="internal-model",
        provider="openai",
        model="approved-model",
        strategies=["roleplay"],
        request_count=2,
    )
    assert grant.grant_id == "SEC-2026-001"
    assert len(AuthorizationVerifier.document_sha256(path)) == 64


def test_tampered_authorization_is_rejected(tmp_path):
    payload = _grant()
    payload["max_requests"] = 1000
    path = _write(tmp_path, payload)
    with pytest.raises(ValueError, match="signature"):
        AuthorizationVerifier("test-key").load_and_verify(
            path,
            target_id="internal-model",
            provider="openai",
            model="approved-model",
            strategies=["roleplay"],
            request_count=2,
        )


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"target_ids": ["other"]}, "target is outside scope"),
        ({"providers": ["local"]}, "provider is outside scope"),
        ({"models": ["other"]}, "model is outside scope"),
        ({"strategies": ["encoding_attack"]}, "strategies are outside scope"),
        ({"max_requests": 1}, "request count exceeds grant"),
    ],
)
def test_scope_is_enforced(tmp_path, override, message):
    path = _write(tmp_path, _grant(**override))
    with pytest.raises(ValueError, match=message):
        AuthorizationVerifier("test-key").load_and_verify(
            path,
            target_id="internal-model",
            provider="openai",
            model="approved-model",
            strategies=["roleplay"],
            request_count=2,
        )


def test_expired_authorization_is_rejected(tmp_path):
    expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    path = _write(tmp_path, _grant(expires_at=expired))
    with pytest.raises(ValueError, match="expired"):
        AuthorizationVerifier("test-key").load_and_verify(
            path,
            target_id="internal-model",
            provider="openai",
            model="approved-model",
            strategies=["roleplay"],
            request_count=1,
        )
