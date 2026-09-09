# Acceptable-Use Policy

## Purpose

Jailbreak Framework is intended for authorized defensive evaluation of language
models and the systems around them. It must not be used to gain unauthorized
access, evade lawful controls, harm people or systems, or collect unnecessary
sensitive data.

## Required authorization

Before any real-target request, the operator must have written authorization
from the system owner. The authorization must identify:

- target and environment;
- provider and model;
- permitted strategies and content categories;
- active testing window;
- maximum request, token, and cost limits;
- allowed evidence handling and retention;
- responsible operator and escalation contacts.

The framework encodes these constraints in a signed grant. A technically valid
grant does not replace legal or organizational approval.

## Permitted activities

- Testing systems owned by the operator.
- Testing third-party systems under explicit written authorization.
- Reproducing a finding with the minimum requests and data necessary.
- Developing and validating defensive evaluators, scoring systems, and
  mitigations.
- Sharing sanitized results with authorized reviewers and system owners.

## Prohibited activities

- Testing a target without explicit permission.
- Exceeding the signed target, provider, model, strategy, time, or request scope.
- Attempting to bypass provider billing, authentication, rate limits, or access
  controls.
- Using findings to facilitate abuse, fraud, harassment, surveillance, malware,
  credential theft, or physical harm.
- Collecting personal, confidential, or regulated data not required by the
  approved test plan.
- Publishing raw prompts, responses, credentials, customer identifiers, or
  exploit details without owner approval and disclosure review.
- Disabling RBAC, encryption, audit, or retention controls for real-target work.

## Operator obligations

Operators must minimize data, monitor budgets, pause on unexpected impact,
preserve auditability, and follow incident runbooks when sensitive content or
credentials are exposed. Automated findings require human review before
escalation, publication, or risk acceptance.

## Enforcement

Suspected misuse requires immediate campaign suspension, preservation of
sanitized audit evidence, credential review, and escalation to the designated
security owner. The deploying organization is responsible for legal,
regulatory, employment, and contractual enforcement.
