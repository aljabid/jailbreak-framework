import json
from datetime import datetime, timedelta, timezone

from click.testing import CliRunner

from main import cli


def test_authorization_sign_and_verify_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("JBF_ACTOR_ID", "admin@example.test")
    monkeypatch.setenv("JBF_ACTOR_ROLE", "administrator")
    monkeypatch.setenv("JBF_AUTHORIZATION_SIGNING_KEY", "x" * 32)
    now = datetime.now(timezone.utc)
    unsigned = {
        "schema_version": "1.0",
        "grant_id": "SEC-CLI-1",
        "issued_by": "security@example.test",
        "issued_at": now.isoformat(),
        "not_before": (now - timedelta(minutes=1)).isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
        "target_ids": ["target-1"],
        "providers": ["openai"],
        "models": ["model-1"],
        "strategies": ["roleplay"],
        "max_requests": 5,
    }
    unsigned_path = tmp_path / "unsigned.json"
    signed_path = tmp_path / "signed.json"
    unsigned_path.write_text(json.dumps(unsigned))
    runner = CliRunner()

    signed = runner.invoke(
        cli,
        [
            "authorization",
            "sign",
            "--input",
            str(unsigned_path),
            "--output",
            str(signed_path),
        ],
    )
    assert signed.exit_code == 0, signed.output
    assert signed_path.stat().st_mode & 0o777 == 0o600

    verified = runner.invoke(
        cli,
        [
            "authorization",
            "verify",
            "--input",
            str(signed_path),
            "--target-id",
            "target-1",
            "--provider",
            "openai",
            "--model",
            "model-1",
            "--strategy",
            "roleplay",
            "--request-count",
            "2",
        ],
    )
    assert verified.exit_code == 0, verified.output
    assert json.loads(verified.output)["valid"] is True
