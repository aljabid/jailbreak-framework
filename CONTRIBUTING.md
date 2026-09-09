# Contributing to Jailbreak Framework

Thank you for improving Jailbreak Framework. Contributions must preserve its
authorization-first security model, deterministic evaluation behavior, and
single-node support contract.

## Code of conduct

Use the project only for authorized defensive research. Do not submit real
customer prompts, provider credentials, personal data, private findings, or
unapproved attack material. Treat reviewers and security reporters
professionally.

## Development environment

Install the pinned toolchain and all development/reporting extras:

```bash
python -m pip install "uv==0.11.32"
uv sync --locked --extra dev --extra reporting
```

Do not update dependencies with ad hoc `pip install` commands. Change
`pyproject.toml`, run `uv lock`, and include the reviewed `uv.lock` update.

## Change workflow

1. Define the behavior, threat, or defect being addressed.
2. Add or update focused tests before relying on broad regression coverage.
3. Keep domain, persistence, evaluator, scorer, and encrypted-envelope versions
   independent.
4. Update every affected user, operator, security, and runbook document.
5. Run the complete local gate:

   ```bash
   ./scripts/verify_release.sh
   ```

6. For container changes, rebuild and run:

   ```bash
   ./scripts/scan_image.sh jailbreak-framework:readiness
   ```

## Engineering standards

- Python 3.10 compatibility is required.
- Ruff and MyPy must pass without new suppressions unless the suppression is
  narrowly justified in code.
- Public and cross-layer data uses explicit typed contracts.
- File writes that replace artifacts must be atomic.
- Database changes require forward migrations and migration tests.
- Provider errors must be categorized without leaking secrets.
- Randomized behavior must accept a seed or isolated random generator.
- Security-sensitive comparisons must use constant-time primitives where
  appropriate.
- Logs, reports, exports, and exceptions must pass through redaction controls.
- New outbound endpoints must preserve scheme, host, credential, redirect, and
  allowlist validation.

## Test expectations

Changes should add the narrowest meaningful test type:

| Change | Minimum evidence |
|---|---|
| Domain/config contract | Unit and invalid-input tests |
| Persistence/schema | Migration, transaction, recovery, and integrity tests |
| Provider adapter | Contract tests with injected client/fake transport |
| Evaluator/scorer | Versioned benchmark cases and regression tests |
| Security control | Positive, negative, tamper, and authorization tests |
| CLI behavior | `CliRunner` integration test |
| Packaging/resources | Built-wheel isolated import/resource test |
| Container/runtime | Build, health, hardening, and vulnerability scan |

The project-wide coverage floor is 75%; the current suite is expected to remain
materially above that floor.

## Documentation

Documentation is part of the implementation. Use precise language, state
support boundaries explicitly, include safe copy-paste commands, and avoid
claims not supported by tests or runtime evidence. Add new maintained documents
to [docs/README.md](docs/README.md).

## Security review

Changes involving authorization, access control, cryptography, redaction,
retention, provider endpoints, audit history, backups, or release workflows
require security-owner review. Report suspected vulnerabilities privately under
[SECURITY.md](SECURITY.md).

## Versioning and release notes

Use semantic versioning for the package. Independently increment contract
versions when compatibility changes:

- domain schema;
- SQLite schema;
- evaluator taxonomy/decision logic;
- scoring model;
- encrypted artifact envelope;
- exported evidence schema.

Record user-visible and security-relevant changes in [CHANGELOG.md](CHANGELOG.md).
