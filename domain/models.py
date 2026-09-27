from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION: Literal["1.0"] = "1.0"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    schema_version: Literal["1.0"] = SCHEMA_VERSION


class CampaignStatus(str, Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class WorkItemStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ReviewDecision(str, Enum):
    CONFIRMED = "confirmed"
    FALSE_POSITIVE = "false_positive"
    ACCEPTED_RISK = "accepted_risk"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"


class ModelRequest(DomainModel):
    request_id: UUID = Field(default_factory=uuid4)
    campaign_id: UUID | None = None
    prompt: str = Field(min_length=1)
    system_prompt: str | None = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, gt=0)
    timeout_seconds: float = Field(default=30.0, gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("prompt")
    @classmethod
    def prompt_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be blank")
        return value


class ModelResponse(DomainModel):
    request_id: UUID
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    text: str
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    finish_reason: str | None = None
    provider_request_id: str | None = None
    received_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class AttackCase(DomainModel):
    attack_id: UUID = Field(default_factory=uuid4)
    campaign_id: UUID | None = None
    strategy: str = Field(min_length=1)
    strategy_version: str = Field(default="1.0", min_length=1)
    base_prompt_id: str = Field(min_length=1)
    base_prompt_text: str
    adversarial_prompt: str = Field(min_length=1)
    category: str = "general"
    base_severity: str = "unknown"
    seed: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationResult(DomainModel):
    evaluation_id: UUID = Field(default_factory=uuid4)
    attack_id: UUID
    evaluator: str = Field(min_length=1)
    evaluator_version: str = Field(min_length=1)
    outcome: Literal[
        "refusal",
        "safe_transformation",
        "benign_information",
        "partial_compliance",
        "full_compliance",
        "system_prompt_leak",
        "tool_misuse",
        "indeterminate",
    ]
    success: bool
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    reasoning: str = ""


class RiskAssessment(DomainModel):
    assessment_id: UUID = Field(default_factory=uuid4)
    attack_id: UUID
    scoring_model: str = Field(min_length=1)
    scoring_version: str = Field(min_length=1)
    likelihood: float = Field(ge=0.0, le=1.0)
    impact: float = Field(ge=0.0, le=1.0)
    evidence_confidence: float = Field(ge=0.0, le=1.0)
    risk_score: float = Field(ge=0.0, le=1.0)
    risk_level: Literal["None", "Low", "Medium", "High", "Critical"]
    rationale: str = ""


class Campaign(DomainModel):
    campaign_id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=200)
    status: CampaignStatus = CampaignStatus.DRAFT
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    authorization_reference: str = Field(min_length=1, max_length=500)
    configuration: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class CampaignWorkItem(DomainModel):
    work_item_id: UUID = Field(default_factory=uuid4)
    campaign_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=500)
    status: WorkItemStatus = WorkItemStatus.QUEUED
    payload: dict[str, Any]
    attempts: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, gt=0)
    worker_id: str | None = None
    last_error: str | None = None
    result: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class FindingReview(DomainModel):
    review_id: UUID = Field(default_factory=uuid4)
    work_item_id: UUID
    campaign_id: UUID
    decision: ReviewDecision
    reason: str = Field(min_length=1, max_length=4000)
    reviewer_id: str = Field(min_length=1, max_length=300)
    reviewer_role: str = Field(min_length=1, max_length=100)
    supersedes_review_id: UUID | None = None
    created_at: datetime = Field(default_factory=utc_now)
