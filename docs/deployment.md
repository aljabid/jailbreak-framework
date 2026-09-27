# Deployment Guide

## Supported topology

Version 1.1.0 supports one trusted Linux host. SQLite/WAL, artifact storage, the
campaign worker, and observability service must reside within that host's trust
boundary. Do not place the SQLite file on generic network storage.

## Pre-deployment checklist

- Approved system-owner authorization and acceptable-use review.
- Python 3.10–3.13 or Docker/Compose.
- Secret-manager delivery for provider, authorization-signing, and artifact
  encryption keys.
- Attributable `JBF_ACTOR_ID` and least-privilege `JBF_ACTOR_ROLE`.
- Approved provider endpoint allowlist and outbound network policy.
- Writable encrypted storage for outputs/reports and separate backup storage.
- Retention, monitoring, alert routing, incident ownership, and recovery plan.
- Passing [production-readiness](production-readiness.md) evidence.

## Workstation deployment

```bash
python -m pip install "uv==0.11.32"
uv sync --locked --extra dev --extra reporting
./scripts/verify_release.sh
```

Inject secrets at process start. Do not save them in shell history; the examples
below show variable names only:

```text
JBF_AUTHORIZATION_SIGNING_KEY
JBF_ARTIFACT_ENCRYPTION_KEY
OPENAI_API_KEY                 # only when OpenAI is approved
```

Validate before executing a real campaign:

```bash
.venv/bin/python main.py health --profile production --json-output
```

## Container build

The multi-stage Dockerfile:

- uses a digest-pinned Python 3.12.13/Debian 12.15 base;
- builds from the committed dependency lock;
- installs runtime requirements with hashes;
- excludes build tools from the runtime stage;
- runs as UID/GID 65532;
- provides no embedded production secrets.

Build and scan:

```bash
docker build --tag jailbreak-framework:readiness .
./scripts/scan_image.sh jailbreak-framework:readiness
```

The scan downloads the public advisory database without access to the image,
then scans the image archive with networking disabled. It fails on fixed HIGH
or CRITICAL OS or Python findings.

## Compose runtime

```bash
docker compose config -q
docker compose build
docker compose run --rm jbf health --profile production
```

Compose applies:

- read-only root filesystem;
- dropped Linux capabilities;
- `no-new-privileges`;
- PID, memory, and CPU limits;
- dedicated output/report volumes;
- size-limited `/tmp` tmpfs;
- non-root process identity.

The `.env` integration is for local operation. Production orchestrators should
use their native secret mechanism.

## Observability

Start the loopback service:

```bash
.venv/bin/python main.py serve-observability \
  --host 127.0.0.1 \
  --port 9464 \
  --profile production
```

If a collector cannot access loopback, expose through an authenticated service
mesh or reverse proxy. `--allow-remote` is an explicit acknowledgement; it does
not add authentication or TLS. See [Monitoring](monitoring.md).

## Storage and backup

Create and verify an online backup:

```bash
.venv/bin/python main.py campaign backup --output /secure-backup/jbf.db
.venv/bin/python main.py campaign backup-verify --input /secure-backup/jbf.db
```

Restore only to a new path:

```bash
.venv/bin/python main.py campaign backup-restore \
  --input /secure-backup/jbf.db \
  --destination /recovery/jbf-restored.db \
  --yes
```

Back up encryption-key metadata through a separate controlled channel. Evidence
cannot be recovered without the correct key.

## Upgrade and rollback

1. Pause campaigns and create a verified backup.
2. Record current package/image/database schema versions.
3. Run release gates on the candidate.
4. Upgrade one host and run production health.
5. Resume a low-risk authorized campaign and inspect evidence/audit chains.
6. Roll back application artifacts only when database compatibility permits.

Never downgrade a database whose schema is newer than the application supports.

## Scaling boundary

Multi-node deployment requires a new architecture: PostgreSQL or equivalent,
durable queue, worker leases, distributed rate/cost budgets, centralized
identity, secrets, observability, and disaster recovery. It is not a supported
configuration of this release.
