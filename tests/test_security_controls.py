import sqlite3
from contextlib import closing

import pytest

from domain.models import Campaign, CampaignStatus
from models.local_model import LocalModel
from persistence.sqlite import SQLiteCampaignRepository
from policy.endpoints import validate_http_endpoint
from utils.encryption import ENVELOPE_PREFIX, ArtifactCipher


def test_endpoint_allowlist_and_scheme_are_enforced():
    assert (
        validate_http_endpoint(
            "http://localhost:11434",
            allowed_hosts=["localhost"],
        )
        == "http://localhost:11434"
    )
    with pytest.raises(ValueError, match="allowlisted"):
        validate_http_endpoint(
            "http://169.254.169.254/latest/meta-data",
            allowed_hosts=["localhost"],
        )
    with pytest.raises(ValueError, match="HTTPS"):
        validate_http_endpoint(
            "http://models.example.test",
            allowed_hosts=["models.example.test"],
        )


def test_endpoint_rejects_credentials_and_redirect_primitives():
    with pytest.raises(ValueError, match="credentials"):
        validate_http_endpoint(
            "https://user:pass@models.example.test",
            allowed_hosts=["models.example.test"],
        )


def test_local_model_rejects_non_allowlisted_endpoint():
    with pytest.raises(ValueError, match="allowlisted"):
        LocalModel(
            mode="ollama",
            model_name="test",
            ollama_base_url="https://unapproved.example.test",
            allowed_hosts=["approved.example.test"],
        )
    with pytest.raises(ValueError, match="query or fragment"):
        validate_http_endpoint(
            "https://models.example.test#redirect",
            allowed_hosts=["models.example.test"],
        )


def test_artifact_cipher_detects_tampering():
    cipher = ArtifactCipher.from_base64(ArtifactCipher.generate_key())
    encrypted = cipher.encrypt_json({"secret": "evidence"}, context="case:1")
    assert encrypted.startswith(ENVELOPE_PREFIX)
    assert cipher.decrypt_json(encrypted, context="case:1") == {"secret": "evidence"}
    with pytest.raises(ValueError, match="authentication failed"):
        cipher.decrypt_json(encrypted, context="case:2")


def test_database_encrypts_result_payload(tmp_path):
    cipher = ArtifactCipher.from_base64(ArtifactCipher.generate_key())
    repository = SQLiteCampaignRepository(
        tmp_path / "encrypted.db",
        artifact_cipher=cipher,
    )
    campaign = Campaign(
        name="encrypted",
        provider="mock",
        model="mock",
        authorization_reference="AUTH",
    )
    repository.create_campaign(campaign)
    repository.enqueue(campaign.campaign_id, "one", {"prompt": "safe"})
    repository.transition_campaign(campaign.campaign_id, CampaignStatus.VALIDATED)
    repository.transition_campaign(campaign.campaign_id, CampaignStatus.RUNNING)
    item = repository.claim_next(campaign.campaign_id, "worker")
    repository.complete_item(
        item.work_item_id,
        {"raw_response": "sensitive evidence"},
    )

    with closing(sqlite3.connect(repository.database_path)) as connection:
        stored = connection.execute("SELECT result_json FROM campaign_work_items").fetchone()[0]
    assert stored.startswith(ENVELOPE_PREFIX)
    assert "sensitive evidence" not in stored
