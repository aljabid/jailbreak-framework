# Documentation

This directory contains the maintained technical and operational documentation
for Jailbreak Framework 1.1.0.

## Start here

| Audience | Document | Purpose |
|---|---|---|
| Users | [Project README](../README.md) | Installation, first run, and core workflows |
| Engineers | [Architecture](architecture.md) | Components, data flow, contracts, and scaling boundary |
| Security | [Threat Model](threat-model.md) | Assets, threats, controls, and residual risk |
| Approvers | [Production Readiness](production-readiness.md) | Release gates, evidence, and sign-off criteria |
| Maintainers | [Project Handoff](project-handoff.md) | Current status and publication resumption steps |
| Operators | [Deployment](deployment.md) | Workstation/container deployment and hardening |
| Operators | [Monitoring](monitoring.md) | Health endpoints, metrics, alerts, and response ownership |

## Security and governance

- [Acceptable Use](acceptable-use.md)
- [Authorization Grants](authorization.md)
- [Security Policy](../SECURITY.md)
- [Data Retention](data-retention.md)

## Evaluation governance

- [Evaluator Methodology](evaluator-methodology.md)
- [Scoring Methodology](scoring-methodology.md)
- [Local Acceptance Testing](local-acceptance.md)

## Operational runbooks

- [Runbook Index](runbooks/README.md)
- [Provider Outage](runbooks/provider-outage.md)
- [Credential Exposure](runbooks/credential-exposure.md)
- [Sensitive-Data Incident](runbooks/sensitive-data-incident.md)
- [Database Recovery](runbooks/database-recovery.md)

## Documentation standards

Maintained documents must reflect current executable behavior, identify
supported and unsupported deployment boundaries, avoid unverified security
claims, and provide safe commands. Generated files under `reports/` are
execution artifacts and are not maintained project documentation.
