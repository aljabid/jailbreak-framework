# Sensitive Data Incident Response

## Purpose

Use this runbook when prompts, responses, reports, audit metadata, credentials, or personal/confidential information may have been collected, exposed, retained, or transmitted contrary to policy.

## Immediate actions

1. Stop the affected campaign or service path.
2. Restrict access to affected databases, reports, logs, backups, and exported artifacts.
3. Assign an incident owner and record discovery time, environment, and affected data categories.
4. Preserve evidence without duplicating sensitive content into tickets or chat.
5. Engage the organization’s security, privacy, and legal contacts according to applicable policy.

## Assessment

Determine:

- what data was involved and its sensitivity classification;
- whose data was affected;
- the source, destination, and storage locations;
- the earliest and latest possible exposure times;
- whether encryption was active and whether the key may also be compromised;
- which users, systems, providers, or third parties accessed the data;
- applicable contractual, regulatory, and notification requirements.

## Containment and eradication

- Revoke exposed credentials and rotate affected keys using the credential-exposure runbook.
- Disable unauthorized principals, grants, or campaign scopes.
- Remove prohibited data from active systems only after evidence-preservation requirements are satisfied.
- Apply deletion consistently to reports, caches, backups, and replicas under the approved retention process.
- Correct the collection, redaction, authorization, or export path that caused the incident.

## Recovery

1. Validate configuration, authorization enforcement, encryption, and audit-chain integrity.
2. Test the corrected path with synthetic, non-sensitive data.
3. Restore service gradually while monitoring exports, provider traffic, and audit events.
4. Confirm that retention and deletion jobs operate as intended.

## Closure criteria

- Scope and impact are documented.
- Containment and required deletion are complete.
- Required notifications and contractual actions are complete.
- Controls preventing recurrence are tested.
- Follow-up actions have accountable owners and dates.

See [Credential Exposure Response](credential-exposure.md), [Data Retention](../data-retention.md), and the [Threat Model](../threat-model.md).
