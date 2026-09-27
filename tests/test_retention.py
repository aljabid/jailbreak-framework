import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

from domain.models import Campaign, CampaignStatus
from persistence.sqlite import SQLiteCampaignRepository


def test_retention_is_dry_run_by_default(tmp_path):
    repository = SQLiteCampaignRepository(tmp_path / "retention.db")
    campaign = Campaign(
        name="old campaign",
        provider="mock",
        model="mock",
        authorization_reference="AUTH",
    )
    repository.create_campaign(campaign)
    repository.transition_campaign(campaign.campaign_id, CampaignStatus.VALIDATED)
    repository.transition_campaign(campaign.campaign_id, CampaignStatus.RUNNING)
    repository.transition_campaign(campaign.campaign_id, CampaignStatus.COMPLETED)
    old = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    with closing(sqlite3.connect(repository.database_path)) as connection, connection:
        connection.execute(
            "UPDATE campaigns SET updated_at = ? WHERE campaign_id = ?",
            (old, str(campaign.campaign_id)),
        )

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    preview = repository.purge_campaigns_before(cutoff)
    assert preview["candidate_count"] == 1
    assert preview["deleted_count"] == 0
    assert repository.get_campaign(campaign.campaign_id) is not None

    result = repository.purge_campaigns_before(cutoff, dry_run=False)
    assert result["deleted_count"] == 1
    assert repository.get_campaign(campaign.campaign_id) is None
    assert repository.verify_retention_chain()


def test_retention_never_deletes_active_campaigns(tmp_path):
    repository = SQLiteCampaignRepository(tmp_path / "retention.db")
    campaign = Campaign(
        name="active",
        provider="mock",
        model="mock",
        authorization_reference="AUTH",
    )
    repository.create_campaign(campaign)
    with closing(sqlite3.connect(repository.database_path)) as connection, connection:
        connection.execute(
            "UPDATE campaigns SET updated_at = ? WHERE campaign_id = ?",
            (
                (datetime.now(timezone.utc) - timedelta(days=365)).isoformat(),
                str(campaign.campaign_id),
            ),
        )
    result = repository.purge_campaigns_before(
        datetime.now(timezone.utc) - timedelta(days=30),
        dry_run=False,
    )
    assert result["deleted_count"] == 0
    assert repository.get_campaign(campaign.campaign_id) is not None
