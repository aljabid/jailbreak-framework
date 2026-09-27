# Changelog

All notable changes are recorded here. The project follows
[Semantic Versioning](https://semver.org/) and groups unreleased work under the
next planned version.

## [1.1.0] - Unreleased

### Added

- Anthropic provider adapter (`models/anthropic_model.py`), wired into
  `--provider anthropic` for `run`, `compare`, and `campaign create`.
- Sixth attack strategy, `multi_turn` (crescendo-style conversation
  escalation), added to the default strategy set.
- Expanded the base-prompt corpus from 10 to 154 entries across seven
  content-risk categories (general, deception, privacy, illegal, violence,
  weapons, malware), plus a Spanish/French/German multilingual layer
  (`language` field, `multilingual` tag). Added a `--category` filter to
  `run`/`compare`/`campaign create`.
- Grew the evaluator regression benchmark from 15 to 38 hand-labeled,
  verified cases (more refusal/compliance/leak/partial variants, additional
  multilingual refusals, more judge-injection-resistance cases).
- Optional SQLite-backed response cache (`utils/cache.py`, `--cache`) so an
  identical prompt+model+params request during iterative development
  doesn't re-spend provider tokens.
- `compare` CLI command: runs the same seeded prompt batch across several
  `provider:model` targets in one invocation, verifying authorization
  independently for each non-mock target, and produces a side-by-side
  comparison report (Markdown/JSON/HTML/PPTX).
- `regression-check` CLI command: diffs two runs' aggregate stats and fails
  (non-zero exit) if jailbreak success rate or average risk score rose
  beyond a configurable threshold — for catching safety regressions across
  model versions over time.
- Self-contained interactive HTML dashboard (`Reporter.save_html_dashboard`,
  Plotly via CDN), PPTX slide-deck export (`Reporter.save_pptx_summary`),
  and single-file PDF export (`Reporter.save_pdf_summary`, reportlab) — all
  require the `reporting` extra, available via
  `--format html|pptx|pdf|all` on `report` and `campaign report`.
- "Top Failing Prompts" leaderboard (`Scorer.leaderboard`): ranks
  strategy/base-prompt combinations by success rate and average risk score.
- `scripts/import_external_prompts.py`: converts a locally-provided export
  of a public adversarial-prompt benchmark (AdvBench, JailbreakBench, or a
  custom CSV/JSON) into `data/prompts.json`'s schema, preserving a
  `source`/`license`/`imported_at` attribution block per prompt. Ships with
  no third-party prompt data itself — see
  [Importing external prompt datasets](README.md#importing-external-prompt-datasets).
- `scripts/export_attack_corpus.py`: exports the full attack corpus (924 =
  6 strategies x 154 base prompts, via the real `PromptGenerator`, no
  target model needed) as JSON, consumed by a sibling evaluation project
  (`attack-vs-defense-eval`) that measures a real defensive classifier's
  catch rate against it — see
  [Companion project](README.md#companion-project-measuring-a-real-defense-against-these-attacks).
- Concurrency-stress test suite (`tests/test_concurrency_stress.py`) that
  load-tests the SQLite/WAL campaign repository with 8 concurrent workers:
  zero double-claims across 200 work items, verified database integrity,
  a verified audit hash chain, and a racing-idempotency-key test.
- Full statement-coverage tests for `utils/logger.py` (now 100%) and
  `utils/config.py` (now 99%), closing previously untested branches in the
  JSON log formatter, the `operation()` context manager, corrupt-file
  recovery, config type coercion, and YAML/dotenv fallback paths.
- Rewrote README.md as the project's comprehensive root reference document,
  covering architecture, both execution models, every CLI command, the full
  configuration key reference, authorization/RBAC, and a documentation map.

- Strict, versioned Pydantic domain models and provider protocols.
- Transactional SQLite/WAL campaigns with migrations, idempotent work items,
  checkpoints, retry recovery, pause/cancel transitions, and usage accounting.
- Request, token, cost, failure, and sustained-rate budgets.
- Eight-outcome evaluator taxonomy, structured AI-judge parsing, injection
  delimiters, deterministic benchmark data, and quality metrics.
- Versioned risk scoring across likelihood, impact, exploitability, and
  evidence confidence, including attributable human overrides.
- Signed, scoped, expiring authorization grants and default-deny RBAC.
- AES-256-GCM evidence encryption, centralized redaction, endpoint allowlisting,
  retention controls, and tamper-evident audit chains.
- Append-only finding reviews, sanitized reports, encrypted exports, consistent
  online backups, integrity verification, and restore-to-new-path safeguards.
- Prometheus-compatible metrics, HTTP liveness/readiness service, production
  alert rules, and structured health diagnostics.
- Multi-stage non-root container, read-only Compose runtime, dropped
  capabilities, resource limits, and digest-pinned base image.
- Locked dependencies, hash-verified runtime installation, CI matrices,
  dependency/source/container scanning, SBOM generation, and provenance
  workflows.
- Consolidated release verifier, non-egressing image scanner, and real local
  Ollama acceptance drill.
- Architecture, methodology, deployment, governance, retention, monitoring,
  readiness, security, and incident-response documentation.

### Changed

- `pyproject.toml` is the sole package/dependency authority.
- Durable campaigns are the supported production execution path.
- Randomized prompt generation and mock-provider behavior are fully seedable.
- Provider retry logic honors bounded `Retry-After` and jitter.
- Runtime cryptography is upgraded to `48.0.1`.
- Container base is upgraded and digest-pinned to Python 3.12.13 on Debian
  12.15 after remediation of release-gate findings.
- SQLite schema is version 5; evaluator and scoring contracts are version 2.0.
- Keyword evaluator now Unicode-normalises typographic punctuation (curly
  quotes, en/em dashes, narrow no-break spaces) before matching, and the
  bundled `data/jailbreak_keywords.json` dataset (now version 1.1) expands
  refusal and compliance-opener coverage. Real model output frequently uses
  these code points, and without normalisation common refusals and
  compliances fell through to `indeterminate`. The evaluator contract
  version is unchanged: the output schema and taxonomy are identical, only
  match recall improves. Regression benchmarks still pass at F1 1.0.

### Security

- Closed fixed HIGH/CRITICAL findings discovered during offline image scanning.
- Added explicit loopback defaults and opt-in remote binding for observability.
- Hardened real-target exports, database evidence, endpoint validation, audit
  attribution, and production-key readiness checks.
- Pinned Hugging Face Hub revisions on `from_pretrained`/`load_dataset` calls
  touched by the reporting/import tooling (Bandit B615).
- Bumped locked `pip` `26.1.2` → `26.2.1` (patches `PYSEC-2026-3721`),
  caught by the `security` CI workflow's `pip-audit` step.

### Known boundaries

- Single trusted host only; distributed execution requires a new persistence,
  queue, identity, and rate-limit architecture.
- HMAC authorization is not a multi-organization trust solution.
- Checked-in evaluator/scoring datasets are deterministic regression fixtures,
  not universal claims of model safety.
