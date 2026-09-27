# Data Retention and Disposal

## Objective

Retain prompts, responses, findings, logs, exports, and backups only as long as
required for authorized review, remediation, and applicable legal obligations.
Deletion must cover derived artifacts and backups, not only the live database.

## Data classes

| Class | Examples | Default handling |
|---|---|---|
| Secrets | API/signing/encryption keys | Never persist; rotate on exposure |
| Restricted evidence | Raw prompts/responses, customer data | Encrypt, least privilege, shortest retention |
| Findings | Scores, reviews, sanitized excerpts | Controlled access and approved retention |
| Operational metadata | Counts, timings, error categories | Redacted; retain for reliability analysis |
| Audit/tombstone data | Actor, transition, purge evidence | Retain under audit policy |
| Generated artifacts | Reports, exports, charts, SBOMs | Classify from source evidence |

## Policy definition

Each deployment must record an owner-approved schedule covering:

- active campaign evidence;
- completed and cancelled campaigns;
- failed work and provider errors;
- reports and exports;
- logs and monitoring data;
- live database backups and key escrow;
- audit tombstones and legal holds.

Legal holds override scheduled deletion and must have an owner and expiry review.

## Framework purge

Preview eligible terminal campaigns:

```bash
.venv/bin/python main.py campaign purge --older-than-days 30
```

Execute only after review and confirmation:

```bash
.venv/bin/python main.py campaign purge \
  --older-than-days 30 \
  --execute
```

Only terminal campaigns are eligible. Purge removes campaign data and preserves
a tamper-evident tombstone sufficient to prove the authorized deletion event.

## Backup and derivative disposal

A live-database purge does not remove:

- offline or remote backups;
- exports and reports;
- copied incident evidence;
- provider-side retention;
- monitoring or ticket-system metadata.

Maintain a backup expiry workflow tied to the same classification. Destroying
an encryption key may make evidence inaccessible but is not automatically
equivalent to deletion under every policy or law.

## Verification

For every disposal batch, record scope, policy basis, actor, timestamp, affected
artifact identifiers, backup treatment, exceptions, and audit-chain result.
Periodically test that expired data cannot be retrieved through normal
application, backup, export, or report paths.
