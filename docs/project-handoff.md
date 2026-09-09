# Project Handoff

## Status

Jailbreak Framework 1.1.0 is technically prepared for publication as an authorized LLM security-testing project. Its supported production topology is a trusted single host using SQLite with WAL mode. Distributed and multi-tenant operation remain outside the supported boundary.

The publication target is `https://github.com/aljabid/jailbreak-framework`.

## Completed work

- Strict versioned domain contracts and configuration validation
- Durable campaign execution with checkpoints, retries, pause, cancellation, and recovery
- SQLite schema version 5 with migrations, backup, verification, restoration, retention, and audit chains
- Scoped signed authorization grants and default-deny role-based access control
- AES-256-GCM protection for persisted sensitive evidence
- Provider contracts for OpenAI-compatible, Ollama, Hugging Face, and mock execution
- Versioned evaluator and risk-scoring regression benchmarks
- Health, readiness, Prometheus metrics, alert rules, and operational runbooks
- Hardened non-root container and Compose deployment
- Dependency locking, source security checks, image scanning, SBOM generation, and release verification
- Professional maintained documentation with validated internal links
- Emoji-free source, CLI output, notebook content, persisted results, historical reports, and report generation
- Removal of explanatory source comments and Python docstrings while retaining required script shebangs

## Latest verification

The complete local release gate passed on July 26, 2026, and the test suite
and documentation set were extended again on August 2, 2026:

- 279 tests passed (up from 248), including a dedicated concurrency-stress
  suite that load-tests the SQLite/WAL campaign repository under 8 concurrent
  workers rather than only unit-testing it in isolation
- 91 percent statement coverage (up from 87.24 percent); `utils/logger.py`
  and `utils/config.py` are now at 100 percent and 99 percent respectively
- Ruff passed
- MyPy passed
- Bandit passed
- Python compilation passed
- Evaluator benchmark passed
- Scoring benchmark passed
- Mock readiness passed
- Documentation validation passed for 22 maintained documents (README.md was
  substantially rewritten as the project's primary reference document)
- Source distribution and wheel built successfully
- Docker Compose validation passed

A fresh Markdown report was generated successfully after the emoji removal. An exhaustive scan of readable project files, the wheel, and the source archive found zero emoji characters.

## Local acceptance evidence

The loopback Ollama acceptance drill passed with `qwen2.5:0.5b`:

- scoped authorization signature verified;
- encrypted durable campaign completed;
- audit chain verified;
- database backup integrity passed;
- restoration was verified;
- no test secrets were persisted.

The sanitized evidence is stored at `reports/local-acceptance.json`.

## Resume commands

From the repository root:

```bash
./scripts/verify_release.sh
docker build --tag jailbreak-framework:readiness .
./scripts/scan_image.sh jailbreak-framework:readiness
./scripts/generate_sbom.sh jailbreak-framework:readiness
```

The container must be rebuilt and rescanned immediately before publication so its digest and SBOM correspond to the final source state.

## GitHub publication actions

When publication is authorized:

1. Confirm the repository owner or organization.
2. Select public or private visibility.
3. Add real maintainer and security contact information.
4. Review the acceptable-use and security policies.
5. Run the complete release and container gates.
6. Review generated artifacts and exclude runtime reports, databases, logs, credentials, and local environment files.
7. Create the initial local commit.
8. Create and configure the GitHub repository and remote.
9. Push the default branch and confirm CI and security workflows.
10. Create the signed release tag and publish the verified artifacts, checksums, SBOM, and provenance.

## External approvals

Technical readiness does not replace:

- system-owner authorization for target testing;
- legal and acceptable-use approval;
- production credential provisioning;
- independent security and evaluator review;
- named monitoring and incident-response ownership;
- final organizational release approval.

These approvals should be recorded before describing a deployment as formally certified or organizationally approved.
