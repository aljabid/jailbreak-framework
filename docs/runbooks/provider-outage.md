# Provider Outage Response

## Purpose

Use this runbook when an external or local model provider is unavailable, timing out, rejecting authentication, rate limiting requests, or returning sustained invalid responses.

## Detection

Typical signals include:

- elevated `jbf_provider_requests_total{status="error"}`;
- campaign work failures or growing queue depth;
- readiness failures caused by required dependencies;
- provider-specific authentication, timeout, or rate-limit errors.

## Triage

1. Identify the affected provider, model, environment, and first observed failure.
2. Check provider status information and local network/DNS health.
3. Separate authentication failures from capacity, rate-limit, and service failures.
4. Confirm whether one campaign or all workloads are affected.
5. Preserve representative error metadata without recording prompts, responses, or secrets unnecessarily.

## Containment

- Pause new campaigns targeting the affected provider when retries would add load or cost.
- Allow bounded retries and backoff already in flight; do not create an unbounded retry loop.
- Keep durable queued work intact.
- If an approved fallback provider exists, require a new authorization grant when the provider or scope changes.
- Communicate degraded capability and expected impact to operators.

## Recovery

1. Confirm the provider reports recovery or the local dependency is healthy.
2. Perform one minimal authorized request.
3. Resume a small batch of durable work.
4. Watch provider error rate, latency, queue depth, and campaign failures.
5. Gradually restore normal concurrency.

## Closure criteria

- Provider success rate and latency are within the accepted operating range.
- Queued work is draining without duplicate execution.
- Paused campaigns have an explicit resume or cancellation decision.
- Unexpected cost or quota consumption has been reviewed.
- The incident timeline and corrective actions are recorded.

Do not silently change models or providers: that can alter behavior, cost, data handling, and authorization scope.
