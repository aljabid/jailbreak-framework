# Database Recovery

## Purpose

Use this runbook to recover the SQLite campaign store after corruption, accidental loss, an unsuccessful migration, or host failure.

## Preconditions

- Stop all writers before copying, restoring, or replacing the database.
- Confirm the intended environment and database path.
- Identify the most recent verified backup and its recorded SHA-256 digest.
- Preserve the damaged database and related `-wal` and `-shm` files for investigation.

## Backup verification

Create and validate a backup with the framework command:

```bash
python -m main db-backup --destination backups/jbf.sqlite3
python -m main db-verify-backup --backup backups/jbf.sqlite3
```

Verification must report a valid SQLite integrity check and a matching backup digest before the backup is considered recoverable.

## Restore procedure

1. Stop campaign workers and any process using the database.
2. Preserve the current database files in a restricted incident directory.
3. Verify the selected backup.
4. Restore it to a new path first:

   ```bash
   python -m main db-restore \
     --backup backups/jbf.sqlite3 \
     --destination restored/jbf.sqlite3
   ```

5. Start the application against the restored path in an isolated process.
6. Run `python -m main db-status` and confirm the schema is current.
7. Validate the audit chain:

   ```bash
   python -m main audit-verify --database restored/jbf.sqlite3
   ```

8. Inspect campaign, request, response, metric, and audit counts against the recovery objective.
9. Promote the restored database only after validation succeeds.

## Post-restore checks

- Readiness returns healthy.
- A controlled authorized campaign can be created and resumed.
- Encrypted values can be decrypted with the active encryption key.
- Audit-chain verification succeeds.
- No process is still writing to the damaged database.
- Monitoring shows no persistent storage or work-queue errors.

## Failure handling

If integrity verification fails, do not place the backup into service. Select an earlier verified backup or escalate to a SQLite recovery specialist. Document expected data loss using the configured recovery-point objective.

## Closure criteria

Record the restored backup digest, recovery point, recovery time, validation results, lost-data estimate, incident owner, and corrective actions. Perform a follow-up backup after service stabilizes.

See [Data Retention](../data-retention.md) for retention requirements.
