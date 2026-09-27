from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from domain.models import (
    Campaign,
    CampaignStatus,
    CampaignWorkItem,
    FindingReview,
    ReviewDecision,
)


class CampaignRepository(Protocol):
    def create_campaign(self, campaign: Campaign) -> Campaign: ...

    def get_campaign(self, campaign_id: UUID) -> Campaign | None: ...

    def transition_campaign(self, campaign_id: UUID, new_status: CampaignStatus) -> Campaign: ...

    def enqueue(
        self,
        campaign_id: UUID,
        idempotency_key: str,
        payload: dict[str, Any],
        max_attempts: int = 3,
    ) -> CampaignWorkItem: ...

    def claim_next(self, campaign_id: UUID, worker_id: str) -> CampaignWorkItem | None: ...

    def complete_item(self, work_item_id: UUID, result: dict[str, Any]) -> CampaignWorkItem: ...

    def fail_item(self, work_item_id: UUID, error: str, retry: bool) -> CampaignWorkItem: ...

    def recover_interrupted(self, campaign_id: UUID) -> int: ...

    def campaign_counts(self, campaign_id: UUID) -> dict[str, int]: ...

    def campaign_usage(self, campaign_id: UUID) -> dict[str, int | float]: ...

    def list_findings(self, campaign_id: UUID) -> list[dict[str, Any]]: ...

    def review_finding(
        self,
        work_item_id: UUID,
        decision: ReviewDecision,
        reason: str,
    ) -> FindingReview: ...
