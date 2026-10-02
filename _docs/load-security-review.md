# Load and security review

This is a credential-free plan and regression record. It must run only against the
fixture provider or an approved disposable environment. Never use production or
real invoice/bank data.

## Scenarios and gates

| Scenario | Workload | Pass/fail threshold | Owner | Status |
| --- | --- | --- | --- | --- |
| Preview baseline | 20 sequential valid requests | 100% `200`, no provider calls | `ROLE_SERVICE_OWNER` | PASS in automated suite |
| Preview concurrency | 20 simultaneous valid requests | 100% `200`, isolated identical totals | `ROLE_SERVICE_OWNER` | PASS in automated suite |
| Preview malformed input | 20 invalid requests | 100% safe `400`, no sensitive echo | `ROLE_SERVICE_OWNER` | PASS in automated suite |
| Generation concurrency proxy | 11 requests from one client | Requests after 10 return `429`; no uncontrolled copy | `ROLE_SERVICE_OWNER` | PASS in automated suite |
| Repeated provider timeout | 10 generation requests | 100% `504`; every temporary copy cleaned up | `ROLE_SERVICE_OWNER` | PASS in automated suite |
| Oversized body | Body above configured limit | `413` before provider work | `ROLE_SERVICE_OWNER` | PASS in automated suite |
| Provider timeout | Fixture export timeout | `504`, cleanup attempted | `ROLE_SERVICE_OWNER` | PASS in automated suite |
| CORS/error leakage | Allowed and denied origins plus malformed data | Exact origin only; no bank/credential/PDF leakage | `ROLE_SECURITY_ESCALATION` | PASS in automated suite |

Production-like acceptance requires recording concurrency, duration, request limit,
provider latency, CPU/memory, error rate, and cleanup count for the approved
environment. The current automated checks are bounded functional safeguards, not a
claim of production capacity. They exercise 20 sequential and 20 concurrent valid previews, 20 malformed
previews, 10 timeout generations, and an 11-request rate-limit boundary in the
fixture provider.

For an approved disposable HTTP environment, run the dependency-free synthetic
runner and retain only its aggregate JSON output:

```sh
python3 scripts/load_test.py --base-url https://disposable.example.test --endpoint preview --requests 20 --concurrency 4
python3 scripts/load_test.py --base-url https://disposable.example.test --endpoint generate --requests 10 --concurrency 2
```

The runner uses synthetic invoice values, reports status counts and min/max/average
latency, and never prints response bodies or provider payloads. Platform CPU/memory,
cleanup counts, and penetration results must still be captured by the approved
environment owner.

### Local fixture run

On 2026-10-02, the runner was executed against an isolated fixture-backed backend on
local port 8001. This is reproducible functional evidence, not a production-capacity
claim:

| Endpoint | Requests | Concurrency | Statuses | Average / max latency |
| --- | ---: | ---: | --- | ---: |
| Preview | 20 | 4 | `200: 20` | 5.73 / 26.22 ms |
| Generation | 10 | 2 | `200: 10` | 3.24 / 14.32 ms |

Command used:

```sh
python3 scripts/load_test.py --base-url http://127.0.0.1:8001 --endpoint preview --requests 20 --concurrency 4 --timeout 5
python3 scripts/load_test.py --base-url http://127.0.0.1:8001 --endpoint generate --requests 10 --concurrency 2 --timeout 5
```

## Security findings

The following register records the current credential-free review. `PASS` means the
check is covered by the listed automated test; `PENDING` means it requires the
approved disposable environment or a decision tracked by the linked follow-up.

| Finding/check | Severity | Evidence | Owner | Remediation or follow-up | Retest status |
| --- | --- | --- | --- | --- | --- |
| Injection and malformed input handling | High | `backend/tests/test_security.py`, `backend/tests/test_load_security.py` | `ROLE_SERVICE_OWNER` | Keep bounded parsing and safe error responses; rerun after request parsing changes | PASS: 2026-10-02 |
| CORS and error leakage | High | `backend/tests/test_security.py`, `backend/tests/test_load_security.py` | `ROLE_SECURITY_ESCALATION` | Preserve exact-origin checks and sanitized error bodies; rerun after middleware changes | PASS: 2026-10-02 |
| Artifact exposure and cleanup | High | `backend/tests/test_generate.py`, `backend/tests/test_load_security.py` | `ROLE_SERVICE_OWNER` | Keep temporary-copy cleanup and non-sensitive response headers; rerun after provider changes | PASS: 2026-10-02 |
| Dependency lock and runtime configuration | Medium | `pyproject.toml`, `uv.lock`, `backend/tests/test_configuration.py`; `uv run pytest` | `ROLE_SERVICE_OWNER` | Review dependency updates and validate bounds/timeouts/origin before each deployment | PASS: 2026-10-02 |
| Access control between users | Critical | No authenticated runtime exists in the MVP | `ROLE_IDENTITY_OWNER` | Implement and test the approved identity/session model under #TASK-18 | PENDING decision and implementation: #TASK-18 |
| Live provider authorization and platform hardening | High | Credential-free fixtures only | `ROLE_PLATFORM_OWNER` | Run against an approved disposable environment with sanitized credentials and record findings | PENDING environment: #TASK-21 |

No unresolved findings remain in the credential-free checks. The pending rows are
explicitly not represented as passes: live Google access control, platform
hardening, and penetration testing require #TASK-18 and #TASK-21 plus an approved
disposable environment. Retest this register whenever those follow-ups change.
