# Production Readiness and Acceptance

## Decision scope

This checklist governs Jailbreak Framework 1.1.0 on one trusted host using
SQLite/WAL. A passing checklist does not approve unauthorized target testing
and does not extend support to distributed or multi-tenant deployment.

## Readiness status vocabulary

| Status | Meaning |
|---|---|
| Pass | Current evidence directly satisfies the gate |
| Conditional | Technical control passes; deployment-specific evidence is required |
| Fail | Evidence contradicts the requirement |
| Not run | Required evidence has not been collected |
| Out of scope | Not part of the supported topology |

## Engineering-control matrix

| Area | Required evidence | Local status |
|---|---|---|
| Architecture | Explicit boundaries, contracts, and scaling limit | Pass |
| Domain contracts | Strict versioned validation and negative tests | Pass |
| Configuration | Precedence, coercion, validation, secret omission | Pass |
| Persistence | Transactions, schema 5 migrations, WAL, integrity tests | Pass |
| Execution | Idempotency, checkpoints, retry/recovery, pause/cancel | Pass |
| Provider integration | Contract tests and one real approved provider drill | Pass locally with loopback Ollama |
| Evaluation | Versioned taxonomy, deterministic benchmark, holdout plan | Conditional on deployment dataset |
| Scoring | Versioned dimensions, benchmark, override attribution | Conditional on deployment calibration |
| Authorization | Signature, time/scope validation, document hash | Pass |
| Access control | Default-deny RBAC and attributable actor | Pass |
| Data security | AES-256-GCM, redaction, endpoint policy, retention | Pass |
| Auditability | Hash chains and append-only reviews | Pass |
| Observability | HTTP health/metrics, alert rules, response ownership | Conditional on deployment routing |
| Testing | Unit/integration/CLI/security/provider/recovery tests | Pass |
| Code quality | Ruff, MyPy, compile, coverage threshold | Pass |
| Supply chain | Lock, hashes, SBOM workflow, image scan, base digest | Pass locally; hosted attestation pending |
| Deployment | Non-root/read-only/capability/resource tests | Pass |
| Operations | Runbooks, restoration drill, retention, incident ownership | Conditional on named organizational owners |

## Automated local gates

Run:

```bash
./scripts/verify_release.sh
docker build --tag jailbreak-framework:readiness .
./scripts/scan_image.sh jailbreak-framework:readiness
./scripts/generate_sbom.sh jailbreak-framework:readiness
```

The code gate verifies:

- dependency-lock consistency;
- Ruff, MyPy, and compilation;
- Bandit medium/high source scan;
- complete tests and coverage;
- evaluator and scoring benchmarks;
- mock readiness;
- source/wheel distributions;
- Compose validity.

The image gates separate advisory-database download from offline archive access,
fail on fixed HIGH/CRITICAL OS or Python findings, and produce a CycloneDX SBOM
under `dist/`.

## Local real-provider drill

When loopback Ollama is approved:

```bash
ollama pull qwen2.5:0.5b
.venv/bin/python scripts/local_acceptance.py \
  --model qwen2.5:0.5b \
  --output reports/local-acceptance.json
```

Required evidence:

- installed-model digest;
- nonempty normalized provider response;
- valid scoped signature;
- completed one-request durable campaign;
- encrypted evidence;
- valid campaign audit chain;
- consistent backup hash/integrity;
- successful restore and restored campaign state;
- no persisted test secrets.

The generated report contains identifiers and hashes but no prompt/response or
key material.

## Production health and monitoring

Production health must return `ready: true` with deployment-managed keys:

```bash
.venv/bin/python main.py health --profile production --json-output
```

The monitoring collector must scrape `/health/live`, `/health/ready`, and
`/metrics`. Every alert in `deploy/monitoring/prometheus-rules.yaml` needs a
named route, on-call owner, severity policy, and tested notification path.

## Backup acceptance

At least quarterly:

1. Create an online backup.
2. Record SHA-256, size, schema, and integrity.
3. Retrieve the required key from escrow under dual control.
4. Restore to an isolated new path.
5. Verify SQLite integrity, schema, audit chains, campaign counts, and sample
   authorized evidence decryption.
6. Record recovery-point and recovery-time results.
7. Securely dispose of drill artifacts under retention policy.

The local acceptance script verifies the software path; the organization must
still prove its actual backup store and key-escrow process.

## Deployment approval record

Before go-live, record:

| Gate | Required approver/evidence |
|---|---|
| System authorization | System owner, target scope, test window |
| Acceptable use/legal | Security/legal owner as required |
| Evaluator/scorer calibration | Independent policy reviewers and holdout results |
| Provider acceptance | Approved non-production target/account evidence |
| Security review | Application/container review and residual-risk register |
| Backup/recovery | Backup owner, escrow owner, drill report |
| Monitoring | Service owner, on-call route, alert test |
| Release artifact | Commit/digest, CI results, SBOM, provenance |
| Final decision | Release manager, date, exceptions, expirations |

An exception must identify risk, compensating control, accountable owner, review
date, and expiration. Missing or expired approval means the deployment is not
production-approved even when all local software gates pass.

## Current local evidence

The current workspace has demonstrated:

- 279 passing tests with 91% statement coverage, well above the 75% gate;
- clean Ruff, MyPy, and Bandit results;
- passing evaluator and scoring regression benchmarks;
- buildable source and wheel packages;
- a digest-pinned, non-root hardened image;
- zero fixed HIGH/CRITICAL findings in the offline image scan;
- passing loopback production health and Prometheus endpoints;
- successful real Ollama authorization/execution/audit/backup/restore drill.

These results must be regenerated for the final release artifact. Generated
evidence is time-sensitive and does not replace named organizational approval.
