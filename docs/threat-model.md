# Threat Model

## Scope and assumptions

This model covers Jailbreak Framework 1.1.0 on one trusted host with SQLite/WAL.
The host, operating-system administrator, and secret manager are trusted.
Prompts, responses, provider endpoints, imported data, reports, and judge output
are untrusted. Multi-tenant and distributed deployments require a new model.

## Protected assets

- Provider credentials and tokens.
- Authorization-signing and artifact-encryption keys.
- Target identifiers, prompts, responses, and customer data.
- Findings, reviewer decisions, scores, exports, and reports.
- Campaign state, audit evidence, budgets, and execution capacity.
- Backups, key escrow, SBOMs, and release provenance.

## Actors

| Actor | Security expectation |
|---|---|
| Security administrator | Issues keys/grants and configures policy |
| Campaign author | Defines work within approved scope |
| Campaign operator | Executes and controls campaigns |
| Reviewer | Confirms or rejects findings |
| Auditor | Verifies evidence, history, exports, and backups |
| Target/provider | External or local dependency; responses are untrusted |
| Host administrator | Trusted within the single-host boundary |

## Trust boundaries

1. User/automation to CLI and actor environment.
2. Framework to provider endpoint.
3. Application to SQLite and filesystem artifacts.
4. Runtime to secret manager and backup store.
5. Observability endpoint to monitoring network.
6. Build environment to package registries, base images, and advisory data.

## Threats and controls

| Threat | Primary controls | Residual concern |
|---|---|---|
| Unauthorized target testing | Signed scoped grants, RBAC, attributable audit | Compromised shared signing key |
| Privilege misuse | Default-deny role matrix, separation of duties | Trusted host administrator |
| SSRF/metadata access | Scheme/host allowlists, credential/query/fragment checks, redirect rejection | DNS/network policy outside process |
| Credential disclosure | Environment-only secrets, redaction, no secret summaries | Provider SDK or host compromise |
| Evidence disclosure | AES-256-GCM, restrictive files, RBAC | Key theft or authorized-user misuse |
| Evidence tampering | AEAD authentication, hash-chained audits, append-only reviews | Destruction of all copies |
| Duplicate/lost execution | Transactions, idempotency, checkpoints, stale-work recovery | Host/storage loss between backups |
| Unbounded cost/load | Request/token/cost/failure budgets and rate limits | Provider-side price/config drift |
| Judge prompt injection | Delimiters, strict JSON, indeterminate fallback | Semantically valid judge manipulation |
| Report injection | Markdown neutralization and redaction | Unsafe downstream renderer |
| Stale sensitive data | Retention purge, tombstones, backup policy | Unmanaged derivative copies |
| Supply-chain compromise | Lock, hashes, pinned base digest, scans, SBOM/provenance workflows | Compromised upstream/signing infrastructure |
| Monitoring exposure | Loopback default, explicit remote opt-in, no-store headers | No built-in TLS/authentication |
| Backup failure | Online backup API, SHA-256, integrity/schema checks, restore drill | Lost encryption key or backup-store compromise |

## Abuse cases

- An operator broadens a grant using wildcards.
- A malicious response attempts to instruct the judge or report renderer.
- A crafted endpoint targets loopback, metadata, or redirects.
- A provider error embeds an API key in a message.
- A worker retries a completed request after interruption.
- A reviewer overwrites an earlier decision.
- An attacker restores a modified or incompatible backup.
- A collector exposes readiness details to an untrusted network.

Tests cover positive and negative paths for these controls where the behavior is
implemented locally.

## Residual risks

- HMAC authorization is shared-secret based and unsuitable as a
  cross-organization trust root.
- Keyword evaluation and synthetic regression fixtures have distributional
  limits.
- Model judges can drift or reproduce target-model biases.
- SQLite does not provide multi-host consensus or regional durability.
- The observability server does not implement authentication or TLS.
- Host administrator compromise is outside application-level containment.

## Review triggers

Review this model for every major release, provider or tool integration,
cryptographic change, new data class, remote observability exposure,
distributed-deployment proposal, security incident, or material architecture
change.
