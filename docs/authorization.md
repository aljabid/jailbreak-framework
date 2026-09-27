# Authorization and Access Control

## Security objective

Every real-target campaign must be attributable and constrained before the
first provider request. Authorization grants define what may be tested; RBAC
defines what the current actor may do inside the framework. Both controls must
pass.

## Grant schema

A grant contains:

- schema and grant identifiers;
- issuer and timezone-aware issue/activation/expiry timestamps;
- allowed target identifiers;
- allowed providers and models;
- allowed strategies;
- maximum request count;
- HMAC-SHA-256 signature over canonical JSON.

Example unsigned grant:

```json
{
  "schema_version": "1.0",
  "grant_id": "SEC-2026-0142",
  "issued_by": "security@example.com",
  "issued_at": "2026-07-26T12:00:00Z",
  "not_before": "2026-07-26T12:00:00Z",
  "expires_at": "2026-07-27T12:00:00Z",
  "target_ids": ["internal-assistant"],
  "providers": ["local"],
  "models": ["approved-model"],
  "strategies": ["roleplay", "instruction_override"],
  "max_requests": 20
}
```

Wildcards are supported by policy but should be avoided in production grants.

## Signing

Signing should occur in a controlled environment separate from campaign
execution:

```bash
export JBF_ACTOR_ID="security-admin@example.com"
export JBF_ACTOR_ROLE="administrator"
export JBF_AUTHORIZATION_SIGNING_KEY="value-from-secret-manager"

.venv/bin/python main.py authorization sign \
  --input unsigned.json \
  --output signed.json
```

The output is written atomically with mode `0600`. Never put the signing key in
the grant, command history, logs, or source tree.

## Offline verification

Verify the exact requested scope without contacting a provider:

```bash
.venv/bin/python main.py authorization verify \
  --input signed.json \
  --target-id internal-assistant \
  --provider local \
  --model approved-model \
  --strategy roleplay \
  --request-count 10
```

Verification fails closed for an invalid signature, inactive/expired time
window, target/provider/model/strategy mismatch, or excessive request count.
The signed document hash is stored with the campaign for later attribution.

## RBAC

Actor identity and role are injected through:

```bash
export JBF_ACTOR_ID="operator@example.com"
export JBF_ACTOR_ROLE="campaign_operator"
```

RBAC is default-deny. Roles are `administrator`, `campaign_author`,
`campaign_operator`, `reviewer`, `auditor`, and `viewer`; `policy/access.py` is
the authoritative permission matrix. Production readiness fails when RBAC is
disabled.

## Key management

`JBF_AUTHORIZATION_SIGNING_KEY` must be at least 32 characters and supplied by a
secret manager or equivalent protected injection. Define rotation, emergency
revocation, access review, and audit procedures.

HMAC uses a shared secret: every verifier capable of checking signatures can
also create them. For multi-tenant, third-party, or cross-organization trust,
replace HMAC with an asymmetric signing service or organizational PKI while
preserving the same grant-policy interface.

## Operational controls

- Issue grants with the narrowest scope and shortest practical lifetime.
- Separate grant approval, signing, campaign operation, and finding review.
- Hash and retain the approved grant with the evidence record.
- Reject clock-skewed or timezone-naive documents.
- Pause immediately if actual target behavior exceeds expected impact.
- Treat a valid grant as necessary but not sufficient; written owner approval
  and acceptable-use obligations still apply.
