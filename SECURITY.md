# Security Policy

Jailbreak Framework handles adversarial prompts, provider credentials, model
responses, authorization records, and potentially sensitive findings. Security
is therefore a release requirement, not an optional deployment feature.

## Supported versions

Security fixes are provided for the latest minor release on `main`. Generated
reports, notebooks, historical research snapshots, and modified third-party
images are not supported release artifacts.

| Version | Support |
|---|---|
| 1.1.x | Production-candidate security fixes |
| 1.0.x and earlier | Unsupported |

## Reporting a vulnerability

Do not open a public issue containing exploit details, credentials, model
responses, authorization grants, personal data, or customer identifiers. Send a
private report to the security contact designated by the deploying
organization.

Include:

- affected version, artifact digest, and commit when available;
- deployment mode and required privileges;
- a minimal reproduction using the mock provider or a target you own;
- expected versus observed behavior;
- impact, affected confidentiality/integrity/availability properties;
- sanitized logs and relevant configuration keys without secret values;
- suggested mitigation, if known.

Recommended response targets:

- acknowledgement within two business days;
- initial severity and scope assessment within five business days;
- coordinated remediation and disclosure timeline after triage.

If credentials or sensitive evidence may be exposed, follow the
[credential-exposure](docs/runbooks/credential-exposure.md) or
[sensitive-data incident](docs/runbooks/sensitive-data-incident.md) runbook
immediately.

## Security invariants

Production deployments must:

- require a valid signed authorization grant for every real target;
- keep RBAC enabled and inject attributable actor identity;
- inject provider, signing, and encryption keys through a secret manager;
- encrypt durable real-target evidence with AES-256-GCM;
- restrict provider endpoints to approved schemes and hosts;
- reject endpoint credentials, redirect primitives, and metadata-service access;
- redact secrets and personal identifiers from logs, reports, and exports;
- enforce request, token, cost, failure, and rate limits;
- preserve and periodically verify audit chains;
- implement live-data and backup retention;
- run source, dependency, secret, package, and container security gates;
- protect observability endpoints at the network boundary;
- maintain tested backup restoration and key escrow.

The legacy JSON workflow is limited to offline mock experimentation. Durable
campaigns are the only supported path for real-target evidence.

## Cryptography and key handling

- Artifact encryption uses AES-256-GCM with unique random nonces and
  context-bound associated data.
- Authorization grants currently use HMAC-SHA-256. Signing and execution should
  occur in separate trust domains. Multi-tenant or cross-organization
  deployments should replace HMAC with an asymmetric organizational signing
  service.
- Never reuse test keys in production.
- Store backup material separately from encryption-key escrow and restrict
  access to both.
- Key identifiers may be logged; key material must never be logged.

## Vulnerability management

The local image scan intentionally separates networked advisory-database
download from the offline image scan:

```bash
./scripts/scan_image.sh jailbreak-framework:readiness
```

The gate fails on fixed HIGH or CRITICAL OS and Python findings. Unfixed
findings require documented risk acceptance, compensating controls, an owner,
and an expiration date.

## Security boundaries

Version 1.1.0 supports one trusted host with SQLite/WAL. It does not claim
multi-tenant isolation, multi-region durability, or distributed authorization.
See the [threat model](docs/threat-model.md) for residual risks.
