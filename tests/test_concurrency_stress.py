import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

from domain.models import Campaign, CampaignStatus, WorkItemStatus
from persistence.sqlite import SQLiteCampaignRepository

WORKER_COUNT = 8
WORK_ITEM_COUNT = 200


def _running_campaign(repository, name="stress test"):
    campaign = Campaign(
        name=name,
        provider="mock",
        model="mock",
        authorization_reference="AUTH-STRESS-1",
    )
    repository.create_campaign(campaign)
    repository.transition_campaign(campaign.campaign_id, CampaignStatus.VALIDATED)
    repository.transition_campaign(campaign.campaign_id, CampaignStatus.RUNNING)
    return campaign


def _drain(repository, campaign_id, worker_id):
    claimed_ids = []
    while True:
        item = repository.claim_next(campaign_id, worker_id)
        if item is None:
            return claimed_ids
        claimed_ids.append(str(item.work_item_id))
        repository.complete_item(item.work_item_id, {"success": True, "worker": worker_id})


class TestConcurrentWorkClaiming:
    def test_each_work_item_is_claimed_by_exactly_one_worker(self, tmp_path):
        repository = SQLiteCampaignRepository(tmp_path / "campaigns.db")
        campaign = _running_campaign(repository)
        for number in range(WORK_ITEM_COUNT):
            repository.enqueue(campaign.campaign_id, str(number), {"number": number})

        with ThreadPoolExecutor(max_workers=WORKER_COUNT) as pool:
            futures = [
                pool.submit(_drain, repository, campaign.campaign_id, f"worker-{index}")
                for index in range(WORKER_COUNT)
            ]
            per_worker_claims = [future.result(timeout=60) for future in futures]

        all_claimed = [work_item_id for claims in per_worker_claims for work_item_id in claims]

        assert len(all_claimed) == WORK_ITEM_COUNT
        assert len(set(all_claimed)) == WORK_ITEM_COUNT

        counts = repository.campaign_counts(campaign.campaign_id)
        assert counts["completed"] == WORK_ITEM_COUNT
        assert counts["queued"] == 0
        assert counts["running"] == 0

        for item in repository.list_work_items(campaign.campaign_id):
            assert item.attempts == 1
            assert item.status == WorkItemStatus.COMPLETED
            assert item.worker_id is None

    def test_database_integrity_holds_after_concurrent_writes(self, tmp_path):
        db_path = tmp_path / "campaigns.db"
        repository = SQLiteCampaignRepository(db_path)
        campaign = _running_campaign(repository)
        for number in range(WORK_ITEM_COUNT):
            repository.enqueue(campaign.campaign_id, str(number), {"number": number})

        with ThreadPoolExecutor(max_workers=WORKER_COUNT) as pool:
            futures = [
                pool.submit(_drain, repository, campaign.campaign_id, f"worker-{index}")
                for index in range(WORKER_COUNT)
            ]
            for future in futures:
                future.result(timeout=60)

        with closing(sqlite3.connect(db_path)) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        assert integrity == "ok"

    def test_audit_chain_stays_valid_under_concurrent_completions(self, tmp_path):
        repository = SQLiteCampaignRepository(tmp_path / "campaigns.db")
        campaign = _running_campaign(repository)
        for number in range(WORK_ITEM_COUNT):
            repository.enqueue(campaign.campaign_id, str(number), {"number": number})

        with ThreadPoolExecutor(max_workers=WORKER_COUNT) as pool:
            futures = [
                pool.submit(_drain, repository, campaign.campaign_id, f"worker-{index}")
                for index in range(WORKER_COUNT)
            ]
            for future in futures:
                future.result(timeout=60)

        assert repository.verify_audit_chain(campaign.campaign_id) is True


class TestConcurrentIdempotentEnqueue:
    def test_racing_enqueue_with_same_key_creates_one_work_item(self, tmp_path):
        repository = SQLiteCampaignRepository(tmp_path / "campaigns.db")
        campaign = _running_campaign(repository, name="idempotency race")

        barrier = threading.Barrier(WORKER_COUNT)

        def _enqueue_same_key(index):
            barrier.wait(timeout=10)
            return repository.enqueue(
                campaign.campaign_id,
                "shared-key",
                {"attempt": index},
            )

        with ThreadPoolExecutor(max_workers=WORKER_COUNT) as pool:
            futures = [pool.submit(_enqueue_same_key, index) for index in range(WORKER_COUNT)]
            results = [future.result(timeout=30) for future in futures]

        work_item_ids = {str(result.work_item_id) for result in results}
        assert len(work_item_ids) == 1

        counts = repository.campaign_counts(campaign.campaign_id)
        assert counts["total"] == 1
