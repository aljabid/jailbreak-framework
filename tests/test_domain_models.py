from uuid import uuid4

import pytest
from pydantic import ValidationError

from domain.models import AttackCase, ModelRequest, ModelResponse, RiskAssessment
from domain.providers import ModelProvider
from models.local_model import LocalModel


def test_model_request_rejects_blank_prompt():
    with pytest.raises(ValidationError):
        ModelRequest(prompt="   ")


def test_model_request_rejects_invalid_limits():
    with pytest.raises(ValidationError):
        ModelRequest(prompt="hello", max_tokens=0)
    with pytest.raises(ValidationError):
        ModelRequest(prompt="hello", temperature=2.1)


def test_domain_models_reject_unknown_fields():
    with pytest.raises(ValidationError):
        ModelRequest(prompt="hello", accidental_field=True)


def test_model_response_total_tokens():
    request_id = uuid4()
    response = ModelResponse(
        request_id=request_id,
        provider="mock",
        model="mock-model",
        text="response",
        prompt_tokens=4,
        completion_tokens=6,
    )
    assert response.total_tokens == 10
    assert response.schema_version == "1.0"


def test_attack_case_has_stable_identity():
    case = AttackCase(
        strategy="roleplay",
        base_prompt_id="prompt-1",
        base_prompt_text="base",
        adversarial_prompt="transformed",
    )
    assert case.attack_id
    assert case.strategy_version == "1.0"


def test_risk_assessment_enforces_bounded_values():
    with pytest.raises(ValidationError):
        RiskAssessment(
            attack_id=uuid4(),
            scoring_model="composite",
            scoring_version="1.0",
            likelihood=1.1,
            impact=0.5,
            evidence_confidence=0.8,
            risk_score=0.4,
            risk_level="Medium",
        )


def test_local_model_implements_provider_contract():
    provider = LocalModel(mode="mock", mock_success_rate=1.0)
    assert isinstance(provider, ModelProvider)
    response = provider.complete(ModelRequest(prompt="hello"))
    assert response.provider == "mock"
    assert response.text
