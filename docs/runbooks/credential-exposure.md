# Credential Exposure Response

## Purpose

Use this runbook when an API key, authorization signing key, encryption key, database credential, or other secret may have been disclosed, logged, committed, or accessed without authorization.

## Immediate actions

1. Stop affected workloads if continued execution could expand the exposure.
2. Record the discovery time, affected environment, suspected credential type, and incident owner. Do not copy the secret into the incident record.
3. Revoke or disable the exposed credential at its issuing system.
4. Issue a replacement through the approved secret-management process.
5. Remove the exposed value from runtime configuration, logs, artifacts, and deployment systems.

Do not delay revocation while attempting to determine whether the credential was used.

## Investigation

- Identify the earliest and latest possible exposure times.
- Review provider access logs, framework audit events, CI output, shell history, and artifact inventories.
- Determine which environments, campaigns, data stores, and external providers were reachable with the credential.
- Preserve relevant evidence using access-controlled storage and documented hashes.
- Treat encryption-key exposure as possible disclosure of every record protected by that key.

## Recovery

1. Deploy the replacement credential without printing it to logs or command output.
2. Restart affected services and confirm readiness.
3. Run a minimal authorized provider request where appropriate.
4. Validate the audit chain and inspect new events for unexpected principals or scopes.
5. Monitor provider error rates and authentication failures during the observation window.

## Special handling by credential type

### Authorization signing key

Rotate `JBF_AUTH_SIGNING_KEY`, restart all verifiers, and invalidate outstanding grants issued under the old key. Confirm new grants contain the expected principal, campaign, strategy, scope, and expiry.

### Data-encryption key

Rotate `JBF_DATA_ENCRYPTION_KEY` under a documented migration plan. Records encrypted with the previous key must remain decryptable only for the minimum migration period. Do not simply replace the key while encrypted records still depend on it.

### Provider API key

Revoke the key at the provider, review provider-side usage and billing, constrain the replacement key to the minimum required permissions, and test only after the old key is confirmed inactive.

## Closure criteria

- The exposed credential is revoked.
- Replacement credentials are deployed and verified.
- The exposure window and affected systems are documented.
- Unauthorized use has been assessed and contained.
- Required notifications have been completed.
- Corrective actions have owners and target dates.

See also [Sensitive Data Incident Response](sensitive-data-incident.md) and the project [Security Policy](../../SECURITY.md).
