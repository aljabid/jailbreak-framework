import sqlite3
from contextlib import closing

from application.campaigns import CampaignRunner
from application.policies import BudgetPolicy
from application.rate_limits import TokenBucketRateLimiter
from domain.models import Campaign, CampaignStatus
from persistence.sqlite import SCHEMA_VERSION, SQLiteCampaignRepository


def _campaign(repository):
    campaign = Campaign(
        name="budget test",
        provider="mock",
        model="mock",
        authorization_reference="AUTH-1",
    )
    repository.create_campaign(campaign)
    return campaign


def test_request_budget_pauses_with_queued_work(tmp_path):
    repository = SQLiteCampaignRepository(tmp_path / "campaigns.db")
    campaign = _campaign(repository)
    for number in range(3):
        repository.enqueue(campaign.campaign_id, str(number), {"number": number})

    runner = CampaignRunner(
        repository,
        lambda payload: {"response_tokens": 5, "value": payload["number"]},
        worker_id="budget-worker",
        budget=BudgetPolicy(max_requests=1),
    )
    counts = runner.run(campaign.campaign_id)

    assert counts["completed"] == 1
    assert counts["queued"] == 2
    assert counts["budget_exhausted"] == 1
    assert counts["budget_reason"].startswith("request budget")
    assert repository.get_campaign(campaign.campaign_id).status == CampaignStatus.PAUSED


def test_cancelling_mid_run_stops_further_work_and_status_stays_cancelled(tmp_path):
    """Regression test for a real bug: run()'s loop used to check campaign status
    only once, before the loop started -- a cancellation issued by another caller
    while a campaign was actively running had no effect on the in-flight run(),
    which kept claiming and completing every remaining queued item anyway."""
    repository = SQLiteCampaignRepository(tmp_path / "campaigns.db")
    campaign = _campaign(repository)
    for number in range(5):
        repository.enqueue(campaign.campaign_id, str(number), {"number": number})
    repository.transition_campaign(campaign.campaign_id, CampaignStatus.VALIDATED)
    repository.transition_campaign(campaign.campaign_id, CampaignStatus.RUNNING)

    processed = []

    def processor(payload):
        processed.append(payload["number"])
        if len(processed) == 1:
            # Simulate a cancellation request arriving from another caller
            # (e.g. the wrapper service's DELETE /campaigns/{id} endpoint)
            # while this run() is still mid-loop.
            repository.transition_campaign(campaign.campaign_id, CampaignStatus.CANCELLED)
        return {"response_tokens": 1, "value": payload["number"]}

    runner = CampaignRunner(repository, processor, worker_id="cancel-worker")
    counts = runner.run(campaign.campaign_id, recover=False)

    assert len(processed) == 1, "run() must stop claiming work once cancelled, not drain the queue"
    assert counts["completed"] == 1
    assert counts["queued"] == 4
    final = repository.get_campaign(campaign.campaign_id)
    assert final.status == CampaignStatus.CANCELLED, "run() must not overwrite a cancellation with COMPLETED/FAILED"


def test_usage_is_persisted_and_aggregated(tmp_path):
    repository = SQLiteCampaignRepository(tmp_path / "campaigns.db")
    campaign = _campaign(repository)
    repository.enqueue(campaign.campaign_id, "one", {"number": 1})

    runner = CampaignRunner(
        repository,
        lambda _payload: {
            "response_tokens": 123,
            "estimated_cost_usd": 0.0042,
        },
        worker_id="usage-worker",
    )
    runner.run(campaign.campaign_id)

    assert repository.campaign_usage(campaign.campaign_id) == {
        "requests": 1,
        "tokens": 123,
        "cost_usd": 0.0042,
    }


def test_schema_migrates_existing_version_one_database(tmp_path):
    path = tmp_path / "legacy.db"
    SQLiteCampaignRepository(path)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("UPDATE schema_metadata SET value = '1' WHERE key = 'schema_version'")
        connection.execute("ALTER TABLE campaign_work_items RENAME TO old_work_items")
        connection.execute(
            """
            CREATE TABLE campaign_work_items (
                work_item_id TEXT PRIMARY KEY,
                campaign_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL,
                worker_id TEXT,
                last_error TEXT,
                result_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(campaign_id, idempotency_key)
            )
            """
        )
        connection.execute("DROP TABLE old_work_items")

    SQLiteCampaignRepository(path)
    with closing(sqlite3.connect(path)) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(campaign_work_items)")}
        version = connection.execute(
            "SELECT value FROM schema_metadata WHERE key = 'schema_version'"
        ).fetchone()[0]
    assert {"tokens_used", "cost_usd"} <= columns
    assert int(version) == SCHEMA_VERSION


def test_token_bucket_waits_when_capacity_is_exhausted():
    now = [0.0]
    waits = []

    def clock():
        return now[0]

    def sleep(seconds):
        waits.append(seconds)
        now[0] += seconds

    limiter = TokenBucketRateLimiter(
        requests_per_second=2,
        burst=1,
        clock=clock,
        sleeper=sleep,
    )
    limiter.acquire()
    limiter.acquire()

    assert waits == [0.5]
