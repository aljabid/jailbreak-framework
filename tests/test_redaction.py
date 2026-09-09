import json
import logging

from domain.models import Campaign, CampaignStatus
from persistence.sqlite import SQLiteCampaignRepository
from utils.logger import AttackRecordLogger, JBFLogger
from utils.redaction import markdown_inline, redact_text, redact_value
from utils.reporter import Reporter

SECRET = "sk-proj-abcdefghijklmnopqrstuv"


def test_secret_redaction_is_recursive_and_non_mutating():
    original = {"nested": [{"token": SECRET}], "safe": "value"}
    result = redact_value(original)
    assert SECRET not in json.dumps(result)
    assert original["nested"][0]["token"] == SECRET


def test_pii_redaction_is_explicit():
    value = "Contact analyst@example.test or 312-555-1212"
    assert "analyst@example.test" in redact_text(value, include_pii=False)
    redacted = redact_text(value, include_pii=True)
    assert "analyst@example.test" not in redacted
    assert "312-555-1212" not in redacted


def test_markdown_content_is_redacted_and_neutralized():
    value = markdown_inline(f"`value|x`\n{SECRET}")
    assert SECRET not in value
    assert "\\|" in value
    assert "\n" not in value


def test_attack_record_never_persists_api_key(tmp_path):
    path = tmp_path / "results.json"
    logger = AttackRecordLogger(str(path))
    logger.save({"raw_response": f"accidentally returned {SECRET}"})
    assert SECRET not in path.read_text()


def test_logs_redact_secrets_and_pii(tmp_path):
    path = tmp_path / "logs.txt"
    JBFLogger(
        log_level="INFO",
        log_file=str(path),
        json_file=None,
        console=False,
    )
    logging.getLogger("redaction-test").info("key=%s contact=%s", SECRET, "analyst@example.test")
    logging.shutdown()
    content = path.read_text()
    assert SECRET not in content
    assert "analyst@example.test" not in content


def test_database_results_redact_secrets(tmp_path):
    repository = SQLiteCampaignRepository(tmp_path / "campaigns.db")
    campaign = Campaign(
        name="redaction",
        provider="mock",
        model="mock",
        authorization_reference="AUTH",
    )
    repository.create_campaign(campaign)
    repository.enqueue(campaign.campaign_id, "one", {"prompt": "safe"})
    repository.transition_campaign(campaign.campaign_id, CampaignStatus.VALIDATED)
    repository.transition_campaign(campaign.campaign_id, CampaignStatus.RUNNING)
    item = repository.claim_next(campaign.campaign_id, "worker")
    repository.complete_item(item.work_item_id, {"raw_response": SECRET})
    assert SECRET.encode() not in (tmp_path / "campaigns.db").read_bytes()


def test_markdown_report_redacts_and_escapes(tmp_path):
    path = Reporter(str(tmp_path)).save_markdown_report(
        [
            {
                "strategy": "roleplay",
                "risk_level": "High",
                "risk_score": 0.8,
                "success": True,
                "adversarial_prompt": f"`unsafe|cell` {SECRET}",
                "raw_response": "analyst@example.test",
                "eval_reasoning": "line\nbreak",
            }
        ],
        {
            "total_attacks": 1,
            "total_success": 1,
            "success_rate": 1.0,
            "average_risk_score": 0.8,
            "by_strategy": {},
            "by_risk_level": {},
        },
    )
    content = path.read_text()
    assert SECRET not in content
    assert "analyst@example.test" not in content
