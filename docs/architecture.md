# Architecture

## Scope

Jailbreak Framework 1.1.0 is a modular, single-host security-evaluation system.
The supported production path is the durable campaign workflow backed by
SQLite/WAL. The legacy JSON workflow is retained only for offline mock
experimentation.

## System context

```text
Authorized operator
       |
       v
CLI and policy boundary
       |
       +--> Authorization / RBAC / budgets / endpoint policy
       |
       v
Campaign application service
       |
       +--> Prompt generation --> Provider adapter --> Target model
       |                                |
       |                                v
       +<-- Scoring <--- Evaluation <--- Response
       |
       +--> SQLite/WAL, encrypted evidence, audit chain, reviews
       |
       +--> Logs, reports, health, metrics, backups
```

## Component boundaries

| Package | Responsibility |
|---|---|
| `application/` | Campaign execution, budgets, and rate limiting |
| `domain/` | Strict versioned records and provider protocols |
| `policy/` | Authorization, RBAC, and endpoint restrictions |
| `persistence/` | Transactions, migrations, work claims, audit chains, backups |
| `core/` | Generation, provider execution, evaluation, and scoring |
| `models/` | OpenAI and local provider adapters |
| `evaluation/` | Versioned evaluator and scoring benchmarks |
| `observability/` | Metrics, liveness/readiness, and HTTP monitoring surface |
| `utils/` | Configuration, encryption, redaction, logging, files, and reports |
| `scripts/` | Reproducible release, image-scan, and local-acceptance controls |

Dependencies point inward toward domain contracts and policy. Provider,
persistence, and presentation details must not become implicit domain state.

## Durable execution flow

1. The operator identity is resolved and authorized by RBAC.
2. A real-target grant is signature-checked and validated for time and scope.
3. Strict configuration and endpoint policy are evaluated.
4. Deterministic prompts are generated and assigned idempotency keys.
5. The campaign and work items are committed transactionally.
6. A worker atomically claims one queued item.
7. Provider execution applies rate limits, bounded retries, and error
   categorization.
8. Evaluation and scoring produce versioned structured results.
9. Evidence is encrypted before persistence; safe metadata and audit events are
   committed with the work transition.
10. Interrupted work can be recovered without duplicating completed evidence.
11. Reviewers append attributable decisions; prior reviews remain immutable.

## State and concurrency

SQLite runs in WAL mode. Transactions protect campaign transitions, idempotent
enqueue, atomic work claims, completion/failure, reviews, audit events, and
retention. This supports multiple local threads or processes on one host.

Do not place the database on general-purpose network storage and do not share it
across hosts. Distributed execution requires PostgreSQL or an equivalent
transactional store, a durable queue, distributed leases, centralized identity,
global rate/cost controls, and a new failure-mode analysis.

## Contract versions

| Contract | Current version |
|---|---|
| Domain records | 1.0 |
| SQLite schema | 5 |
| Evaluator | 2.0 |
| Scoring model | 2.0 |
| Encrypted envelope | `jbfenc:v1` |
| Export schema | 1.0 |

Compatibility changes must update the relevant version and include migration or
consumer tests. Package version alone is not a substitute for contract
versioning.

## Security boundaries

Prompts, target responses, judge output, endpoint URLs, imported data, provider
errors, report fields, and restored files are untrusted. Actor identity,
authorization grants, and keys become trusted only after validation.

The observability service binds to loopback by default. Non-loopback exposure is
an explicit deployment decision and requires a protected network path.

## Availability and recovery

Every completed work item is checkpointed. Retryable failures retain work state;
stale in-progress items can be recovered. Consistent online backup uses the
SQLite backup API and produces SHA-256, schema, size, and integrity evidence.
Restore refuses to overwrite an existing destination.

## Deliberate non-goals

- Multi-tenant isolation.
- Multi-region or active-active execution.
- Unattended legal authorization decisions.
- Universal model-safety certification.
- Storing production secrets in project files or images.
