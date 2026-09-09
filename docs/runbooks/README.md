# Operations Runbooks

These runbooks define the minimum response procedures for the framework’s most important operational incidents.

| Scenario | Runbook |
|---|---|
| Secret, signing-key, or encryption-key disclosure | [Credential Exposure Response](credential-exposure.md) |
| SQLite corruption, loss, or failed migration | [Database Recovery](database-recovery.md) |
| Model provider failure or degradation | [Provider Outage Response](provider-outage.md) |
| Unauthorized sensitive-data collection or disclosure | [Sensitive Data Incident Response](sensitive-data-incident.md) |

Operators should adapt escalation contacts, notification deadlines, recovery objectives, and evidence-retention requirements to their organization before production use. Every exercise or incident should result in dated findings and assigned corrective actions.
