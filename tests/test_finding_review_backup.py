import pytest

from domain.models import Campaign, CampaignStatus, ReviewDecision
from persistence.sqlite import SQLiteCampaignRepository


def _completed_finding(repository):
    campaign = Campaign(
        name="finding review",
        provider="mock",
        model="mock",
        authorization_reference="AUTH",
    )
    repository.create_campaign(campaign)
    repository.enqueue(campaign.campaign_id, "finding", {"prompt": "safe"})
    repository.transition_campaign(campaign.campaign_id, CampaignStatus.VALIDATED)
    repository.transition_campaign(campaign.campaign_id, CampaignStatus.RUNNING)
    item = repository.claim_next(campaign.campaign_id, "worker")
    completed = repository.complete_item(
        item.work_item_id,
        {
            "success": True,
            "risk_level": "High",
            "risk_score": 0.8,
            "raw_response": "evidence",
        },
    )
    return campaign, completed


def test_reviews_are_append_only_and_attributed(tmp_path):
    repository = SQLiteCampaignRepository(
        tmp_path / "reviews.db",
        actor_id="reviewer@example.test",
        actor_role="reviewer",
    )
    campaign, item = _completed_finding(repository)
    first = repository.review_finding(
        item.work_item_id,
        ReviewDecision.NEEDS_MORE_EVIDENCE,
        "Reproduction required",
    )
    second = repository.review_finding(
        item.work_item_id,
        ReviewDecision.CONFIRMED,
        "Reproduced independently",
    )
    assert second.supersedes_review_id == first.review_id
    findings = repository.list_findings(campaign.campaign_id)
    assert findings[0]["review"].review_id == second.review_id
    assert findings[0]["review"].reviewer_id == "reviewer@example.test"
    assert repository.verify_audit_chain(campaign.campaign_id)


def test_non_finding_cannot_be_reviewed(tmp_path):
    repository = SQLiteCampaignRepository(tmp_path / "reviews.db")
    campaign = Campaign(
        name="not a finding",
        provider="mock",
        model="mock",
        authorization_reference="AUTH",
    )
    repository.create_campaign(campaign)
    repository.enqueue(campaign.campaign_id, "safe", {"prompt": "safe"})
    repository.transition_campaign(campaign.campaign_id, CampaignStatus.VALIDATED)
    repository.transition_campaign(campaign.campaign_id, CampaignStatus.RUNNING)
    item = repository.claim_next(campaign.campaign_id, "worker")
    repository.complete_item(item.work_item_id, {"success": False})
    with pytest.raises(ValueError, match="successful"):
        repository.review_finding(
            item.work_item_id,
            ReviewDecision.CONFIRMED,
            "invalid review",
        )


def test_backup_verify_and_restore_to_new_path(tmp_path):
    source = SQLiteCampaignRepository(tmp_path / "source.db")
    campaign, _ = _completed_finding(source)
    backup_path = tmp_path / "backup.db"
    manifest = source.backup_to(backup_path)

    verified = SQLiteCampaignRepository.verify_backup(
        backup_path,
        expected_sha256=manifest["sha256"],
    )
    assert verified["integrity"] == "ok"

    restored_path = tmp_path / "restored.db"
    restored = SQLiteCampaignRepository.restore_backup(
        backup_path,
        restored_path,
        expected_sha256=manifest["sha256"],
    )
    assert restored["source_sha256"] == manifest["sha256"]
    restored_repository = SQLiteCampaignRepository(restored_path)
    assert restored_repository.get_campaign(campaign.campaign_id) is not None

    with pytest.raises(FileExistsError):
        SQLiteCampaignRepository.restore_backup(
            backup_path,
            restored_path,
        )


def test_backup_hash_mismatch_is_rejected(tmp_path):
    repository = SQLiteCampaignRepository(tmp_path / "source.db")
    backup = tmp_path / "backup.db"
    repository.backup_to(backup)
    with pytest.raises(ValueError, match="SHA-256"):
        SQLiteCampaignRepository.verify_backup(backup, expected_sha256="0" * 64)
