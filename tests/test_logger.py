import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from utils.logger import AttackRecordLogger, JBFLogger, JSONFormatter


class TestJSONFormatter:
    def test_optional_fields_included_when_present(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="jbf.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        record.operation = "run_campaign"
        record.operation_id = "abc123"
        record.strategy = "roleplay"
        record.model = "gpt-4"

        entry = json.loads(formatter.format(record))

        assert entry["operation"] == "run_campaign"
        assert entry["operation_id"] == "abc123"
        assert entry["strategy"] == "roleplay"
        assert entry["model"] == "gpt-4"

    def test_optional_fields_omitted_when_absent(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="jbf.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )

        entry = json.loads(formatter.format(record))

        assert "operation" not in entry
        assert "operation_id" not in entry
        assert "strategy" not in entry
        assert "model" not in entry

    def test_exception_info_included(self):
        formatter = JSONFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            record = logging.LogRecord(
                name="jbf.test",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="failed",
                args=(),
                exc_info=sys.exc_info(),
            )

        entry = json.loads(formatter.format(record))

        assert "exception" in entry
        assert "ValueError" in entry["exception"]


class TestJBFLoggerBasics:
    def test_get_returns_named_logger(self):
        log = JBFLogger.get("jbf.named")
        assert isinstance(log, logging.Logger)
        assert log.name == "jbf.named"

    def test_session_id_is_stable_string(self):
        first = JBFLogger.session_id()
        second = JBFLogger.session_id()
        assert first == second
        assert isinstance(first, str)
        assert len(first) > 0


class TestJBFLoggerOperationContext:
    def test_operation_success_logs_start_and_end(self, caplog):
        target_logger = logging.getLogger("jbf.op.success")
        target_logger.propagate = True
        with (
            caplog.at_level(logging.INFO, logger="jbf.op.success"),
            JBFLogger.operation("do_thing", target_logger, seed=42) as operation_id,
        ):
            assert isinstance(operation_id, str)

        messages = [record.message for record in caplog.records]
        assert any("[START] do_thing" in m and "seed=42" in m for m in messages)
        assert any("[END] do_thing" in m for m in messages)

    def test_operation_failure_logs_failed_and_reraises(self, caplog):
        target_logger = logging.getLogger("jbf.op.failure")
        target_logger.propagate = True
        with (
            caplog.at_level(logging.INFO, logger="jbf.op.failure"),
            pytest.raises(RuntimeError, match="kaboom"),
            JBFLogger.operation("do_thing", target_logger),
        ):
            raise RuntimeError("kaboom")

        messages = [record.message for record in caplog.records]
        assert any("[FAILED] do_thing" in m and "kaboom" in m for m in messages)
        assert not any("[END] do_thing" in m for m in messages)

    def test_operation_defaults_to_jbf_logger(self):
        with JBFLogger.operation("unlogged_target") as operation_id:
            assert isinstance(operation_id, str)


class TestAttackRecordLoggerPersistence:
    def test_load_existing_recovers_from_corrupt_file(self, tmp_path):
        results_file = tmp_path / "results.json"
        results_file.write_text("{ not valid json", encoding="utf-8")

        recorder = AttackRecordLogger(results_file=str(results_file))

        assert recorder.all_records() == []
        assert recorder.record_count == 0

    def test_load_existing_recovers_from_non_list_json(self, tmp_path):
        results_file = tmp_path / "results.json"
        results_file.write_text('{"not": "a list"}', encoding="utf-8")

        recorder = AttackRecordLogger(results_file=str(results_file))

        assert recorder.all_records() == []

    def test_save_batch_persists_all_records_with_defaults(self, tmp_path):
        results_file = tmp_path / "results.json"
        recorder = AttackRecordLogger(
            results_file=str(results_file),
            run_metadata={"seed": 1},
        )

        recorder.save_batch([{"prompt": "a"}, {"prompt": "b", "timestamp": "explicit"}])

        assert recorder.record_count == 2
        stored = json.loads(results_file.read_text(encoding="utf-8"))
        assert stored[0]["session_id"] == JBFLogger.SESSION_ID
        assert stored[0]["run_metadata"] == {"seed": 1}
        assert stored[1]["timestamp"] == "explicit"

    def test_flush_cleans_up_temp_file_on_serialization_error(self, tmp_path):
        results_file = tmp_path / "results.json"
        recorder = AttackRecordLogger(results_file=str(results_file))

        with pytest.raises(TypeError):
            recorder.save({"bad": object()})

        leftover_temp_files = list(tmp_path.glob(f".{results_file.name}.*.tmp"))
        assert leftover_temp_files == []
        assert not results_file.exists()
