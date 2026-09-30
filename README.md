# Invoice Filler

Initial project scaffold for the Invoice Filler MVP. The backend and frontend are
kept intentionally empty until their task is reached; no Google integration or
invoice behavior is included yet.

## Local development

The project currently has no third-party dependencies:

```sh
uv run python -m unittest discover -s backend/tests
cd frontend && npm test
```

The current smoke test can also be run with:

```sh
uv run python -m unittest discover -s backend/tests -t .
```

## Runtime configuration

The process can start without configuration so that liveness remains observable,
but `/api/ready` returns `503` until all of these variables are valid. Values are
read once when the application starts; credential references identify a secret
manager location and must not contain credential material.

```sh
export INVOICE_ENVIRONMENT=development
export INVOICE_FRONTEND_ORIGIN=http://localhost:3000
export GOOGLE_CREDENTIALS_REFERENCE=secret-manager://invoice/google
export GOOGLE_TEMPLATE_ID=template-id-placeholder
export INVOICE_MAX_REQUEST_BYTES=1048576
export INVOICE_MAX_RESPONSE_BYTES=5242880
export GOOGLE_PROVIDER_CONNECT_TIMEOUT_SECONDS=3
export GOOGLE_PROVIDER_READ_TIMEOUT_SECONDS=10
```

`INVOICE_ENVIRONMENT` and the origin are non-secret metadata. Request and response
limits are positive byte counts (up to 10 MiB and 50 MiB respectively), and provider
timeouts are positive seconds (up to five minutes). The health and readiness API
contracts are documented in [`_docs/api.md`](_docs/api.md).
