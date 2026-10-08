# Invoice Filler API

## Purpose

This document describes the HTTP API for the invoice filler MVP. The API is intended
for a browser client and a single configured Google Docs template. It does not expose
Google credentials, allow users to select arbitrary templates, or persist invoices.

## General conventions

- Base path: `/api`
- Transport: HTTPS in deployed environments
- Request and JSON response encoding: UTF-8
- JSON media type: `application/json`
- Dates: ISO 8601 calendar dates in `YYYY-MM-DD` format
- Monetary values: decimal strings, never binary floating-point JSON numbers
- Currency: uppercase ISO 4217 code, for example `EUR`
- Request IDs: returned in the `X-Request-ID` header and included in error bodies
- Sensitive values must not appear in URLs, logs, request IDs, or error messages
- Generated PDFs should use `Cache-Control: no-store`

The backend is authoritative for template configuration, field detection, validation,
normalization, calculations, and generated output. The client must not be trusted to
provide a calculated total or template identifier.

## Endpoints

### `GET /auth/google`

Starts the Google OAuth 2.0 authorization-code flow. The backend generates a
single-use state value and redirects to Google; client secrets and tokens never
appear in the browser URL.

### `GET /auth/google/callback`

Validates the one-time state, exchanges the authorization code server-side, and
creates a process-local session cookie with `Max-Age=3600`, `Path=/`, `HttpOnly`,
and `SameSite=Lax`; `Secure` is added in production. The callback always mints a
new opaque session ID, preventing session fixation. Access-token refresh rotates
the server-side access token without exposing or changing the browser cookie.
Invalid state, denied consent, revoked authorization, and provider failures return
safe classified errors. Durable encrypted session/token storage is follow-up #24.

### `POST /auth/logout`

Deletes the current process-local session and expires the session cookie.

### `GET /api/session`

Returns only authentication state and sanitized user identity metadata. When OAuth
is not configured it returns `{"authenticated":true,"auth_required":false}` for
the credential-free fixture workflow.

### `GET /api/health`

Returns a lightweight liveness response. It should not require Google credentials or
make a provider call.

Successful response:

```http
200 OK
Content-Type: application/json
```

```json
{
  "status": "ok"
}
```

The configured Google provider reads and fills the template with a service
account using only `documents` and `drive.file` scopes. It accepts a
secret-mounted JSON path or `file://` URI through
`GOOGLE_CREDENTIALS_REFERENCE`; credential contents are never returned or logged.
The provider verifies the configured file is a non-trashed Google Doc, then
normalizes body, table, header, footer, and split text-run locations. Filling
uses a temporary Drive copy and Docs `replaceAllText` requests, followed by PDF
export and cleanup. Authentication, missing-template, permission, and transient
provider failures are reduced to safe provider error classes.

The local fixture and mocked Google-provider tests run in the default suite. A
real Google check must use a disposable document shared with the service account;
it is intentionally not part of the credential-free test command.

### `GET /api/ready`

Reports whether the service has the configuration required to handle requests. This
check may validate configuration locally, but should avoid mutating Google documents.

Successful response:

```json
{
  "status": "ready"
}
```

If required configuration is missing or unusable, return `503 Service Unavailable`
with the standard error format. Do not include credentials or secret values.

### Configuration

The application reads these environment variables at startup:

| Variable | Required | Meaning |
| --- | --- | --- |
| `INVOICE_ENVIRONMENT` | Yes | Environment label, such as `development` or `production` |
| `INVOICE_FRONTEND_ORIGIN` | Yes | One HTTP(S) browser origin, without a path |
| `GOOGLE_CREDENTIALS_REFERENCE` | Yes | Reference to externally managed Google credentials; not credential contents |
| `GOOGLE_TEMPLATE_ID` | Yes | Configured Google Docs template identifier |
| `INVOICE_MAX_REQUEST_BYTES` | Yes | Positive request-body limit, maximum 10 MiB |
| `INVOICE_MAX_RESPONSE_BYTES` | Yes | Positive response limit, maximum 50 MiB |
| `GOOGLE_PROVIDER_CONNECT_TIMEOUT_SECONDS` | Yes | Positive provider connection timeout, maximum 300 seconds |
| `GOOGLE_PROVIDER_READ_TIMEOUT_SECONDS` | Yes | Positive provider read timeout, maximum 300 seconds |

Missing, malformed, or out-of-range values make readiness fail. Public errors only
identify the safe error class; they do not include configuration values or secret
references. Liveness does not load or validate Google configuration.

### `POST /api/template/connect`

Authenticates and reads a Google Docs template link through the configured
backend provider. The request body is:

```json
{"url":"https://docs.google.com/document/d/example/edit"}
```

The response contains an opaque `selection_token`, sanitized template metadata,
and mapped review fields. The browser sends that token in the
`X-Template-Selection` header for subsequent preview and generation requests;
it never sends a document ID directly. Malformed or non-Google links return
`400 invalid_template_url`. Missing access, invalid credentials, trashed/non-Doc
files, and provider failures return safe classified errors without document
contents or provider payloads: access denial is `403 template_access_denied`,
missing/non-Docs files are `404 template_not_found`, reauthorization is
`401 reauthorization_required`, provider outage is `503 provider_unavailable`,
and timeout is `504 provider_timeout`.

### `GET /api/metrics`

Returns aggregate request counts by bounded endpoint and status class, total request
duration by endpoint, and bounded operational event counters for provider failures,
cleanup failures, rate limiting, and suspicious volume. It never includes request bodies, query values,
credentials, document IDs, bank details, client identifiers, or PDF content. Platform
monitoring may scrape this endpoint or replace it with an authenticated metrics
exporter.

### `GET /api/template/fields`

Loads the configured template and returns the fields detected for user review. The
endpoint reads the master template but must never modify it.

Successful response:

```json
{
  "template": {
    "name": "configured-invoice-template",
    "version": "2026-01"
  },
  "fields": [
    {
      "name": "service_start_date",
      "label": "Service date",
      "type": "date",
      "value": "2026-09-30",
      "required": true,
      "calculated": false,
      "confidence": "high",
      "source": {
        "section": "body",
        "location": "table:0/row:1/cell:1"
      },
      "warnings": []
    },
    {
      "name": "total_amount",
      "label": "Total",
      "type": "money",
      "value": null,
      "required": true,
      "calculated": true,
      "confidence": "high",
      "source": {
        "section": "body",
        "location": "table:1/row:3/cell:1"
      },
      "warnings": []
    }
  ],
  "warnings": []
}
```

Confidence values are `high`, `medium`, or `low`. Ambiguous, missing, duplicate, or
unsupported matches must be represented in `warnings`; they must not be silently
selected as authoritative values.

### `POST /api/invoices/preview`

Validates invoice input, normalizes accepted values, and calculates the total without
creating a Google document or storing invoice data.

Request:

```json
{
  "service_start_date": "2026-09-01",
  "service_end_date": "2026-09-05",
  "days_worked": "5",
  "pay_per_day": "240.00",
  "currency": "EUR",
  "bank_name": "Example Bank",
  "account_holder": "Test Account Holder",
  "iban_or_account_number": "TEST-IBAN-0001",
  "swift_or_bic": "TESTBIC1"
}
```

Successful response:

```json
{
  "input": {
    "service_start_date": "2026-09-01",
    "service_end_date": "2026-09-05",
    "days_worked": "5",
    "pay_per_day": "240.00",
    "currency": "EUR",
    "bank_name": "Example Bank",
    "account_holder": "Test Account Holder",
    "iban_or_account_number": "TEST-IBAN-0001",
    "swift_or_bic": "TESTBIC1"
  },
  "calculation": {
    "total_amount": "1200.00",
    "currency": "EUR",
    "rounding": "2 decimal places, half-up"
  },
  "ready_for_generation": true
}
```

The backend calculates `total_amount` as `days_worked * pay_per_day`. The client may
display its own live estimate for usability, but the server response is authoritative.
`days_worked` is independent of the date range unless a separate business-day rule is
explicitly added to the product.

### `POST /api/invoices/generate`

Validates the request again, recalculates the total, copies the configured Google Docs
template, replaces confirmed values, exports the completed document to PDF, and cleans
up the temporary document.

Request body: same `InvoiceInput` schema as `/api/invoices/preview`.

The server must use its configured template and must ignore any client-provided
template ID or client-provided total. A request should be rejected if required field
detection warnings have not been resolved by the client workflow.

Successful response:

```http
200 OK
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice-2026-09-01.pdf"
Cache-Control: no-store
X-Request-ID: req_01...
```

The response body is the PDF bytes. The filename must be generated by the server and
must not contain unsanitized user input.

The endpoint must not return a successful PDF if copying, replacement, export, or
required validation fails. Cleanup must be attempted after a temporary document is
created, including failure paths.

## Shared input schema

`InvoiceInput` contains:

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `invoice_number` | string | Yes | Maximum 50 characters; whitespace normalized |
| `service_start_date` | string | Yes | `YYYY-MM-DD` |
| `service_end_date` | string | No | `YYYY-MM-DD`; define whether it may precede the start date |
| `days_worked` | decimal string | Yes | Non-negative, up to 366, with at most 2 decimal places |
| `pay_per_day` | decimal string | Yes | Non-negative, up to 1,000,000.00, with at most 2 decimal places |
| `currency` | string | Yes | Case-insensitive input; currently only `EUR` is supported and is normalized to uppercase |
| `bank_name` | string | No | Optional individually; maximum 200 characters; whitespace normalized |
| `account_holder` | string | No | Optional individually; maximum 200 characters; whitespace normalized |
| `iban_or_account_number` | string | No | Optional individually; maximum 34 characters after spaces are removed; normalized to uppercase |
| `swift_or_bic` | string | No | Optional individually; normalized to uppercase; must be 8 or 11 alphanumeric characters |

The initial implementation treats bank fields as optional individually. The API must
apply that rule consistently in preview, generation, and template replacement.

Dates are parsed as calendar dates and returned in `YYYY-MM-DD` form. An end date,
when supplied, may not precede the start date. Totals use decimal arithmetic and are
rounded to two decimal places using half-up rounding. Zero is accepted for workdays
and pay; `days_worked` is independent of the date range.

## Standard error format

All non-PDF errors should use this shape:

```json
{
  "error": {
    "code": "validation_error",
    "message": "One or more fields are invalid.",
    "request_id": "req_01...",
    "fields": [
      {
        "name": "pay_per_day",
        "code": "invalid_decimal",
        "message": "Enter a valid non-negative amount."
      }
    ]
  }
}
```

The `message` values are safe for end users. Provider details, stack traces, document
IDs, credentials, bank values, and complete invoice contents belong only in redacted
internal logs.

Recommended status and error codes:

| HTTP status | Code | Meaning |
| --- | --- | --- |
| `400` | `invalid_json` | Request body is malformed JSON |
| `400` | `validation_error` | One or more input fields are invalid |
| `409` | `field_review_required` | Detection is missing or ambiguous and needs user review |
| `413` | `request_too_large` | Request exceeds configured size limits |
| `429` | `rate_limited` | Caller exceeded the generation/request limit |
| `502` | `provider_error` | Google or another configured provider returned an unusable response |
| `503` | `service_not_ready` | Required configuration or dependency is unavailable |
| `504` | `provider_timeout` | Provider operation exceeded its timeout |
| `500` | `internal_error` | Unexpected server failure |

## Idempotency and retries

Preview requests should be safe to repeat. Generation requests may create temporary
Google documents, so retries must be bounded and observable. If the implementation
supports an `Idempotency-Key` request header, repeated requests with the same key and
same input should not create uncontrolled duplicate documents; otherwise the frontend
must prevent duplicate submissions and the backend must still clean up every created
copy.

## Security requirements

- No authentication is required for the initial product, but deployment-level abuse controls are required.
- Google credentials and the configured template ID remain backend-only configuration.
- Restrict CORS to the deployed frontend origin.
- Use HTTPS in production.
- Production configuration rejects an HTTP frontend origin.
- Do not log request bodies, bank fields, PDF bytes, or credentials.
- Apply request and response size limits.
- Generation is limited to ten attempts per client address per minute and returns
  `429 rate_limited` after the limit.
- Use `Cache-Control: no-store` for generated PDFs and sensitive JSON responses where appropriate.
- Return request IDs for support without deriving them from user or bank data.

## Compatibility and change rules

Changes to field names, calculation precision, error codes, or PDF response behavior
are API changes and should update this document, frontend types, contract tests, and
acceptance tests together. Additive response fields are preferred; removing or
renaming fields requires a deliberate versioning or migration decision.
