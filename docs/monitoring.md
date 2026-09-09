# Monitoring and Alerting

## Objectives

Monitoring must detect loss of readiness, provider degradation, repeated work
failures, queue backlog, and unexpected budget behavior without exposing
prompts, responses, credentials, or personal data.

## Observability service

Start on loopback:

```bash
.venv/bin/python main.py serve-observability \
  --host 127.0.0.1 \
  --port 9464 \
  --profile production
```

Endpoints:

| Path | Success | Purpose |
|---|---|---|
| `/health/live` | HTTP 200 | Process liveness |
| `/health/ready` | HTTP 200; 503 when unready | Database, output, config, keys, and RBAC |
| `/metrics` | HTTP 200 | Prometheus text format |

Responses use `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.
The service suppresses request logs to avoid accidental path/header exposure.

## Network security

The default bind is `127.0.0.1`. Non-loopback binds fail unless
`--allow-remote` is supplied. That option adds no TLS or authentication; use an
authenticated reverse proxy, service mesh, firewall, or collector sidecar.
Never expose the endpoint directly to an untrusted network.

## Metrics

Health metrics:

- `jbf_health_live`
- `jbf_health_ready`
- `jbf_health_check{check="..."}`

Runtime metrics include provider request/error/latency observations, evaluator
outcomes, campaign work-item transitions, and queue depth when those operations
occur in the serving process.

Metric labels must remain bounded. Do not use raw prompt, response, user,
customer, grant, or campaign content as labels.

## Alert rules

`deploy/monitoring/prometheus-rules.yaml` defines:

- `JBFNotReady`;
- `JBFProviderErrorRate`;
- `JBFCampaignWorkFailures`;
- `JBFQueueBacklog`.

Validate the YAML and PromQL with the organization's Prometheus toolchain before
deployment. Tune thresholds using expected campaign volume; do not simply
disable noisy alerts.

## Routing and ownership

For every alert, record:

- service and escalation owner;
- destination and fallback route;
- severity and response-time objective;
- maintenance-window behavior;
- linked runbook;
- last notification test and result.

Suggested mapping:

| Alert | Runbook |
|---|---|
| `JBFNotReady` | [Database Recovery](runbooks/database-recovery.md) or deployment diagnosis |
| `JBFProviderErrorRate` | [Provider Outage](runbooks/provider-outage.md) |
| `JBFCampaignWorkFailures` | Provider outage or application incident process |
| `JBFQueueBacklog` | Capacity, stuck-worker, and budget diagnosis |

## Acceptance test

1. Start the service with production-profile ephemeral test keys.
2. Verify live and ready endpoints.
3. Scrape `/metrics` and confirm health gauges.
4. Remove or invalidate a required test dependency and confirm readiness becomes
   HTTP 503.
5. Exercise alert expressions against a staging collector.
6. Confirm notification delivery and acknowledgement.
7. Stop the service and confirm the liveness alert path.

Do not use test keys or synthetic alert routes in production.
