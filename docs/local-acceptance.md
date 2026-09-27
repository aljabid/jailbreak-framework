# Local Production-Acceptance Drill

## Purpose

The local drill provides genuine provider and recovery evidence without an
external account. It uses a loopback Ollama endpoint, a compact local model,
ephemeral authorization/encryption keys, and a temporary database.

It validates software behavior; it does not replace independent review, legal
authorization, production secret management, or an organizational backup-store
exercise.

## Prerequisites

```bash
ollama list
ollama pull qwen2.5:0.5b
```

The endpoint must be reachable at `http://127.0.0.1:11434`. No prompt or model
response leaves the host.

## Run

```bash
.venv/bin/python scripts/local_acceptance.py \
  --endpoint http://127.0.0.1:11434 \
  --model qwen2.5:0.5b \
  --output reports/local-acceptance.json
```

The script:

1. Resolves the installed model digest.
2. Generates ephemeral signing and AES-256-GCM keys.
3. Creates and signs a one-request, one-strategy grant.
4. Verifies the exact target/provider/model/strategy scope.
5. Creates and runs an encrypted durable campaign.
6. Confirms terminal state and counts.
7. Verifies the campaign audit chain.
8. Creates and hash/integrity-verifies an online backup.
9. Restores to a new database and confirms campaign state.
10. Deletes temporary grant, database, backup, and key material.

## Evidence

The optional JSON output is mode `0600` and records:

- timestamps;
- provider/model/digest;
- signed-grant identifier and document hash;
- campaign identifier, terminal status, and counts;
- audit-chain result;
- encryption state;
- backup hash, integrity, and restoration result.

It intentionally excludes keys, prompts, responses, and decrypted findings.

## Failure handling

- Model memory error: use the compact model, stop larger loaded models, and
  confirm available RAM.
- Endpoint error: verify Ollama service status and loopback allowlist.
- Authorization failure: inspect scope/timestamps without printing the key.
- Campaign failure: preserve sanitized error categories and temporary evidence
  until diagnosis.
- Backup failure: stop acceptance and follow the database recovery runbook.
