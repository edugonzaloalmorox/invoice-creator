# Platform monitoring and provisioning specification

This document is the platform-owner handoff for #TASK-21. It defines sanitized
resources and thresholds without claiming that a production account or environment
already exists.

## Ownership and environments

| Resource | Owner | Environment | Access |
| --- | --- | --- | --- |
| Static frontend host | `ROLE_PLATFORM_OWNER` | `staging`, `production` | least-privilege deploy role |
| Backend WSGI service | `ROLE_SERVICE_OWNER` | `staging`, `production` | least-privilege runtime role |
| Secret manager | `ROLE_SECRET_OWNER` | `staging`, `production` | runtime read; owner write |
| Disposable fixture/provider environment | `ROLE_QA_OWNER` | `test` | no production credentials |

Deploy permissions are separate from runtime permissions. Backups and retention must
exclude request bodies, bank data, credentials, raw PDFs, and document contents.
Set a recovery point objective of 24 hours for configuration/runbook metadata and a
recovery time objective of 4 hours for the service; confirm platform-specific values
before production approval.

## Metrics, dashboards, and alerts

Track endpoint, status class, latency, readiness, provider operation class, cleanup
success/failure, rate-limit count, and aggregate suspicious-volume events. The
generation limiter bounds remembered client buckets to 1,000; metrics never expose
the client addresses. Suggested initial alerts:

The backend exposes safe aggregate request/status/latency data and bounded provider,
cleanup, and rate-limit event counters at `GET /api/metrics`. It is suitable for a
disposable/local scrape; production must place it behind the approved monitoring
path or replace it with an authenticated exporter. Suspicious-volume alerts should
use aggregate rate-limit and request counters rather than request bodies, client
identifiers, or document content.

- Availability: `/api/health` below 99.5% over 5 minutes.
- Readiness: any sustained `503` for 5 minutes or 3 consecutive failed probes.
- Latency: p95 preview above 1 second or generation above 30 seconds for 5 minutes.
- Provider: 5 or more `502/504` responses in 5 minutes.
- Cleanup: any cleanup failure, or 2 failures in 15 minutes.
- Abuse: rate-limit responses above 20/minute from one client or a 5x suspicious
  volume increase over the 24-hour baseline.

Dashboards and alerts must contain aggregate counts and sanitized request IDs only;
never bank fields, credentials, document contents, PDFs, or raw provider payloads.

## Failure drill record

Run the credential-free drill with:

```sh
python3 scripts/failure_drill.py
```

The drill records sanitized evidence for a fixture-provider export timeout:

| Stage | Evidence |
| --- | --- |
| Detection | `504 Gateway Timeout` and a successful metrics response |
| Escalation | `ROLE_SERVICE_OWNER` recorded as the escalation owner |
| Mitigation | Provider failure counted and temporary-copy deletion verified |
| Recovery | A fresh fixture app returns `200 OK` from readiness |

The script prints only statuses, role names, and aggregate counters. It does not
print invoice values, document IDs, credentials, request IDs, or provider payloads.
The platform owner must repeat the drill with approved alerting and record
timestamps, notification evidence, and recovery owners in the deployment system.
