# Load and security review

This is a credential-free plan and regression record. It must run only against the
fixture provider or an approved disposable environment. Never use production or
real invoice/bank data.

## Scenarios and gates

| Scenario | Workload | Pass/fail threshold | Owner | Status |
| --- | --- | --- | --- | --- |
| Preview baseline | 20 sequential valid requests | 100% `200`, no provider calls | `ROLE_SERVICE_OWNER` | PASS in automated suite |
| Preview malformed input | 20 invalid requests | 100% safe `400`, no sensitive echo | `ROLE_SERVICE_OWNER` | PASS in automated suite |
| Generation concurrency proxy | 11 requests from one client | Requests after 10 return `429`; no uncontrolled copy | `ROLE_SERVICE_OWNER` | PASS in automated suite |
| Oversized body | Body above configured limit | `413` before provider work | `ROLE_SERVICE_OWNER` | PASS in automated suite |
| Provider timeout | Fixture export timeout | `504`, cleanup attempted | `ROLE_SERVICE_OWNER` | PASS in automated suite |
| CORS/error leakage | Allowed and denied origins plus malformed data | Exact origin only; no bank/credential/PDF leakage | `ROLE_SECURITY_ESCALATION` | PASS in automated suite |

Production-like acceptance requires recording concurrency, duration, request limit,
provider latency, CPU/memory, error rate, and cleanup count for the approved
environment. The current automated checks are bounded functional safeguards, not a
claim of production capacity.

## Security findings

No unresolved findings in the credential-free review. Live Google access control,
platform hardening, and penetration testing remain owned by #TASK-8, #TASK-18,
and #TASK-21. Retest status must be updated here after those environments exist.
