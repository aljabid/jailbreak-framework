import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import _build_judge_model, _build_model
from models.local_model import LocalModel
from utils.config import Config
from utils.logger import AttackRecordLogger, JBFLogger


class TestConfig:
    def test_boolean_env_overrides_are_coerced(self, monkeypatch):
        monkeypatch.setenv("JBF_OUTPUT_SAVE_ALL_RESPONSES", "false")
        monkeypatch.setenv("JBF_LOGGING_CONSOLE", "0")
        cfg = Config(config_file="config.yaml")

        assert cfg.save_all_responses is False
        assert cfg.console_logging is False

    def test_numeric_env_overrides_are_coerced(self, monkeypatch):
        monkeypatch.setenv("JBF_SCORING_HIGH_THRESHOLD", "0.72")
        cfg = Config(config_file="config.yaml")

        assert cfg.high_threshold == 0.72

    def test_cli_rejects_invalid_config(self, tmp_path):
        from click.testing import CliRunner

        from main import cli

        path = tmp_path / "invalid.yaml"
        path.write_text("model:\n  temperature: 9\n")
        result = CliRunner().invoke(cli, ["--config", str(path), "list-strategies"])

        assert result.exit_code != 0
        assert "Invalid configuration" in result.output


class TestBackendBuilders:
    def setup_method(self):
        self.cfg = Config(config_file="config.yaml")

    def test_mock_model_builder_returns_local_mock(self):
        model = _build_model(self.cfg, mock=True)

        assert isinstance(model, LocalModel)
        assert model.mode == "mock"

    def test_local_huggingface_model_builder(self):
        model = _build_model(
            self.cfg,
            mock=False,
            provider="local",
            model_name="test-model",
            local_mode="huggingface",
        )

        assert isinstance(model, LocalModel)
        assert model.mode == "huggingface"
        assert model.model_name == "test-model"

    def test_judge_model_builder_uses_mock_in_mock_runs(self):
        judge = _build_judge_model(self.cfg, mock=True)

        assert isinstance(judge, LocalModel)
        assert judge.mode == "mock"


class TestAttackRecordMetadata:
    def test_run_metadata_is_persisted(self, tmp_path):
        results_file = tmp_path / "results.json"
        logger = AttackRecordLogger(
            str(results_file),
            run_metadata={"provider": "mock", "model_name": "mock"},
        )

        record = {
            "strategy": "roleplay",
            "success": False,
            "raw_response": "nope",
        }
        logger.save(record)

        records = logger.all_records()
        assert len(records) == 1
        assert records[0]["session_id"] == JBFLogger.SESSION_ID
        assert records[0]["run_metadata"]["provider"] == "mock"

    def test_result_write_is_atomic_and_leaves_no_temp_files(self, tmp_path):
        results_file = tmp_path / "results.json"
        logger = AttackRecordLogger(str(results_file))
        logger.save({"strategy": "roleplay", "success": False})

        assert results_file.exists()
        assert list(tmp_path.glob(".results.json.*.tmp")) == []
