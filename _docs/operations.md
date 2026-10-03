# Operations runbook

This runbook describes the credential-free MVP and its documented deployment
boundary. It contains placeholders only; do not copy example credentials,
template IDs, invoice values, or bank details into a real environment.

## Build, test, and start

From a clean checkout:

```sh
uv sync
uv run pytest
cd frontend && npm test
cd ..
uv run python -m backend.run
```

The last command is a development server on
`http://127.0.0.1:8000`. It is not a production server. The deployment topology
for production is:

```text
browser -> TLS/reverse proxy -> static frontend host
                         \-> WSGI backend -> configured document provider
```

The local Makefile uses the deterministic fixture provider. A configured
non-`fixture://` credential reference selects the Google provider.
Production WSGI hosting, TLS termination, and platform provisioning are
follow-up work under #TASK-21.

## Configuration

All variables below are required at startup. Values are read once and readiness
remains `503` until validation succeeds.

| Variable | Example placeholder | Rules | Secret handling |
| --- | --- | --- | --- |
| `INVOICE_ENVIRONMENT` | `development` | Environment label | Non-secret |
| `INVOICE_FRONTEND_ORIGIN` | `http://localhost:3000` | One HTTP(S) origin, no path; HTTPS is required in production | Non-secret |
| `GOOGLE_CREDENTIALS_REFERENCE` | `secret-manager://invoice/google` | Reference only, never credential contents | Secret location; do not log |
| `GOOGLE_TEMPLATE_ID` | `template-id-placeholder` | Configured template ID; current fixture uses `fixture-template` | Backend-only; do not expose |
| `INVOICE_MAX_REQUEST_BYTES` | `1048576` | Positive, maximum 10 MiB | Non-secret |
| `INVOICE_MAX_RESPONSE_BYTES` | `5242880` | Positive, maximum 50 MiB | Non-secret |
| `GOOGLE_PROVIDER_CONNECT_TIMEOUT_SECONDS` | `3` | Positive, maximum 300 seconds | Non-secret |
| `GOOGLE_PROVIDER_READ_TIMEOUT_SECONDS` | `10` | Positive, maximum 300 seconds | Non-secret |

Production CORS allows only the configured frontend origin. Generation is limited
to ten attempts per client address per minute. Request bodies over the configured
limit are rejected before provider work. Health is `GET /api/health` and does not
require configuration; readiness is `GET /api/ready` and returns `503` when the
service cannot safely handle requests.

## Google provider setup boundary

The Google provider uses a dedicated service account with only the
required least-privilege scopes:

- `https://www.googleapis.com/auth/documents`
- `https://www.googleapis.com/auth/drive.file`

Mount the service-account JSON through the deployment secret manager and point
`GOOGLE_CREDENTIALS_REFERENCE` at its absolute path or `file://` URI. Share only
the configured template with the service account and record the template ID and
field-map version (`2026-01`) in deployment configuration. The provider reads
body, table, header, footer, and split-run text, then performs replacement only
on a temporary copy before export and cleanup. Never place a token, service-account
key, real template ID, or document contents in this repository.

## Google user sign-in

When user OAuth is enabled, register the exact `GOOGLE_OAUTH_REDIRECT_URI` and
configure `GOOGLE_OAUTH_SCOPES` with `openid` plus only the approved Drive/Docs
scope. The browser receives only a short-lived session cookie; authorization and
refresh tokens remain server-side. A missing `openid` scope prevents identity
creation and readiness fails safely. After changing scopes or redirect URIs,
re-authorize through `/auth/google` and verify `/api/session` before testing a
template connection.

For denied consent, invalid state, expired sessions, or revoked access, sign in
again rather than copying authorization codes or tokens into tickets. Durable
encrypted token/session persistence and refresh recovery are follow-up #24.
See [_docs/google-oauth-setup.md](google-oauth-setup.md) for the per-environment
Cloud project, consent, redirect, scope, Picker, and disposable-account checklist.

## Incident response

### Credential failure

1. Check `/api/ready` and the redacted provider error classification.
2. Verify the secret-manager reference and service-account permissions without
   printing the secret or token.
3. Disable generation at the reverse proxy if the provider is unavailable; keep
   liveness available for diagnosis.
4. Rotate or revoke credentials through the secret-management procedure in
   follow-up #TASK-19, not in application logs or source control.

### Template change or stale field map

1. Stop generation or return the service to not-ready.
2. Compare the configured template revision with field-map version `2026-01`.
3. Use a disposable copy to update and test the map; never test by mutating the
   production master.
4. Deploy the map and template version together, then verify `/api/template/fields`
   warnings before re-enabling generation.

### Provider outage or timeout

Observe `502 provider_error` and `504 provider_timeout` responses, provider latency,
and readiness. Do not retry uncontrolled generation requests. Temporary copies must
be deleted/trash-requested on every path; investigate any cleanup failure using the
sanitized request ID and provider operation, never a document ID in a public log.

### Orphaned temporary documents

Use the provider's isolated temporary-copy listing and a documented retention
window to identify copies created by the service account. Delete/trash only verified
temporary copies, preserve the master, and record counts rather than document
contents or IDs. Automating this inventory belongs to #TASK-21.

### Sensitive-data incident

1. Disable the affected endpoint at the proxy and preserve only redacted request IDs.
2. Do not copy bank details, credentials, PDFs, request bodies, or document contents
   into tickets or chat.
3. Revoke/rotate exposed credentials through #TASK-19 and assess provider access.
4. Check URLs, headers, logs, analytics, temporary names, and error payloads for
   leakage; document only synthetic reproduction values.

## Safe observability and rollback

Safe logs/metrics include the query-free endpoint, status class, latency, readiness state, provider
operation class, rate-limit counts, cleanup success/failure counts, and generated
request IDs. Never record request bodies, bank fields, credentials, PDF bytes,
document contents, or raw provider payloads.

Rollback is the previously verified application and matching field-map/template
version. Disable generation first, keep `/api/health` available, restore the last
known-good release, and verify readiness plus a synthetic fixture workflow before
re-enabling traffic. Ownership and escalation contacts are deployment-specific
placeholders and must be filled by the platform owner under #TASK-21.
