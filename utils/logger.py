import json
import logging
import logging.handlers
import os
import sys
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .redaction import redact_text, redact_value


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record), include_pii=True)


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if hasattr(record, "operation"):
            entry["operation"] = record.operation
        if hasattr(record, "operation_id"):
            entry["operation_id"] = record.operation_id
        if hasattr(record, "strategy"):
            entry["strategy"] = record.strategy
        if hasattr(record, "model"):
            entry["model"] = record.model
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(redact_value(entry, include_pii=True))


class JBFLogger:
    SESSION_ID: str = str(uuid.uuid4())[:8]

    def __init__(
        self,
        log_level: str = "INFO",
        log_file: str | None = "outputs/logs.txt",
        console: bool = True,
        json_file: str | None = "outputs/logs.jsonl",
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
    ):
        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
        self.log_file = Path(log_file) if log_file else None
        self.json_file = Path(json_file) if json_file else None
        self.console = console

        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
        if self.json_file:
            self.json_file.parent.mkdir(parents=True, exist_ok=True)

        self._configure_root_logger(max_bytes, backup_count)

    def _configure_root_logger(self, max_bytes: int, backup_count: int) -> None:
        root = logging.getLogger()
        root.setLevel(self.log_level)
        root.handlers.clear()

        fmt = f"[%(asctime)s] [%(levelname)-8s] [session:{self.SESSION_ID}] %(name)s — %(message)s"
        date_fmt = "%Y-%m-%d %H:%M:%S"
        formatter = RedactingFormatter(fmt, datefmt=date_fmt)

        if self.console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            console_handler.setLevel(self.log_level)
            root.addHandler(console_handler)

        if self.log_file:
            file_handler = logging.handlers.RotatingFileHandler(
                self.log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(self.log_level)
            root.addHandler(file_handler)

        if self.json_file:
            json_handler = logging.handlers.RotatingFileHandler(
                self.json_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            json_handler.setFormatter(JSONFormatter())
            json_handler.setLevel(self.log_level)
            root.addHandler(json_handler)

    @staticmethod
    def get(name: str) -> logging.Logger:

        return logging.getLogger(name)

    @classmethod
    def session_id(cls) -> str:
        return cls.SESSION_ID

    @staticmethod
    @contextmanager
    def operation(operation_name: str, logger_obj: logging.Logger | None = None, **kwargs):

        if logger_obj is None:
            logger_obj = logging.getLogger("jbf")

        operation_id = str(uuid.uuid4())[:8]
        extra_msg = ", ".join(f"{k}={v}" for k, v in kwargs.items())

        logger_obj.info(f"[START] {operation_name} ({operation_id}) — {extra_msg}")
        start_time = datetime.now(timezone.utc)

        try:
            yield operation_id
        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger_obj.error(
                f"[FAILED] {operation_name} ({operation_id}) failed after {duration:.2f}s: {e}",
                exc_info=True,
            )
            raise
        else:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger_obj.info(f"[END] {operation_name} ({operation_id}) completed in {duration:.2f}s")


class AttackRecordLogger:
    def __init__(
        self,
        results_file: str = "outputs/results.json",
        run_metadata: dict | None = None,
        redact_persisted_secrets: bool = True,
    ):
        self.results_file = Path(results_file)
        self.results_file.parent.mkdir(parents=True, exist_ok=True)
        self._records: list[dict] = []
        self.run_metadata = run_metadata or {}
        self.redact_persisted_secrets = redact_persisted_secrets
        self._load_existing()

    def _load_existing(self) -> None:
        if self.results_file.exists():
            try:
                with open(self.results_file, encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._records = data
            except (OSError, json.JSONDecodeError):
                self._records = []

    def save(self, record: dict) -> None:

        record.setdefault("session_id", JBFLogger.SESSION_ID)
        record.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        if self.run_metadata and "run_metadata" not in record:
            record["run_metadata"] = self.run_metadata

        stored = (
            redact_value(record, include_pii=False) if self.redact_persisted_secrets else record
        )
        self._records.append(stored)
        self._flush()

    def save_batch(self, records: list) -> None:

        ts = datetime.now(timezone.utc).isoformat()
        for r in records:
            r.setdefault("session_id", JBFLogger.SESSION_ID)
            r.setdefault("timestamp", ts)
            if self.run_metadata and "run_metadata" not in r:
                r["run_metadata"] = self.run_metadata
            stored = redact_value(r, include_pii=False) if self.redact_persisted_secrets else r
            self._records.append(stored)
        self._flush()

    def _flush(self) -> None:

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.results_file.parent,
                prefix=f".{self.results_file.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                json.dump(self._records, handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.results_file)
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()

    @property
    def record_count(self) -> int:
        return len(self._records)

    def all_records(self) -> list:
        return list(self._records)
