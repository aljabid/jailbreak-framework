from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from domain.models import (
    Campaign,
    CampaignStatus,
    CampaignWorkItem,
    FindingReview,
    ReviewDecision,
    WorkItemStatus,
)
from utils.encryption import ENVELOPE_PREFIX, ArtifactCipher
from utils.redaction import redact_value

SCHEMA_VERSION = 5
AUDIT_GENESIS_HASH = "0" * 64

ALLOWED_TRANSITIONS: dict[CampaignStatus, set[CampaignStatus]] = {
    CampaignStatus.DRAFT: {
        CampaignStatus.VALIDATED,
        CampaignStatus.CANCELLED,
    },
    CampaignStatus.VALIDATED: {
        CampaignStatus.RUNNING,
        CampaignStatus.CANCELLED,
    },
    CampaignStatus.RUNNING: {
        CampaignStatus.PAUSED,
        CampaignStatus.COMPLETED,
        CampaignStatus.CANCELLED,
        CampaignStatus.FAILED,
    },
    CampaignStatus.PAUSED: {
        CampaignStatus.RUNNING,
        CampaignStatus.CANCELLED,
    },
    CampaignStatus.COMPLETED: set(),
    CampaignStatus.CANCELLED: set(),
    CampaignStatus.FAILED: set(),
}


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteCampaignRepository:
    def __init__(
        self,
        database_path: str | Path,
        artifact_cipher: ArtifactCipher | None = None,
        actor_id: str = "system",
        actor_role: str = "system",
    ):
        self.database_path = Path(database_path)
        self.artifact_cipher = artifact_cipher
        self.actor_id = actor_id
        self.actor_role = actor_role
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=30,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @contextmanager
    def _transaction(self, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS campaigns (
                    campaign_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    authorization_reference TEXT NOT NULL,
                    configuration_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS campaign_work_items (
                    work_item_id TEXT PRIMARY KEY,
                    campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id)
                        ON DELETE CASCADE,
                    idempotency_key TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
                    max_attempts INTEGER NOT NULL CHECK (max_attempts > 0),
                    worker_id TEXT,
                    last_error TEXT,
                    result_json TEXT,
                    tokens_used INTEGER NOT NULL DEFAULT 0 CHECK (tokens_used >= 0),
                    cost_usd REAL NOT NULL DEFAULT 0 CHECK (cost_usd >= 0),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(campaign_id, idempotency_key)
                );

                CREATE INDEX IF NOT EXISTS idx_work_campaign_status
                    ON campaign_work_items(campaign_id, status, created_at);

                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    campaign_id TEXT REFERENCES campaigns(campaign_id)
                        ON DELETE CASCADE,
                    event_type TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    previous_hash TEXT,
                    event_hash TEXT
                );

                CREATE TABLE IF NOT EXISTS retention_events (
                    event_id TEXT PRIMARY KEY,
                    campaign_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS finding_reviews (
                    review_id TEXT PRIMARY KEY,
                    work_item_id TEXT NOT NULL REFERENCES campaign_work_items(work_item_id)
                        ON DELETE CASCADE,
                    campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id)
                        ON DELETE CASCADE,
                    decision TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    reviewer_id TEXT NOT NULL,
                    reviewer_role TEXT NOT NULL,
                    supersedes_review_id TEXT REFERENCES finding_reviews(review_id),
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_reviews_work_created
                    ON finding_reviews(work_item_id, created_at);
                """
            )
            existing = connection.execute(
                "SELECT value FROM schema_metadata WHERE key = 'schema_version'"
            ).fetchone()
            existing_version = int(existing["value"]) if existing else 0
            if existing_version > SCHEMA_VERSION:
                raise RuntimeError("Database schema is newer than this application supports")
            self._migrate(connection, existing_version)
            connection.execute(
                """
                INSERT INTO schema_metadata(key, value) VALUES('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(SCHEMA_VERSION),),
            )

    def _migrate(self, connection: sqlite3.Connection, existing_version: int) -> None:

        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(campaign_work_items)").fetchall()
        }
        if "tokens_used" not in columns:
            connection.execute(
                "ALTER TABLE campaign_work_items ADD COLUMN tokens_used INTEGER NOT NULL DEFAULT 0"
            )
        if "cost_usd" not in columns:
            connection.execute(
                "ALTER TABLE campaign_work_items ADD COLUMN cost_usd REAL NOT NULL DEFAULT 0"
            )
        audit_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(audit_events)").fetchall()
        }
        if "previous_hash" not in audit_columns:
            connection.execute("ALTER TABLE audit_events ADD COLUMN previous_hash TEXT")
        if "event_hash" not in audit_columns:
            connection.execute("ALTER TABLE audit_events ADD COLUMN event_hash TEXT")
        if existing_version < 3:
            self._backfill_audit_hashes(connection)

    def create_campaign(self, campaign: Campaign) -> Campaign:
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO campaigns(
                    campaign_id, name, status, provider, model,
                    authorization_reference, configuration_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(campaign.campaign_id),
                    campaign.name,
                    campaign.status.value,
                    campaign.provider,
                    campaign.model,
                    campaign.authorization_reference,
                    json.dumps(campaign.configuration, sort_keys=True),
                    campaign.created_at.isoformat(),
                    campaign.updated_at.isoformat(),
                ),
            )
            self._audit(
                connection,
                campaign.campaign_id,
                "campaign.created",
                {"status": campaign.status.value},
            )
        return campaign

    def get_campaign(self, campaign_id: UUID) -> Campaign | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM campaigns WHERE campaign_id = ?",
                (str(campaign_id),),
            ).fetchone()
        return self._campaign_from_row(row) if row else None

    def transition_campaign(self, campaign_id: UUID, new_status: CampaignStatus) -> Campaign:
        with self._transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT * FROM campaigns WHERE campaign_id = ?",
                (str(campaign_id),),
            ).fetchone()
            if not row:
                raise KeyError(f"Campaign not found: {campaign_id}")
            current = CampaignStatus(row["status"])
            if new_status == current:
                return self._campaign_from_row(row)
            if new_status not in ALLOWED_TRANSITIONS[current]:
                raise ValueError(
                    f"Invalid campaign transition: {current.value} -> {new_status.value}"
                )
            now = _utc_iso()
            connection.execute(
                "UPDATE campaigns SET status = ?, updated_at = ? WHERE campaign_id = ?",
                (new_status.value, now, str(campaign_id)),
            )
            self._audit(
                connection,
                campaign_id,
                "campaign.transitioned",
                {"from": current.value, "to": new_status.value},
            )
            updated = connection.execute(
                "SELECT * FROM campaigns WHERE campaign_id = ?",
                (str(campaign_id),),
            ).fetchone()
        return self._campaign_from_row(updated)

    def enqueue(
        self,
        campaign_id: UUID,
        idempotency_key: str,
        payload: dict[str, Any],
        max_attempts: int = 3,
    ) -> CampaignWorkItem:
        if not idempotency_key.strip():
            raise ValueError("idempotency_key must not be blank")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        now = _utc_iso()
        work_item_id = uuid4()
        with self._transaction(immediate=True) as connection:
            if not connection.execute(
                "SELECT 1 FROM campaigns WHERE campaign_id = ?",
                (str(campaign_id),),
            ).fetchone():
                raise KeyError(f"Campaign not found: {campaign_id}")
            connection.execute(
                """
                INSERT INTO campaign_work_items(
                    work_item_id, campaign_id, idempotency_key, status,
                    payload_json, attempts, max_attempts, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)
                ON CONFLICT(campaign_id, idempotency_key) DO NOTHING
                """,
                (
                    str(work_item_id),
                    str(campaign_id),
                    idempotency_key,
                    WorkItemStatus.QUEUED.value,
                    json.dumps(payload, sort_keys=True),
                    max_attempts,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM campaign_work_items
                WHERE campaign_id = ? AND idempotency_key = ?
                """,
                (str(campaign_id), idempotency_key),
            ).fetchone()
        return self._work_item_from_row(row)

    def claim_next(self, campaign_id: UUID, worker_id: str) -> CampaignWorkItem | None:
        if not worker_id.strip():
            raise ValueError("worker_id must not be blank")
        with self._transaction(immediate=True) as connection:
            campaign = connection.execute(
                "SELECT status FROM campaigns WHERE campaign_id = ?",
                (str(campaign_id),),
            ).fetchone()
            if not campaign:
                raise KeyError(f"Campaign not found: {campaign_id}")
            if campaign["status"] != CampaignStatus.RUNNING.value:
                return None
            row = connection.execute(
                """
                SELECT * FROM campaign_work_items
                WHERE campaign_id = ? AND status = ? AND attempts < max_attempts
                ORDER BY created_at, work_item_id
                LIMIT 1
                """,
                (str(campaign_id), WorkItemStatus.QUEUED.value),
            ).fetchone()
            if not row:
                return None
            now = _utc_iso()
            connection.execute(
                """
                UPDATE campaign_work_items
                SET status = ?, worker_id = ?, attempts = attempts + 1,
                    updated_at = ?
                WHERE work_item_id = ? AND status = ?
                """,
                (
                    WorkItemStatus.RUNNING.value,
                    worker_id,
                    now,
                    row["work_item_id"],
                    WorkItemStatus.QUEUED.value,
                ),
            )
            claimed = connection.execute(
                "SELECT * FROM campaign_work_items WHERE work_item_id = ?",
                (row["work_item_id"],),
            ).fetchone()
        return self._work_item_from_row(claimed)

    def complete_item(self, work_item_id: UUID, result: dict[str, Any]) -> CampaignWorkItem:
        result = redact_value(result, include_pii=False)
        tokens_used = self._result_tokens(result)
        cost_usd = self._result_cost(result)
        with self._transaction(immediate=True) as connection:
            row = self._require_running_item(connection, work_item_id)
            connection.execute(
                """
                UPDATE campaign_work_items
                SET status = ?, result_json = ?, last_error = NULL,
                    worker_id = NULL, tokens_used = ?, cost_usd = ?,
                    updated_at = ?
                WHERE work_item_id = ?
                """,
                (
                    WorkItemStatus.COMPLETED.value,
                    self._serialize_result(work_item_id, result),
                    tokens_used,
                    cost_usd,
                    _utc_iso(),
                    str(work_item_id),
                ),
            )
            self._audit(
                connection,
                UUID(row["campaign_id"]),
                "work_item.completed",
                {"work_item_id": str(work_item_id)},
            )
            updated = connection.execute(
                "SELECT * FROM campaign_work_items WHERE work_item_id = ?",
                (str(work_item_id),),
            ).fetchone()
        return self._work_item_from_row(updated)

    def fail_item(self, work_item_id: UUID, error: str, retry: bool) -> CampaignWorkItem:
        with self._transaction(immediate=True) as connection:
            row = self._require_running_item(connection, work_item_id)
            can_retry = retry and row["attempts"] < row["max_attempts"]
            status = WorkItemStatus.QUEUED if can_retry else WorkItemStatus.FAILED
            connection.execute(
                """
                UPDATE campaign_work_items
                SET status = ?, last_error = ?, worker_id = NULL, updated_at = ?
                WHERE work_item_id = ?
                """,
                (status.value, error[:4000], _utc_iso(), str(work_item_id)),
            )
            self._audit(
                connection,
                UUID(row["campaign_id"]),
                "work_item.retry_scheduled" if can_retry else "work_item.failed",
                {"work_item_id": str(work_item_id), "error": error[:1000]},
            )
            updated = connection.execute(
                "SELECT * FROM campaign_work_items WHERE work_item_id = ?",
                (str(work_item_id),),
            ).fetchone()
        return self._work_item_from_row(updated)

    def recover_interrupted(self, campaign_id: UUID) -> int:
        with self._transaction(immediate=True) as connection:
            cursor = connection.execute(
                """
                UPDATE campaign_work_items
                SET status = ?, worker_id = NULL, updated_at = ?
                WHERE campaign_id = ? AND status = ? AND attempts < max_attempts
                """,
                (
                    WorkItemStatus.QUEUED.value,
                    _utc_iso(),
                    str(campaign_id),
                    WorkItemStatus.RUNNING.value,
                ),
            )
            connection.execute(
                """
                UPDATE campaign_work_items
                SET status = ?, worker_id = NULL,
                    last_error = COALESCE(last_error, 'attempt limit reached during recovery'),
                    updated_at = ?
                WHERE campaign_id = ? AND status = ? AND attempts >= max_attempts
                """,
                (
                    WorkItemStatus.FAILED.value,
                    _utc_iso(),
                    str(campaign_id),
                    WorkItemStatus.RUNNING.value,
                ),
            )
            count = cursor.rowcount
            if count:
                self._audit(
                    connection,
                    campaign_id,
                    "campaign.recovered",
                    {"requeued_items": count},
                )
        return count

    def campaign_counts(self, campaign_id: UUID) -> dict[str, int]:
        counts = {status.value: 0 for status in WorkItemStatus}
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM campaign_work_items
                WHERE campaign_id = ?
                GROUP BY status
                """,
                (str(campaign_id),),
            ).fetchall()
        for row in rows:
            counts[row["status"]] = row["count"]
        counts["total"] = sum(counts.values())
        return counts

    def campaign_usage(self, campaign_id: UUID) -> dict[str, int | float]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE status = ?) AS requests,
                    COALESCE(SUM(tokens_used), 0) AS tokens,
                    COALESCE(SUM(cost_usd), 0.0) AS cost_usd
                FROM campaign_work_items
                WHERE campaign_id = ?
                """,
                (WorkItemStatus.COMPLETED.value, str(campaign_id)),
            ).fetchone()
        return {
            "requests": int(row["requests"]),
            "tokens": int(row["tokens"]),
            "cost_usd": round(float(row["cost_usd"]), 8),
        }

    def list_work_items(
        self,
        campaign_id: UUID,
        status: WorkItemStatus | None = None,
    ) -> list[CampaignWorkItem]:
        if status is None:
            query = """
                SELECT * FROM campaign_work_items
                WHERE campaign_id = ?
                ORDER BY created_at, work_item_id
            """
            parameters: tuple[str, ...] = (str(campaign_id),)
        else:
            query = """
                SELECT * FROM campaign_work_items
                WHERE campaign_id = ? AND status = ?
                ORDER BY created_at, work_item_id
            """
            parameters = (str(campaign_id), status.value)
        with closing(self._connect()) as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._work_item_from_row(row) for row in rows]

    def list_findings(self, campaign_id: UUID) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        for item in self.list_work_items(campaign_id, status=WorkItemStatus.COMPLETED):
            if not item.result or not item.result.get("success"):
                continue
            review = self._latest_review(item.work_item_id)
            findings.append(
                {
                    "work_item": item,
                    "review": review,
                }
            )
        return findings

    def review_finding(
        self,
        work_item_id: UUID,
        decision: ReviewDecision,
        reason: str,
    ) -> FindingReview:
        if not reason.strip():
            raise ValueError("Review reason must not be blank")
        with self._transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT * FROM campaign_work_items WHERE work_item_id = ?",
                (str(work_item_id),),
            ).fetchone()
            if not row:
                raise KeyError(f"Work item not found: {work_item_id}")
            item = self._work_item_from_row(row)
            if (
                item.status != WorkItemStatus.COMPLETED
                or not item.result
                or not item.result.get("success")
            ):
                raise ValueError("Only successful completed findings can be reviewed")
            previous = connection.execute(
                """
                SELECT review_id FROM finding_reviews
                WHERE work_item_id = ?
                ORDER BY created_at DESC, review_id DESC LIMIT 1
                """,
                (str(work_item_id),),
            ).fetchone()
            review = FindingReview(
                work_item_id=work_item_id,
                campaign_id=item.campaign_id,
                decision=decision,
                reason=reason,
                reviewer_id=self.actor_id,
                reviewer_role=self.actor_role,
                supersedes_review_id=(UUID(previous["review_id"]) if previous else None),
            )
            connection.execute(
                """
                INSERT INTO finding_reviews(
                    review_id, work_item_id, campaign_id, decision, reason,
                    reviewer_id, reviewer_role, supersedes_review_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(review.review_id),
                    str(review.work_item_id),
                    str(review.campaign_id),
                    review.decision.value,
                    review.reason,
                    review.reviewer_id,
                    review.reviewer_role,
                    (str(review.supersedes_review_id) if review.supersedes_review_id else None),
                    review.created_at.isoformat(),
                ),
            )
            self._audit(
                connection,
                item.campaign_id,
                "finding.reviewed",
                {
                    "work_item_id": str(work_item_id),
                    "review_id": str(review.review_id),
                    "decision": decision.value,
                    "reason": reason,
                },
            )
        return review

    def _latest_review(self, work_item_id: UUID) -> FindingReview | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT * FROM finding_reviews
                WHERE work_item_id = ?
                ORDER BY created_at DESC, review_id DESC LIMIT 1
                """,
                (str(work_item_id),),
            ).fetchone()
        if not row:
            return None
        return FindingReview(
            review_id=UUID(row["review_id"]),
            work_item_id=UUID(row["work_item_id"]),
            campaign_id=UUID(row["campaign_id"]),
            decision=ReviewDecision(row["decision"]),
            reason=row["reason"],
            reviewer_id=row["reviewer_id"],
            reviewer_role=row["reviewer_role"],
            supersedes_review_id=(
                UUID(row["supersedes_review_id"]) if row["supersedes_review_id"] else None
            ),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def backup_to(self, destination: str | Path) -> dict[str, Any]:

        destination = Path(destination)
        if destination.exists():
            raise FileExistsError(f"Backup destination already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as source, closing(sqlite3.connect(destination)) as target:
            source.backup(target)
            integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            destination.unlink(missing_ok=True)
            raise RuntimeError(f"Backup integrity check failed: {integrity}")
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        return {
            "path": str(destination),
            "sha256": digest,
            "size_bytes": destination.stat().st_size,
            "schema_version": SCHEMA_VERSION,
        }

    @staticmethod
    def verify_backup(
        backup_path: str | Path,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        path = Path(backup_path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected_sha256 and digest != expected_sha256:
            raise ValueError("Backup SHA-256 does not match expected value")
        with closing(sqlite3.connect(path)) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            metadata = connection.execute(
                "SELECT value FROM schema_metadata WHERE key = 'schema_version'"
            ).fetchone()
        if integrity != "ok":
            raise ValueError(f"Backup integrity check failed: {integrity}")
        if not metadata:
            raise ValueError("Backup does not contain schema metadata")
        return {
            "path": str(path),
            "sha256": digest,
            "size_bytes": path.stat().st_size,
            "schema_version": int(metadata[0]),
            "integrity": integrity,
        }

    @staticmethod
    def restore_backup(
        backup_path: str | Path,
        destination: str | Path,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:

        verified = SQLiteCampaignRepository.verify_backup(
            backup_path, expected_sha256=expected_sha256
        )
        destination = Path(destination)
        if destination.exists():
            raise FileExistsError(f"Restore destination already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(backup_path, destination)
        restored = SQLiteCampaignRepository.verify_backup(destination)
        return {**restored, "source_sha256": verified["sha256"]}

    def list_audit_events(self, campaign_id: UUID) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT event_id, event_type, event_json, created_at,
                       previous_hash, event_hash
                FROM audit_events
                WHERE campaign_id = ?
                ORDER BY created_at, event_id
                """,
                (str(campaign_id),),
            ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "event": json.loads(row["event_json"]),
                "created_at": row["created_at"],
                "previous_hash": row["previous_hash"],
                "event_hash": row["event_hash"],
            }
            for row in rows
        ]

    def verify_audit_chain(self, campaign_id: UUID) -> bool:
        previous_hash = AUDIT_GENESIS_HASH
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT event_id, campaign_id, event_type, event_json,
                       created_at, previous_hash, event_hash
                FROM audit_events
                WHERE campaign_id = ?
                ORDER BY created_at, event_id
                """,
                (str(campaign_id),),
            ).fetchall()
        for row in rows:
            if row["previous_hash"] != previous_hash:
                return False
            expected = self._audit_hash(
                event_id=row["event_id"],
                campaign_id=row["campaign_id"],
                event_type=row["event_type"],
                event_json=row["event_json"],
                created_at=row["created_at"],
                previous_hash=previous_hash,
            )
            if row["event_hash"] != expected:
                return False
            previous_hash = expected
        return True

    def purge_campaigns_before(
        self,
        cutoff: datetime,
        *,
        dry_run: bool = True,
    ) -> dict[str, Any]:

        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("Retention cutoff must be timezone-aware")
        terminal = (
            CampaignStatus.COMPLETED.value,
            CampaignStatus.CANCELLED.value,
            CampaignStatus.FAILED.value,
        )
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT campaign_id, status, updated_at
                FROM campaigns
                WHERE status IN (?, ?, ?) AND updated_at < ?
                ORDER BY updated_at, campaign_id
                """,
                (*terminal, cutoff.astimezone(timezone.utc).isoformat()),
            ).fetchall()
        candidates = [row["campaign_id"] for row in rows]
        if dry_run or not candidates:
            return {
                "dry_run": dry_run,
                "candidate_count": len(candidates),
                "deleted_count": 0,
                "campaign_ids": candidates,
            }

        with self._transaction(immediate=True) as connection:
            for row in rows:
                self._retention_tombstone(
                    connection,
                    campaign_id=row["campaign_id"],
                    event={
                        "status": row["status"],
                        "last_updated_at": row["updated_at"],
                        "retention_cutoff": cutoff.isoformat(),
                    },
                )
                connection.execute(
                    "DELETE FROM campaigns WHERE campaign_id = ?",
                    (row["campaign_id"],),
                )
        return {
            "dry_run": False,
            "candidate_count": len(candidates),
            "deleted_count": len(candidates),
            "campaign_ids": candidates,
        }

    def verify_retention_chain(self) -> bool:
        previous_hash = AUDIT_GENESIS_HASH
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT * FROM retention_events
                ORDER BY created_at, event_id
                """
            ).fetchall()
        for row in rows:
            if row["previous_hash"] != previous_hash:
                return False
            expected = self._retention_hash(
                event_id=row["event_id"],
                campaign_id=row["campaign_id"],
                event_type=row["event_type"],
                event_json=row["event_json"],
                created_at=row["created_at"],
                previous_hash=previous_hash,
            )
            if row["event_hash"] != expected:
                return False
            previous_hash = expected
        return True

    def _require_running_item(
        self, connection: sqlite3.Connection, work_item_id: UUID
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM campaign_work_items WHERE work_item_id = ?",
            (str(work_item_id),),
        ).fetchone()
        if not row:
            raise KeyError(f"Work item not found: {work_item_id}")
        if row["status"] != WorkItemStatus.RUNNING.value:
            raise ValueError(f"Work item {work_item_id} is not running: {row['status']}")
        return row

    def _audit(
        self,
        connection: sqlite3.Connection,
        campaign_id: UUID,
        event_type: str,
        event: dict[str, Any],
    ) -> None:
        event = {
            **event,
            "actor_id": self.actor_id,
            "actor_role": self.actor_role,
        }
        event_id = str(uuid4())
        created_at = _utc_iso()
        event_json = json.dumps(event, sort_keys=True)
        previous = connection.execute(
            """
            SELECT event_hash FROM audit_events
            WHERE campaign_id = ?
            ORDER BY created_at DESC, event_id DESC
            LIMIT 1
            """,
            (str(campaign_id),),
        ).fetchone()
        previous_hash = (
            previous["event_hash"] if previous and previous["event_hash"] else AUDIT_GENESIS_HASH
        )
        event_hash = self._audit_hash(
            event_id=event_id,
            campaign_id=str(campaign_id),
            event_type=event_type,
            event_json=event_json,
            created_at=created_at,
            previous_hash=previous_hash,
        )
        connection.execute(
            """
            INSERT INTO audit_events(
                event_id, campaign_id, event_type, event_json, created_at,
                previous_hash, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                str(campaign_id),
                event_type,
                event_json,
                created_at,
                previous_hash,
                event_hash,
            ),
        )

    def _retention_tombstone(
        self,
        connection: sqlite3.Connection,
        *,
        campaign_id: str,
        event: dict[str, Any],
    ) -> None:
        event_id = str(uuid4())
        event_type = "campaign.retention_purged"
        event_json = json.dumps(event, sort_keys=True)
        created_at = _utc_iso()
        previous = connection.execute(
            """
            SELECT event_hash FROM retention_events
            ORDER BY created_at DESC, event_id DESC LIMIT 1
            """
        ).fetchone()
        previous_hash = (
            previous["event_hash"] if previous and previous["event_hash"] else AUDIT_GENESIS_HASH
        )
        event_hash = self._retention_hash(
            event_id=event_id,
            campaign_id=campaign_id,
            event_type=event_type,
            event_json=event_json,
            created_at=created_at,
            previous_hash=previous_hash,
        )
        connection.execute(
            """
            INSERT INTO retention_events(
                event_id, campaign_id, event_type, event_json, created_at,
                previous_hash, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                campaign_id,
                event_type,
                event_json,
                created_at,
                previous_hash,
                event_hash,
            ),
        )

    def _backfill_audit_hashes(self, connection: sqlite3.Connection) -> None:
        campaign_rows = connection.execute(
            "SELECT DISTINCT campaign_id FROM audit_events"
        ).fetchall()
        for campaign_row in campaign_rows:
            campaign_id = campaign_row["campaign_id"]
            previous_hash = AUDIT_GENESIS_HASH
            rows = connection.execute(
                """
                SELECT event_id, campaign_id, event_type, event_json, created_at
                FROM audit_events
                WHERE campaign_id = ?
                ORDER BY created_at, event_id
                """,
                (campaign_id,),
            ).fetchall()
            for row in rows:
                event_hash = self._audit_hash(
                    event_id=row["event_id"],
                    campaign_id=row["campaign_id"],
                    event_type=row["event_type"],
                    event_json=row["event_json"],
                    created_at=row["created_at"],
                    previous_hash=previous_hash,
                )
                connection.execute(
                    """
                    UPDATE audit_events
                    SET previous_hash = ?, event_hash = ?
                    WHERE event_id = ?
                    """,
                    (previous_hash, event_hash, row["event_id"]),
                )
                previous_hash = event_hash

    @staticmethod
    def _audit_hash(
        *,
        event_id: str,
        campaign_id: str,
        event_type: str,
        event_json: str,
        created_at: str,
        previous_hash: str,
    ) -> str:
        material = json.dumps(
            {
                "event_id": event_id,
                "campaign_id": campaign_id,
                "event_type": event_type,
                "event_json": event_json,
                "created_at": created_at,
                "previous_hash": previous_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    @staticmethod
    def _retention_hash(**fields: str) -> str:
        return hashlib.sha256(
            json.dumps(
                fields,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _result_tokens(result: dict[str, Any]) -> int:
        value = result.get("response_tokens", result.get("tokens_used", 0))
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _result_cost(result: dict[str, Any]) -> float:
        value = result.get("estimated_cost_usd", 0.0)
        try:
            return max(0.0, float(value or 0.0))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _campaign_from_row(row: sqlite3.Row) -> Campaign:
        return Campaign(
            campaign_id=UUID(row["campaign_id"]),
            name=row["name"],
            status=CampaignStatus(row["status"]),
            provider=row["provider"],
            model=row["model"],
            authorization_reference=row["authorization_reference"],
            configuration=json.loads(row["configuration_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _work_item_from_row(self, row: sqlite3.Row) -> CampaignWorkItem:
        return CampaignWorkItem(
            work_item_id=UUID(row["work_item_id"]),
            campaign_id=UUID(row["campaign_id"]),
            idempotency_key=row["idempotency_key"],
            status=WorkItemStatus(row["status"]),
            payload=json.loads(row["payload_json"]),
            attempts=row["attempts"],
            max_attempts=row["max_attempts"],
            worker_id=row["worker_id"],
            last_error=row["last_error"],
            result=self._deserialize_result(UUID(row["work_item_id"]), row["result_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _serialize_result(self, work_item_id: UUID, result: dict[str, Any]) -> str:
        if self.artifact_cipher is None:
            return json.dumps(result, sort_keys=True)
        return self.artifact_cipher.encrypt_json(
            result,
            context=f"campaign-work-item:{work_item_id}",
        )

    def _deserialize_result(self, work_item_id: UUID, raw: str | None) -> dict[str, Any] | None:
        if raw is None:
            return None
        if raw.startswith(ENVELOPE_PREFIX):
            if self.artifact_cipher is None:
                raise ValueError("Artifact encryption key is required to read this result")
            return self.artifact_cipher.decrypt_json(
                raw,
                context=f"campaign-work-item:{work_item_id}",
            )
        return json.loads(raw)
