# Invoice Filler

Invoice Filler is a small browser application for filling invoices automatically. It reviews invoice fields,
calculates a total and downloads a generated PDF with the final invoice. The
application uses a deterministic in-memory fixture provider for local development
and credential-free tests. A Google Docs provider is available for a secret-mounted
service-account credential and can fill an isolated copy of the selected template.

The application currently supports one configured template, does not persist
invoice data, and is not a production deployment.

Optional Google user sign-in is enabled when all OAuth variables are configured.
The configured scopes must include `openid`; the current local OAuth settings use
only `drive.file`, so they can open Google consent but cannot yet establish a
user session until the scope is updated and consent is granted again.

## Quick start

Requirements:

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)
- Node.js (for the frontend test command)

Install dependencies and run the test suites:

```sh
uv sync
uv run pytest
(cd frontend && npm test)
```

Start both local servers with the development defaults:

```sh
make run
```

To use a real Google template locally, copy [`.env.example`](.env.example) to
`.env`, set `GOOGLE_CREDENTIALS_REFERENCE` to the absolute path of the
service-account JSON file, and then run `make run`. `.env` is ignored by Git;
never commit the JSON file or its contents.

Then open [http://localhost:3000](http://localhost:3000). `make run` starts the
backend on `http://localhost:8000` and serves the static frontend on port 3000.
It stops existing processes listening on those two development ports first.

To start the services separately:

```sh
make backend
make frontend
```

The backend can also be started directly after exporting the required settings:

```sh
export INVOICE_ENVIRONMENT=development
export INVOICE_FRONTEND_ORIGIN=http://localhost:3000
export GOOGLE_CREDENTIALS_REFERENCE=fixture://local
export GOOGLE_TEMPLATE_ID=fixture-template
export INVOICE_MAX_REQUEST_BYTES=1048576
export INVOICE_MAX_RESPONSE_BYTES=5242880
export GOOGLE_PROVIDER_CONNECT_TIMEOUT_SECONDS=3
export GOOGLE_PROVIDER_READ_TIMEOUT_SECONDS=10
uv run python -m backend.run
```

For Google template access, set `GOOGLE_CREDENTIALS_REFERENCE` to an absolute
path or `file://` URI for a secret-mounted service-account JSON file. The
provider requests only the `documents` and `drive.file` scopes and requires the
service account to have access to the configured Google Docs template. It creates
an isolated temporary copy for replacement and deletes it after export. Never
commit the JSON file or put its contents in an environment variable.

## Local workflow

1. Enter invoice details in the browser.
2. Preview the invoice. The backend validates and normalizes the input and
   calculates `days_worked * pay_per_day` using decimal arithmetic.
3. Paste the Google Docs template link and wait for the backend to authenticate
   and read its mapped fields.
4. Review detected template fields and resolve any required warnings.
5. Generate the PDF. The backend validates and recalculates the values before
   exporting the fixture PDF; the browser downloads the resulting file.

The backend is authoritative for validation, calculations, template selection,
and generated output. The client cannot provide the total or choose an
arbitrary template.

## API overview

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Lightweight liveness check; does not require configuration |
| `GET /api/ready` | Reports whether startup configuration is valid |
| `GET /api/metrics` | Returns safe aggregate request/status/latency metrics |
| `POST /api/template/connect` | Authenticates a Google Docs link and loads mapped fields |
| `GET /api/template/fields` | Loads mapped fields for review |
| `POST /api/invoices/preview` | Validates input and calculates the total without creating a document |
| `POST /api/invoices/generate` | Creates a temporary fixture copy, replaces values, and returns a PDF |

See the [API contract](_docs/api.md) for request/response schemas, validation
rules, error formats, and security requirements.

## Configuration

All variables are read and validated at startup. In local development, the
defaults in [`Makefile`](Makefile) configure the fixture provider.

| Variable | Meaning |
| --- | --- |
| `INVOICE_ENVIRONMENT` | Environment label, such as `development` or `production` |
| `INVOICE_FRONTEND_ORIGIN` | The single allowed browser origin |
| `GOOGLE_CREDENTIALS_REFERENCE` | Reference to externally managed credentials; never credential contents |
| `GOOGLE_TEMPLATE_ID` | The configured template identifier (`fixture-template` locally) |
| `INVOICE_MAX_REQUEST_BYTES` | Positive request-body limit, up to 10 MiB |
| `INVOICE_MAX_RESPONSE_BYTES` | Positive response limit, up to 50 MiB |
| `GOOGLE_PROVIDER_CONNECT_TIMEOUT_SECONDS` | Provider connection timeout, up to 300 seconds |
| `GOOGLE_PROVIDER_READ_TIMEOUT_SECONDS` | Provider read timeout, up to 300 seconds |
| `GOOGLE_OAUTH_CLIENT_ID` | Google OAuth web client ID; backend configuration only |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Secret-managed OAuth client secret; never logged |
| `GOOGLE_OAUTH_REDIRECT_URI` | Exact registered callback URL |
| `GOOGLE_OAUTH_SCOPES` | Space-separated scopes; must include `openid` when enabled |
| `SESSION_SECRET` | Secret used for process-local session configuration |

Production requires an HTTPS frontend origin. Readiness returns `503` when a
required value is missing or invalid. Do not put credentials, real template IDs,
invoice data, bank details, or PDF contents in source control or logs.

## Repository layout

```text
backend/       Dependency-free WSGI backend, domain logic, provider boundary, and tests
frontend/      Static browser client and Node-based frontend tests
_docs/         API contract, operations runbook, product plan, testing guidance, and reviews
Makefile       Local development commands and fixture configuration defaults
```

Useful documentation:

- [API contract](_docs/api.md)
- [Operations runbook](_docs/operations.md)
- [Google OAuth setup](_docs/google-oauth-setup.md)
- [Testing guidelines](_docs/testing-guidelines.md)
- [MVP acceptance review](_docs/acceptance-review.md)
- [Product plan](_docs/invoice-filler-plan.md)

## Current scope and follow-up work

The repository has automated coverage for validation/calculation, field
detection, preview and generation, frontend behavior, provider failure paths,
cleanup, CORS, request limits, rate limiting, and sensitive-data handling.

Authentication and authorization are implemented when the OAuth configuration is
present; durable encrypted token/session persistence remains follow-up #TASK-24.

The following are intentionally outside the current MVP:

- Credential rotation and incident operations (#TASK-19)
- Load/penetration testing and platform provisioning (#TASK-20 and #TASK-21)

See the [acceptance review](_docs/acceptance-review.md) for the current status
and evidence.
