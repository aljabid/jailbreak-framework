from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from domain.models import CampaignStatus
from observability.metrics import GLOBAL_METRICS
from persistence.repositories import CampaignRepository

from .policies import BudgetPolicy

WorkProcessor = Callable[[dict[str, Any]], dict[str, Any]]


class CampaignRunner:
    def __init__(
        self,
        repository: CampaignRepository,
        processor: WorkProcessor,
        worker_id: str,
        budget: BudgetPolicy | None = None,
    ):
        if not worker_id.strip():
            raise ValueError("worker_id must not be blank")
        self.repository = repository
        self.processor = processor
        self.worker_id = worker_id
        self.budget = budget or BudgetPolicy()

    def run(self, campaign_id: UUID, recover: bool = True) -> dict[str, Any]:
        campaign = self.repository.get_campaign(campaign_id)
        if campaign is None:
            raise KeyError(f"Campaign not found: {campaign_id}")

        if recover:
            self.repository.recover_interrupted(campaign_id)

        if campaign.status == CampaignStatus.DRAFT:
            campaign = self.repository.transition_campaign(campaign_id, CampaignStatus.VALIDATED)
        if campaign.status in (CampaignStatus.VALIDATED, CampaignStatus.PAUSED):
            campaign = self.repository.transition_campaign(campaign_id, CampaignStatus.RUNNING)
        if campaign.status != CampaignStatus.RUNNING:
            return self.repository.campaign_counts(campaign_id)

        budget_reason: str | None = None
        while True:
            # Re-read status each iteration so a cancellation issued by another
            # caller mid-run (via repository.transition_campaign(..., CANCELLED))
            # actually stops work claiming further items -- without this check the
            # loop only looked at status once, before the loop started, so a
            # "cancel" while a campaign was running would flip the stored status
            # but the background run() would keep processing every remaining
            # queued item regardless.
            current_status = self.repository.get_campaign(campaign_id)
            if current_status is None or current_status.status != CampaignStatus.RUNNING:
                break
            counts = self.repository.campaign_counts(campaign_id)
            if counts["queued"] == 0:
                break
            usage = self.repository.campaign_usage(campaign_id)
            budget_reason = self.budget.exceeded_reason(usage, counts)
            if budget_reason:
                self.repository.transition_campaign(campaign_id, CampaignStatus.PAUSED)
                counts["budget_exhausted"] = 1
                break
            item = self.repository.claim_next(campaign_id, self.worker_id)
            if item is None:
                break
            try:
                result = self.processor(item.payload)
                if not isinstance(result, dict):
                    raise TypeError("Campaign processor must return a dictionary")
                self.repository.complete_item(item.work_item_id, result)
                GLOBAL_METRICS.increment(
                    "jbf_campaign_work_items",
                    labels={"status": "completed"},
                )
            except Exception as exc:
                self.repository.fail_item(
                    item.work_item_id,
                    error=f"{type(exc).__name__}: {exc}",
                    retry=True,
                )
                GLOBAL_METRICS.increment(
                    "jbf_campaign_work_items",
                    labels={"status": "processor_error"},
                )

        final_counts: dict[str, Any] = dict(self.repository.campaign_counts(campaign_id))
        if budget_reason:
            final_counts["budget_exhausted"] = 1
            final_counts["budget_reason"] = budget_reason
        current = self.repository.get_campaign(campaign_id)
        if (
            current is not None
            and current.status == CampaignStatus.RUNNING
            and final_counts["queued"] == 0
            and final_counts["running"] == 0
        ):
            terminal = (
                CampaignStatus.FAILED if final_counts["failed"] > 0 else CampaignStatus.COMPLETED
            )
            self.repository.transition_campaign(campaign_id, terminal)
        GLOBAL_METRICS.set_gauge(
            "jbf_campaign_queued_items",
            float(final_counts["queued"]),
            labels={"campaign_id": str(campaign_id)},
        )
        return final_counts
