from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ResponseCache:
    """Disk-backed cache of provider responses, keyed by request fingerprint.

    Opt-in only: intended for iterative development so repeated identical
    requests against a paid provider don't re-spend tokens. Never used
    automatically for real-target campaigns.
    """

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS response_cache (
                    cache_key TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    hits INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            connection.commit()

    @staticmethod
    def make_key(
        *,
        provider: str,
        model: str,
        prompt: str,
        temperature: float | None,
        max_tokens: int | None,
    ) -> str:
        material = json.dumps(
            {
                "provider": provider,
                "model": model,
                "prompt": prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    def get(self, cache_key: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT response_json FROM response_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE response_cache SET hits = hits + 1 WHERE cache_key = ?",
                (cache_key,),
            )
            connection.commit()
        return dict(json.loads(row["response_json"]))

    def set(
        self,
        cache_key: str,
        *,
        provider: str,
        model: str,
        response: dict[str, Any],
    ) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO response_cache(
                    cache_key, provider, model, response_json, created_at, hits
                ) VALUES (?, ?, ?, ?, ?, 0)
                ON CONFLICT(cache_key) DO UPDATE SET
                    response_json = excluded.response_json,
                    created_at = excluded.created_at
                """,
                (
                    cache_key,
                    provider,
                    model,
                    json.dumps(response, sort_keys=True, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.commit()

    def stats(self) -> dict[str, int]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS entries, COALESCE(SUM(hits), 0) AS hits FROM response_cache"
            ).fetchone()
        return {"entries": int(row["entries"]), "hits": int(row["hits"])}

    def clear(self) -> int:
        with closing(self._connect()) as connection:
            cursor = connection.execute("DELETE FROM response_cache")
            connection.commit()
        return cursor.rowcount
