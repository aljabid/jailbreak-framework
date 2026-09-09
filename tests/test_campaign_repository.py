import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

import pytest

from application.campaigns import CampaignRunner
from domain.models import Campaign, CampaignStatus, WorkItemStatus
from persistence.sqlite import SQLiteCampaignRepository


@pytest.fixture
def repository(tmp_path):
    return SQLiteCampaignRepository(tmp_path / "campaigns.db")


@pytest.fixture
def campaign(repository):
    value = Campaign(
        name="test campaign",
        provider="mock",
        model="mock",
        authorization_reference="TEST-AUTH-001",
    )
    repository.create_campaign(value)
    return value


def test_campaign_lifecycle_is_enforced(repository, campaign):
    validated = repository.transition_campaign(campaign.campaign_id, CampaignStatus.VALIDATED)
    assert validated.status == CampaignStatus.VALIDATED

    with pytest.raises(ValueError, match="Invalid campaign transition"):
        repository.transition_campaign(campaign.campaign_id, CampaignStatus.COMPLETED)


def test_enqueue_is_idempotent(repository, campaign):
    first = repository.enqueue(campaign.campaign_id, "stable-key", {"value": 1})
    second = repository.enqueue(campaign.campaign_id, "stable-key", {"value": 2})

    assert first.work_item_id == second.work_item_id
    assert second.payload == {"value": 1}
    assert repository.campaign_counts(campaign.campaign_id)["total"] == 1


def test_claim_is_atomic_across_workers(repository, campaign):
    repository.enqueue(campaign.campaign_id, "only-once", {"value": 1})
    repository.transition_campaign(campaign.campaign_id, CampaignStatus.VALIDATED)
    repository.transition_campaign(campaign.campaign_id, CampaignStatus.RUNNING)

    def claim(worker):
        return repository.claim_next(campaign.campaign_id, worker)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claimed = list(pool.map(claim, ["worker-a", "worker-b"]))

    items = [item for item in claimed if item is not None]
    assert len(items) == 1
    assert items[0].attempts == 1


def test_interrupted_work_is_requeued(repository, campaign):
    repository.enqueue(campaign.campaign_id, "recover-me", {"value": 1})
    repository.transition_campaign(campaign.campaign_id, CampaignStatus.VALIDATED)
    repository.transition_campaign(campaign.campaign_id, CampaignStatus.RUNNING)
    claimed = repository.claim_next(campaign.campaign_id, "dead-worker")

    assert claimed.status == WorkItemStatus.RUNNING
    assert repository.recover_interrupted(campaign.campaign_id) == 1
    recovered = repository.claim_next(campaign.campaign_id, "new-worker")
    assert recovered.work_item_id == claimed.work_item_id
    assert recovered.attempts == 2


def test_runner_checkpoints_successful_work(repository, campaign):
    for number in range(3):
        repository.enqueue(
            campaign.campaign_id,
            f"item-{number}",
            {"number": number},
        )

    runner = CampaignRunner(
        repository,
        processor=lambda payload: {"answer": payload["number"] * 2},
        worker_id="worker-1",
    )
    counts = runner.run(campaign.campaign_id)

    assert counts["completed"] == 3
    assert repository.get_campaign(campaign.campaign_id).status == CampaignStatus.COMPLETED


def test_runner_retries_then_fails(repository, campaign):
    repository.enqueue(
        campaign.campaign_id,
        "always-fails",
        {"number": 1},
        max_attempts=2,
    )

    def fail(_payload):
        raise RuntimeError("provider unavailable")

    runner = CampaignRunner(repository, fail, worker_id="worker-1")
    counts = runner.run(campaign.campaign_id)

    assert counts["failed"] == 1
    assert repository.get_campaign(campaign.campaign_id).status == CampaignStatus.FAILED
    event_types = [
        event["event_type"] for event in repository.list_audit_events(campaign.campaign_id)
    ]
    assert "work_item.retry_scheduled" in event_types
    assert "work_item.failed" in event_types
    assert repository.verify_audit_chain(campaign.campaign_id)


def test_audit_chain_detects_tampering(repository, campaign):
    repository.transition_campaign(campaign.campaign_id, CampaignStatus.VALIDATED)
    assert repository.verify_audit_chain(campaign.campaign_id)

    with closing(sqlite3.connect(repository.database_path)) as connection, connection:
        connection.execute(
            """
            UPDATE audit_events SET event_json = '{"tampered":true}'
            WHERE event_id = (
                SELECT event_id FROM audit_events
                WHERE campaign_id = ? LIMIT 1
            )
            """,
            (str(campaign.campaign_id),),
        )

    assert repository.verify_audit_chain(campaign.campaign_id) is False


def test_audit_events_include_actor_identity(tmp_path):
    repository = SQLiteCampaignRepository(
        tmp_path / "actor.db",
        actor_id="operator@example.test",
        actor_role="campaign_operator",
    )
    campaign = Campaign(
        name="actor audit",
        provider="mock",
        model="mock",
        authorization_reference="AUTH",
    )
    repository.create_campaign(campaign)
    event = repository.list_audit_events(campaign.campaign_id)[0]["event"]
    assert event["actor_id"] == "operator@example.test"
    assert event["actor_role"] == "campaign_operator"
