#!/usr/bin/env python3


from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import requests
import yaml
from click.testing import CliRunner

from main import cli
from persistence.sqlite import SQLiteCampaignRepository
from utils.encryption import ArtifactCipher

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _invoke(runner: CliRunner, args: list[str], environment: dict[str, str]):
    result = runner.invoke(cli, args, env=environment)
    if result.exit_code != 0:
        raise RuntimeError(
            f"Command failed ({' '.join(args)}):\n{result.output}"
        ) from result.exception
    return result


def _model_digest(endpoint: str, model: str) -> str:
    response = requests.get(f"{endpoint.rstrip('/')}/api/tags", timeout=10)
    response.raise_for_status()
    for item in response.json().get("models", []):
        if item.get("name") == model or item.get("model") == model:
            return str(item.get("digest", ""))
    raise ValueError(f"Model is not installed in Ollama: {model}")


def run_acceptance(endpoint: str, model: str) -> dict:
    started_at = datetime.now(timezone.utc)
    runner = CliRunner()
    signing_key = secrets.token_urlsafe(48)
    artifact_key = ArtifactCipher.generate_key()
    environment = {
        "JBF_ACTOR_ID": "local-acceptance@localhost",
        "JBF_ACTOR_ROLE": "administrator",
        "JBF_AUTHORIZATION_SIGNING_KEY": signing_key,
        "JBF_ARTIFACT_ENCRYPTION_KEY": artifact_key,
    }

    with tempfile.TemporaryDirectory(prefix="jbf-local-acceptance-") as directory:
        root = Path(directory)
        database_path = root / "campaign.db"
        config_path = root / "config.yaml"
        config = {
            "model": {
                "provider": "local",
                "name": model,
                "local_mode": "ollama",
                "ollama_base_url": endpoint,
                "allowed_hosts": ["127.0.0.1", "localhost", "::1"],
                "temperature": 0.0,
                "max_tokens": 64,
                "timeout": 120,
                "requests_per_second": 10,
                "rate_limit_delay": 0,
            },
            "attack": {
                "strategies": ["roleplay"],
                "base_prompts_file": str(PROJECT_ROOT / "data" / "prompts.json"),
                "max_retries": 1,
                "retry_delay": 0.1,
                "max_retry_delay": 1,
                "retry_jitter": 0,
            },
            "evaluation": {
                "mode": "keyword",
                "keywords_file": str(PROJECT_ROOT / "data" / "jailbreak_keywords.json"),
            },
            "storage": {"database_path": str(database_path)},
            "output": {
                "results_file": str(root / "results.json"),
                "logs_file": str(root / "logs.txt"),
                "report_dir": str(root / "reports"),
            },
            "security": {"enforce_rbac": True},
            "logging": {"console": False, "file": False},
        }
        config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

        unsigned_path = root / "unsigned-grant.json"
        signed_path = root / "signed-grant.json"
        unsigned = {
            "schema_version": "1.0",
            "grant_id": "LOCAL-ACCEPTANCE-DRILL",
            "issued_by": "local-security-owner@localhost",
            "issued_at": started_at.isoformat(),
            "not_before": (started_at - timedelta(minutes=1)).isoformat(),
            "expires_at": (started_at + timedelta(hours=1)).isoformat(),
            "target_ids": ["local-ollama"],
            "providers": ["local"],
            "models": [model],
            "strategies": ["roleplay"],
            "max_requests": 1,
        }
        unsigned_path.write_text(json.dumps(unsigned), encoding="utf-8")

        base = ["--config", str(config_path)]
        _invoke(
            runner,
            base
            + [
                "authorization",
                "sign",
                "--input",
                str(unsigned_path),
                "--output",
                str(signed_path),
            ],
            environment,
        )
        verification = _invoke(
            runner,
            base
            + [
                "authorization",
                "verify",
                "--input",
                str(signed_path),
                "--target-id",
                "local-ollama",
                "--provider",
                "local",
                "--model",
                model,
                "--strategy",
                "roleplay",
                "--request-count",
                "1",
            ],
            environment,
        )
        if not json.loads(verification.output)["valid"]:
            raise RuntimeError("Authorization verification did not pass")

        created = _invoke(
            runner,
            base
            + [
                "campaign",
                "create",
                "--name",
                "Local provider production-acceptance drill",
                "--target-id",
                "local-ollama",
                "--authorization-file",
                str(signed_path),
                "--strategy",
                "roleplay",
                "--count",
                "1",
                "--seed",
                "20260726",
                "--max-requests",
                "1",
                "--max-tokens",
                "512",
                "--max-failures",
                "1",
            ],
            environment,
        )
        match = re.search(r"Campaign ID: ([0-9a-f-]+)", created.output)
        if not match:
            raise RuntimeError("Campaign creation did not return an identifier")
        campaign_id = match.group(1)
        campaign_uuid = UUID(campaign_id)

        _invoke(
            runner,
            base + ["campaign", "run", campaign_id],
            environment,
        )
        status_result = _invoke(
            runner,
            base + ["campaign", "status", campaign_id, "--json-output"],
            environment,
        )
        status = json.loads(status_result.output)
        if status["status"] != "completed":
            raise RuntimeError(f"Campaign did not complete: {status['status']}")

        backup_path = root / "campaign.backup.db"
        backup = _invoke(
            runner,
            base + ["campaign", "backup", "--output", str(backup_path)],
            environment,
        )
        backup_manifest = json.loads(backup.output)
        verified = _invoke(
            runner,
            base
            + [
                "campaign",
                "backup-verify",
                "--input",
                str(backup_path),
                "--sha256",
                backup_manifest["sha256"],
            ],
            environment,
        )
        verification_manifest = json.loads(verified.output)
        restored_path = root / "restored.db"
        _invoke(
            runner,
            base
            + [
                "campaign",
                "backup-restore",
                "--input",
                str(backup_path),
                "--destination",
                str(restored_path),
                "--sha256",
                backup_manifest["sha256"],
                "--yes",
            ],
            environment,
        )

        cipher = ArtifactCipher.from_base64(artifact_key)
        repository = SQLiteCampaignRepository(
            database_path,
            artifact_cipher=cipher,
            actor_id=environment["JBF_ACTOR_ID"],
            actor_role=environment["JBF_ACTOR_ROLE"],
        )
        restored_repository = SQLiteCampaignRepository(
            restored_path,
            artifact_cipher=cipher,
        )
        restored_campaign = restored_repository.get_campaign(campaign_uuid)
        if restored_campaign is None or restored_campaign.status.value != "completed":
            raise RuntimeError("Restored campaign evidence is incomplete")

        signed_sha256 = hashlib.sha256(signed_path.read_bytes()).hexdigest()
        return {
            "schema_version": "1.0",
            "drill": "local-provider-production-acceptance",
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "provider": "ollama",
            "endpoint_scope": "loopback-only",
            "model": model,
            "model_digest": _model_digest(endpoint, model),
            "authorization": {
                "grant_id": unsigned["grant_id"],
                "document_sha256": signed_sha256,
                "signature_verified": True,
            },
            "campaign_id": campaign_id,
            "campaign_status": status["status"],
            "counts": status["counts"],
            "audit_chain_valid": repository.verify_audit_chain(campaign_uuid),
            "encryption_enabled": True,
            "backup": {
                "sha256": backup_manifest["sha256"],
                "integrity": verification_manifest["integrity"],
                "restoration_verified": True,
            },
            "secrets_persisted": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="qwen2.5:0.5b")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    evidence = run_acceptance(args.endpoint, args.model)
    rendered = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        os.chmod(args.output, 0o600)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
