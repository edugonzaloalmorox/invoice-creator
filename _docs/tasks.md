# Invoice Filler MVP backlog

Each numbered section is a groomed issue. The issue numbers are stable cross-reference targets (`#TASK-NUMBER`).

## 1. Set up an empty project with a passing test

## Goal

When done, a new contributor can install the existing toolchain, run documented backend and frontend commands, and see both smoke tests pass. The repository contains only the minimal application structure and no product or Google behavior.

## Acceptance criteria

- [x] Separate `backend` and `frontend` application/test locations exist with importable entry points.
- [x] Backend and frontend smoke tests pass using the exact commands documented in `README.md`.
- [x] A fresh checkout runs both commands without Google credentials, environment variables, or network access.
- [x] README documents supported runtimes and exact install/test commands.
- [x] No Google client, invoice calculation, HTTP endpoint, persistence, or document-generation behavior is included.

## Out of scope

- Runtime configuration and health/readiness, moved to #TASK-2.
- Invoice schemas/calculation, moved to #TASK-3.
- Product UI, moved to #TASK-5.

## Constraints

- Keep changes in `README.md`, `pyproject.toml`, `uv.lock`, `backend/`, `frontend/`, and tests.
- Do not add dependencies without approval; follow `_docs/testing-guidelines.md`.

## 2. Set up application configuration and health checks

## Goal

When done, the application has typed non-secret configuration and health/readiness checks that distinguish a running process from usable configuration.

## Acceptance criteria

- [x] Configuration covers environment name, frontend origin, Google credential reference, template ID, request/body limits, and provider timeouts.
- [x] Missing/invalid required configuration produces a safe readiness/startup error without secret values.
- [x] Health succeeds when the process is alive and does not require Google access.
- [x] Readiness is not-ready for absent/unusable configuration and ready only after validation succeeds.
- [x] Health/readiness status codes and JSON shapes are documented and tested.
- [x] Required variables and placeholders are documented; tests prove secrets are absent from responses/errors.

## Out of scope

- Google authentication/API calls, moved to #TASK-8.
- Production abuse controls, moved to #TASK-14.
- Deployment/runbook, moved to #TASK-16.

## Constraints

- Centralize typed configuration; do not read environment variables in handlers.
- Never log credential contents; follow `_docs/api.md` and `_docs/testing-guidelines.md`.

## 3. Implement invoice validation and calculation

## Goal

When done, the backend validates invoice input and calculates an authoritative total with decimal arithmetic and documented normalization rules.

## Acceptance criteria

- [x] Schemas cover dates, workdays, daily pay, currency, bank name, account holder, IBAN/account number, and SWIFT/BIC with requiredness documented.
- [x] Malformed dates and end-before-start are rejected; valid dates use one normalized format.
- [x] Workdays/pay reject missing, negative, non-numeric, over-limit, and excess-precision values as applicable.
- [x] Currency accepts only the supported code and normalizes case.
- [x] Bank fields enforce requiredness, length, and documented format rules without storing input.
- [x] Total equals `days_worked * pay_per_day` using decimal arithmetic and documented currency rounding.
- [x] Boundary tests cover zero/maximum values, date boundaries, precision, and field-level errors without echoing bank data.

## Out of scope

- HTTP routing, moved to #TASK-4.
- Browser validation, moved to #TASK-5.
- Template/provider validation, moved to #TASK-9 and #TASK-11.

## Constraints

- Reuse these schemas/calculator in #TASK-4 and #TASK-12; never use binary floating point for money.
- Follow `_docs/api.md` and `_docs/testing-guidelines.md`.

## 4. Implement the invoice preview endpoint

## Goal

When done, `POST /api/invoices/preview` validates an invoice and returns normalized values and the server-authoritative total without document creation or retention.

## Acceptance criteria

- [x] Valid input returns the documented success status with normalized values and calculated total.
- [x] Invalid JSON, missing body, wrong content type, and field validation errors return the documented field-level error shape.
- [x] Invalid input never returns a successful-looking total.
- [x] Boundary values accepted by #TASK-3 produce the same values/total through this endpoint.
- [x] The endpoint performs no Google calls, writes, persistence, or temporary-file creation.
- [x] Tests prove invoice/bank data is absent from logs, exceptions, and request identifiers.

## Out of scope

- PDF generation, moved to #TASK-12.
- Template detection, moved to #TASK-9.
- Browser integration, moved to #TASK-5.

## Constraints

- Reuse #TASK-3; follow `_docs/api.md`; disable caching for invoice data.

## 5. Build the invoice form and connect preview

## Goal

When done, an unauthenticated user can enter all invoice details, request a preview, and see normalized values, total, and errors without losing input.

## Acceptance criteria

- [x] Labeled controls exist for dates, workdays, daily pay, currency, bank name, account holder, IBAN/account number, and SWIFT/BIC; required fields are visible.
- [x] Keyboard users can reach controls, understand errors without color alone, and submit accessibly.
- [x] Valid submission calls preview and displays server-normalized values and total.
- [x] Invalid submission shows field-level errors and preserves every entered value.
- [x] Pending preview communicates loading and prevents duplicate requests.
- [x] Generation remains unavailable until required input has valid preview state.
- [x] Bank details never appear in URL, analytics payload, or debug output.

## Out of scope

- Detected-field review, moved to #TASK-10.
- PDF download, moved to #TASK-13.
- Full security controls, moved to #TASK-14.

## Constraints

- Read `_docs/design-system.md`; use the existing stack; treat backend totals as authoritative.

## 6. Define a document-provider interface and local test provider

## Goal

When done, generation code uses an interface for reading, copying, replacing, exporting, and cleaning documents, with deterministic credential-free fixtures.

## Acceptance criteria

- [x] The interface defines template read, copy, replacement, PDF export, and delete/trash operations.
- [x] Inputs, outputs, timeout/error behavior, and cleanup expectations are documented.
- [x] The fixture provider returns deterministic content and records call order.
- [x] Tests cover success, missing fields, duplicates, provider errors, and cleanup calls.
- [x] Fixtures contain no real bank, invoice, credential, or identifying data.
- [x] Provider errors are safely classified without exposing provider payloads.

## Out of scope

- Live Google authentication/API, moved to #TASK-8.
- Template field map, moved to #TASK-7.
- Orchestration, moved to #TASK-12.

## Constraints

- Keep concrete providers behind dependency injection; no network/Google credentials in unit tests.

## 7. Inspect the supported template and create a field map

## Goal

When done, the supported invoice template has a sanitized, versioned field map identifying every editable field, exact location, formatting, and requiredness.

## Acceptance criteria

- [x] A disposable/test copy is inspected, including body, table, header, footer, and split-run structures.
- [x] Every field has stable name, label, location, format, type, and required/optional status.
- [x] Matching rules and duplicate/ambiguous conditions are recorded.
- [x] Sanitized fixtures reproduce every supported structure without real data.
- [x] Template ID/version prevents silent use of an obsolete map.
- [x] The map and fixtures are consumable by detection and replacement tests.

## Out of scope

- Live Google API, moved to #TASK-8.
- Runtime detection, moved to #TASK-9.
- Replacement, moved to #TASK-11.

## Constraints

- Never commit a real template, credential, bank detail, or invoice; preserve location metadata.

## 8. Add Google authentication and template reading

## Goal

When done, the backend securely reads the configured Google Docs template with least-privilege credentials and proves the master is never mutated.

## Acceptance criteria

- [x] Authentication uses documented least-privilege scopes and a service-account/credential reference.
- [x] Required sharing permission and template configuration are documented without credentials.
- [x] Reads normalize supported body/table/header/footer/split-run structures while preserving locations.
- [x] Missing/invalid credentials, missing template, and permission errors are safely classified without secrets/provider payloads.
- [x] An integration check proves the master revision/content is unchanged.
- [x] Mock/disposable integration tests are separated from credential-free tests.

## Out of scope

- Detection, moved to #TASK-9.
- Copy/replacement, moved to #TASK-11.
- Deployment runbook, moved to #TASK-16.

## Constraints

- Do not log tokens, credential files, document contents, or bank data; bound calls using #TASK-2 and follow #TASK-6/#TASK-7.

## 9. Implement field detection and the template-fields endpoint

## Goal

When done, `GET /api/template/fields` returns stable reviewable fields and explicitly reports uncertainty rather than silently choosing matches.

## Acceptance criteria

- [x] Success includes stable name, type, value, source location, required/calculated status, confidence, and warnings.
- [x] Detection follows the field map and only documented required synonyms.
- [x] Missing required fields are marked incomplete; duplicates include all candidates and are ambiguous.
- [x] Already-filled values are surfaced with the documented state/warning.
- [x] Stale, unreadable, and unsupported structures yield safe errors/warnings, never fabricated values.
- [x] The endpoint does not mutate the template; tests prove this.

## Out of scope

- Review UI, moved to #TASK-10.
- Replacement, moved to #TASK-11.
- Authentication, moved to #TASK-8.

## Constraints

- Use stable names from #TASK-7, expose no unrelated document content, and document the response in `_docs/api.md`.

## 10. Build the detected-field review interface

## Goal

When done, users can inspect detected values, resolve/correct allowed fields, understand warnings, and confirm a complete payload before generation.

## Acceptance criteria

- [x] Every field from #TASK-9 displays label, value, type, source/state, and requiredness.
- [x] Low-confidence, ambiguous, and missing-required fields have visible text warnings and block unresolved confirmation.
- [x] User edits survive validation, preview, and retry failures.
- [x] Detected, user-edited, and calculated values are visually/state-wise distinct.
- [x] Confirmation shows the submission and enables generation only when required fields and preview are valid.
- [x] Loading, empty, backend-error, and retry states are accessible and preserve edits.

## Out of scope

- PDF generation/download, moved to #TASK-13.
- Provider replacement, moved to #TASK-11.
- Broad security controls, moved to #TASK-14.

## Constraints

- Read `_docs/design-system.md`; keep totals server-authoritative and use #TASK-9’s contract.

## 11. Implement temporary document copying and value replacement

## Goal

When done, confirmed values are applied only to a unique isolated copy, including all mapped structures, while unrelated content and formatting remain intact.

## Acceptance criteria

- [x] Each generation creates a unique short-lived copy whose name contains no sensitive input.
- [x] Replacements work for mapped body, table, header, footer, and split-run fixtures.
- [x] Only mapped fields change; unrelated content, structure, and formatting match the fixture comparison.
- [x] Missing, duplicate, stale, and ambiguous fields fail safely and are classified.
- [x] Tests prove the master is unchanged and record the temporary document ID.
- [x] Cleanup is requested after successful and failed replacement paths; cleanup failure is available to orchestration.

## Out of scope

- PDF/orchestration, moved to #TASK-12.
- Review/confirmation, moved to #TASK-10.
- Credentials, moved to #TASK-8.

## Constraints

- Use #TASK-6/#TASK-7; reject stale state or make it idempotent; never log sensitive values.

## 12. Implement PDF export and generation orchestration

## Goal

When done, `POST /api/invoices/generate` validates/recalculates, creates and updates an isolated copy, exports a non-empty PDF, and cleans up on every outcome.

## Acceptance criteria

- [x] Valid input recalculates server-side, copies the template, replaces values, exports a non-empty PDF, and deletes/trashes the temporary copy.
- [x] Response is `application/pdf` with safe date-based filename, request ID, and `Cache-Control: no-store`.
- [x] Invalid or stale confirmation data fails before mutation with safe field/classified errors.
- [x] Copy, replacement, export, timeout, empty/corrupt PDF, and cleanup failures have documented safe responses and bounded work.
- [x] Cleanup is attempted after every created copy; cleanup failure is observable without hiding the primary failure.
- [x] Tests prove the master is unchanged and no invoice data persists.

## Out of scope

- Browser download, moved to #TASK-13.
- Production abuse/HTTPS, moved to #TASK-14.
- Operational monitoring, moved to #TASK-16.

## Constraints

- Reuse #TASK-3, #TASK-6, and #TASK-11; apply #TASK-2 timeouts and safe redacted logging.

## 13. Connect the review flow to PDF download

## Goal

When done, a user can submit a confirmed review, download only a successful PDF, and retry recoverable failures without losing work or duplicating submissions.

## Acceptance criteria

- [x] Generate is disabled until confirmation and valid preview requirements are met.
- [x] Submission shows loading, prevents duplicates, and restores an actionable state.
- [x] Download starts only for successful `application/pdf` and uses the safe server filename.
- [x] Non-PDF, error, timeout, and network responses show clear failure and do not download.
- [x] Retryable failures preserve all form/review values and valid preview state.
- [x] No bank data appears in URLs, logs, or analytics.

## Out of scope

- Backend semantics, moved to #TASK-12.
- User authentication, moved to follow-up #TASK-18.
- Security infrastructure, moved to #TASK-14.

## Constraints

- Read `_docs/design-system.md`; use #TASK-12’s contract and do not infer success from HTTP 200 alone.

## 14. Add MVP security and privacy controls

## Goal

When done, production-like requests have restrictive transport/origin/body controls and bank data, credentials, PDFs, and identifiers are not leaked through application surfaces.

## Acceptance criteria

- [x] Production configuration documents HTTPS and rejects or prevents insecure deployment assumptions.
- [x] CORS allows only configured origins and is not wildcarded in production.
- [x] Oversized requests are rejected before expensive provider work.
- [x] Generation has rate limiting or equivalent bounded abuse control with documented tests.
- [x] Logs redact bank details, credentials, document/PDF contents, and sensitive fields.
- [x] Bank details never appear in URLs, analytics, request IDs, exceptions, provider errors, temporary names, or headers.
- [x] PDF responses are non-cacheable and failed requests leave no accessible artifacts.

## Out of scope

- Authentication/authorization, moved to follow-up #TASK-18.
- Credential rotation/incident operations, moved to follow-up #TASK-19.
- General deployment, covered by #TASK-16.

## Constraints

- Preserve unauthenticated MVP flow; use #TASK-2/#TASK-6 boundaries and add regression tests for every control.

## 15. Add automated integration and failure-path tests

## Goal

When done, automated tests prove the complete credential-free MVP workflow and failure/cleanup invariants without modifying a master template.

## Acceptance criteria

- [x] An integration test covers detection, review payload, calculation, copy, replacement, PDF export, response, and cleanup.
- [x] Tests cover invalid input, low-confidence/ambiguous detection, timeout, empty/corrupt export, retryable failure, and cleanup failure.
- [x] Tests prove the original fixture/document is unchanged after success and every failure.
- [x] Tests verify duplicate submissions do not duplicate work where promised.
- [x] Tests verify sensitive data is absent from logs, URLs, IDs, temporary names, and errors.
- [x] Documented backend/frontend test commands run the relevant suite from a clean checkout.

## Out of scope

- New behavior not required by another issue, moved to that issue.
- Production load/penetration testing, moved to follow-up #TASK-20.
- Manual acceptance walkthrough, moved to #TASK-17.

## Constraints

- Use #TASK-6 fixtures; default suite requires no Google credentials; follow `_docs/testing-guidelines.md`.

## 16. Document deployment and operational setup

## Goal

When done, another engineer can build, configure, deploy, operate, and troubleshoot the MVP using repository documentation alone.

## Acceptance criteria

- [x] Exact backend/frontend build, test, start commands and deployment topology are documented.
- [x] All environment variables, defaults/required status, origins, limits, and secret-handling rules are documented.
- [x] Google APIs/scopes, service-account sharing, template ID/version, and cleanup permissions are documented.
- [x] Runbook covers credential failures, template changes, provider outages, orphaned temporary documents, and sensitive-data incidents.
- [x] Runbook identifies safe logs/metrics, health/readiness behavior, rollback/disable steps, and ownership/escalation.
- [x] Docs contain placeholders/examples only, with no real credentials, bank data, invoice data, or production IDs.

## Out of scope

- Missing runtime controls, moved to #TASK-2, #TASK-8, or #TASK-14.
- Full on-call platform provisioning, moved to follow-up #TASK-21.
- Product acceptance sign-off, moved to #TASK-17.

## Constraints

- Keep docs synchronized with `_docs/api.md`, configuration, and provider behavior; use least-privilege scopes and secret storage.

## 17. Perform MVP acceptance review

## Goal

When done, the supported unauthenticated MVP flow has been exercised end to end, deviations and deferrals are recorded, exclusions are verified, and the MVP is accepted or returned to an issue with evidence.

## Acceptance criteria

- [x] Reviewer loads detected fields, corrects values, previews total, confirms fields, generates PDF, and downloads it successfully.
- [x] Reviewer simulates generation failure, verifies a clear error, retries without losing values, and confirms no master-template mutation.
- [x] Review records template version, environment, date, commands/results, and artifact outcome without sensitive data.
- [x] Every deviation/deferred feature links to an existing follow-up (#TASK-18 through #TASK-21 or a newly numbered issue).
- [x] Explicit exclusions—authentication, multiple templates, persistence, unsupported structures—are verified as excluded.
- [x] MVP is accepted only when prior criteria and security/privacy checks pass; otherwise owning issue is reopened or linked.

## Out of scope

- Fixes discovered during review, returned to the owning issue or a numbered follow-up.
- Features outside MVP, including accounts and multiple templates, tracked in #TASK-18 or a new issue.
- Long-term monitoring/load testing, moved to #TASK-20 and #TASK-21.

## Constraints

- Use a sanitized/disposable template and no real personal/bank data.
- Follow `_docs/process.md`; read criteria before and after review and retain evidence for every step.

## Follow-up issues

The following issues are intentionally outside the MVP but are real, linked backlog items rather than silent omissions.

## 18. Add user authentication and authorization

## Goal

When done, users can sign in with Google through an OAuth 2.0 authorization-code
flow, and every invoice/template operation is authorized against the signed-in
user rather than a shared service account.

## Acceptance criteria

- [x] Google OAuth 2.0 web-server authorization-code flow is documented and
  implemented with a registered redirect URI, validated `state`, and backend
  code exchange; access tokens and refresh tokens never pass through browser
  storage or URLs.
- [x] A successful callback creates or resumes a local user identity and a
  server-managed session; the session cookie has documented expiry, secure,
  HttpOnly, SameSite, logout, and rotation behavior.
- [x] Unauthenticated users can only access the documented sign-in/start routes;
  template reading, preview, generation, and artifact access require a valid
  session belonging to the requesting user.
- [x] Session expiry, logout, revoked Google consent, denied consent, invalid
  OAuth state, and Google/provider outage have visible safe behavior and do not
  disclose tokens or provider payloads.
- [x] Authorization checks prevent one user from reading another user’s template
  selection, invoice data, temporary document, or generated artifact.
- [x] Tests cover callback/state/session and authorization boundaries using fake
  identities and tokens, without real personal, bank, or Google data.

## Out of scope

- Encrypted refresh-token/session persistence, moved to #TASK-24.
- Google Cloud OAuth client, consent-screen, redirect-URI, and Picker setup,
  moved to #TASK-25.
- Template selection and Google Drive/Docs provider handoff, covered by #TASK-22.
- Organization roles and billing, moved to a future numbered issue.

## Constraints

- Use Google OAuth 2.0 authorization-code flow with offline access for backend
  provider calls; do not implement an implicit flow or put tokens in the frontend.
- Keep identity, session, token, invoice, and bank data redacted from logs,
  request IDs, URLs, analytics, and error responses.
- Follow `_docs/api.md`, `_docs/operations.md`, and
  `_docs/testing-guidelines.md`; do not add dependencies without approval.

## 19. Add credential rotation and incident response operations

## Goal

When done, operators can rotate Google credentials, revoke compromised access, and respond to sensitive-data incidents with documented, tested procedures.

## Acceptance criteria

- [x] Credential issuance, storage, rotation, revocation, and emergency disablement steps are documented.
- [x] Incident steps identify containment, evidence preservation, notification/escalation, and recovery owners.
- [x] Rotation can occur without committing secrets or exposing invoice/bank data in logs.
- [x] A tabletop or automated check records that the procedures are executable.

## Out of scope

- Initial credential setup, covered by #TASK-8 and #TASK-16.
- General application security controls, covered by #TASK-14.

## Constraints

- Never place real credentials or incident data in the repository; follow the deployment platform’s secret-management policy.

## 20. Perform production load and penetration testing

## Goal

When done, production-like capacity, abuse resistance, and common security attack surfaces have documented evidence and remediation owners.

## Acceptance criteria

- [ ] Load scenarios, concurrency, duration, limits, and pass/fail thresholds are documented.
- [ ] Tests cover preview, generation, provider timeout, rate limits, oversized requests, and cleanup under load.
- [ ] Security testing covers injection, CORS, error leakage, access control, artifact exposure, and dependency/runtime configuration.
- [ ] Findings have severity, owner, remediation/follow-up, and retest status; no real invoice/bank data is used.

## Out of scope

- Credential-free functional integration tests, covered by #TASK-15.
- Implementing remediations, which return to the owning issue or a new numbered issue.

## Constraints

- Run only against approved disposable environments and sanitized fixtures; do not test production without explicit authorization.

## 21. Establish long-term operational monitoring and platform provisioning

## Goal

When done, the deployed service has owned platform resources, actionable monitoring, alert thresholds, retention rules, and recovery procedures beyond the MVP runbook.

## Acceptance criteria

- [ ] Infrastructure ownership, environments, deployment permissions, backups/retention, and recovery objectives are documented.
- [ ] Metrics and alerts cover availability, readiness, latency, provider failures, cleanup failures, rate limiting, and suspicious volume.
- [ ] Dashboards and alerts avoid bank details, document contents, credentials, and raw PDFs.
- [ ] A failure drill records detection, escalation, mitigation, and recovery evidence.

## Out of scope

- MVP deployment/runbook documentation, covered by #TASK-16.
- Product behavior changes, which require a separate numbered issue.

## Constraints

- Use least-privilege platform access, bounded retention, and sanitized operational data; do not block MVP acceptance on this follow-up.

## 22. Connect a Google Docs template from the frontend

## Goal

When done, a signed-in user can authorize access to their Google Drive/Docs and
connect a selected invoice template to the existing review and fill flow. The
backend uses that user’s OAuth credentials for all Google operations and never a
shared service-account identity.

## Acceptance criteria

- [x] The initial template screen clearly shows the signed-in Google account,
  authorization state, and an accessible action to connect or re-authorize Drive.
- [x] The user can select a Google Docs template through the authorized Drive/Docs
  flow; if a URL is retained, it is accepted only after the backend verifies that
  the authenticated user can access that exact Google Docs file.
- [x] Loading shows an accessible pending state, prevents duplicate submissions,
  and preserves the selected link/selection across validation or network failure.
- [x] The backend obtains the current user’s OAuth credentials from the server-side
  session/token store, extracts and validates the document ID, and never accepts
  client-supplied identity, access tokens, or refresh tokens.
- [x] Unsupported links, malformed URLs, denied access, revoked consent, expired
  sessions, trashed/non-Docs files, and provider failures return safe actionable
  errors without leaking document contents, tokens, or provider payloads.
- [x] A successful response contains only the per-user opaque selection token,
  sanitized template identity, field-map version, and reviewable field metadata;
  raw document content and OAuth credentials are never returned.
- [x] Preview, replacement, export, cleanup, and generated-artifact access use the
  same authorized user/template boundary, and one user cannot use another user’s
  selection token.
- [x] Retry and back-navigation preserve the user’s selection and invoice edits
  without creating duplicate provider work.
- [x] Tests cover OAuth-authenticated success, access denial, revoked/expired
  authorization, invalid selection ownership, provider failure, duplicate
  submission, sensitive-value redaction, and successful handoff using mocked or
  disposable Google resources.

## Out of scope

- User identity, OAuth callback, session lifecycle, and authorization middleware,
  covered by #TASK-18.
- Encrypted token/session persistence and key management, covered by #TASK-24.
- Google OAuth client, consent-screen, redirect-URI, and Picker configuration,
  covered by #TASK-25.
- Arbitrary web URLs, folder browsing, multiple-template administration, and
  cross-organization sharing; these require a separately groomed follow-up.
- Changes to Google document copying, replacement, export, or cleanup semantics,
  covered by #TASK-11 and #TASK-12.

## Constraints

- Keep OAuth code exchange, token refresh, and Google API calls in the backend; the
  browser must never receive service-account material, refresh tokens, access
  tokens, or raw document content.
- Use the authenticated user’s Google credentials and least-privilege Drive/Docs
  scopes. Prefer a Picker/file-selection flow with `drive.file`; document and
  approve any broader scope required by pasted-link or copy/export behavior.
- Reuse the existing Google provider, field map, review state, and generation API;
  do not duplicate template parsing or invoice calculation in the frontend.
- Use the existing frontend styles and accessibility patterns; no
  `_docs/design-system.md` is currently present, so document any new visual
  decisions in the task implementation.
- Use sanitized/disposable fixtures and follow `_docs/testing-guidelines.md`.

## 23. Diagnose and repair authenticated Google Docs template connection

## Goal

When done, `POST /api/template/connect` uses the signed-in user’s OAuth 2.0
credentials to read an authorized Google Docs template in the target environment,
or it returns a correctly classified, actionable failure. The investigation must
account for the observed browser/server symptom that the CORS preflight succeeds
(`OPTIONS /api/template/connect` returns `204`) while the document contents are
not fetched. It must also retain the earlier reported `502 Bad Gateway` case:
`127.0.0.1 - - [02/Oct/2026 08:37:00] "POST /api/template/connect HTTP/1.1" 502 138`.

## Acceptance criteria

- [x] The failure is reproduced with a sanitized/disposable Google Docs template
  and a signed-in test identity; evidence separately records the browser request
  sequence and response for the `OPTIONS` preflight and the actual `POST`, and
  identifies whether the failure is in frontend API-origin/configuration,
  credentialed CORS/cookie handling, OAuth callback/state, token
  refresh/revocation, user permission, template access/type, or provider
  availability.
- [x] When the preflight returns `204`, the frontend still sends the actual
  credentialed `POST` with the expected JSON body, and the response includes the
  documented CORS headers; a preflight success is not treated as a successful
  template connection.
- [x] The authenticated `POST` reaches the intended backend route, accepts the
  session cookie under the documented local/deployed origin configuration, and
  obtains the current user’s server-side OAuth credentials rather than falling
  back to a shared service account or an unauthenticated request.
- [x] For a valid authorized Google Docs file, the backend completes the Docs/Drive
  read and returns the documented sanitized connection/field response; logs and
  public responses make clear whether failure occurred before or during provider
  access without exposing document contents.
- [x] OAuth authorization and refresh use the documented client configuration and
  scopes; client secrets, access tokens, refresh tokens, document IDs, and user
  identity details are absent from logs, URLs, request IDs, and public errors.
- [x] Permission-denied, revoked/expired authorization, missing or non-Docs files,
  provider-unavailable, timeout, malformed request, and missing-session cases map
  to documented safe status/code behavior without raw provider payloads.
- [x] A successful connection reads the template without mutating the master, and
  preview, generation, and cleanup continue through the authenticated user boundary.
- [x] Automated tests cover the diagnosed failure, including preflight plus actual
  POST behavior, credentialed origin/session handling, and the successful
  OAuth-authenticated path with mocked tokens or an approved disposable
  environment; the default suite remains runnable without network access or real
  credentials.
- [x] The runbook records OAuth consent, redirect, origin/cookie configuration,
  token-revocation, reauthorization, and safe recovery checks without real
  identifiers or secrets.

## Out of scope

- Initial user identity, OAuth callback, session lifecycle, and authorization,
  covered by #TASK-18.
- Encrypted OAuth token/session persistence and key management, covered by #TASK-24.
- OAuth client and consent-screen setup, covered by #TASK-25.
- Credential rotation or compromise response, covered by #TASK-19.
- Production platform provisioning or long-term monitoring, covered by #TASK-21.
- Changes to template parsing, field detection, replacement, export, or cleanup,
  covered by #TASK-7, #TASK-9, #TASK-11, and #TASK-12.
- General frontend/API deployment configuration unrelated to this connection
  flow, covered by #TASK-2 and #TASK-16.

## Constraints

- Keep OAuth code exchange, token refresh, and provider calls in the backend; never
  expose client secrets, access/refresh tokens, or raw document content to the browser.
- Reuse the existing provider/error contract and field-map/generation boundaries
  from #TASK-2, #TASK-7, #TASK-8, #TASK-9, #TASK-11, #TASK-12, and #TASK-22; do not
  silently turn an authorization failure into a successful-looking connection.
- Treat `OPTIONS 204` as only a CORS preflight result; verify the subsequent
  credentialed `POST` in browser/network and backend evidence before declaring the
  connection fixed.
- Use sanitized/disposable data, follow `_docs/api.md`, `_docs/operations.md`,
  `_docs/credential-rotation.md`, and `_docs/testing-guidelines.md`, and do not
  add dependencies without approval.

## 24. Persist OAuth sessions and user Google credentials securely

## Goal

When done, authenticated users can return to the application and the backend can
refresh Google access without exposing or losing per-user authorization state.

## Acceptance criteria

- [ ] A durable data model maps an internal user to the minimum identity fields,
  session records, encrypted OAuth refresh-token material, granted scopes, and
  revocation/expiry metadata.
- [ ] Refresh tokens are encrypted at rest with a documented key source and
  rotation/recovery procedure; plaintext tokens never appear in logs, URLs,
  analytics, exceptions, tests, or browser storage.
- [ ] Session lookup, expiration, rotation, logout, token refresh, revoked-token
  handling, and deletion/revocation behavior are implemented and tested.
- [ ] Data access is scoped by internal user identity; tests prove one user cannot
  read another user’s token, template selection, invoice, or artifact records.
- [ ] Backups, retention, deletion, and incident handling are documented without
  real identities or tokens.

## Out of scope

- OAuth login/callback and authorization middleware, covered by #TASK-18.
- Template selection and Google API handoff, covered by #TASK-22.
- Google Cloud OAuth client and consent-screen setup, covered by #TASK-25.
- Organization roles, billing, and team sharing, moved to a future numbered issue.

## Constraints

- Do not add a persistence or encryption dependency without approval; use the
  project’s approved datastore/key-management services and document the choice.
- Apply #TASK-14 privacy controls and follow `_docs/credential-rotation.md`.
- Use synthetic identities/tokens only in tests; default tests must not require a
  live database, Google account, or network.

## 25. Configure the Google OAuth application and template-selection flow

## Goal

When done, the deployed application has a verified Google OAuth client and a
least-privilege user flow for selecting authorized Google Docs templates.

## Acceptance criteria

- [ ] Google Cloud project APIs, OAuth consent screen, test/published user status,
  authorized origins, and exact redirect URIs are documented for each environment.
- [ ] Client IDs and secrets are supplied through secret management/configuration;
  no client secret, refresh token, or real user data is committed to the repository.
- [ ] The selected OAuth scopes are documented with their Drive/Docs capabilities,
  verification implications, and the reason each is required by read/copy/export.
- [ ] The preferred template-selection path uses Google Picker or an equivalent
  per-file authorization boundary; pasted links are either supported with an
  explicitly approved scope or rejected with an actionable explanation.
- [ ] Disposable-account checks cover consent, callback, refresh, file selection,
  inaccessible files, revoked access, and redirect/state failures.
- [ ] Operations documentation explains consent changes, test-user management,
  OAuth client rotation, redirect changes, and emergency disablement.

## Out of scope

- User login/session/authorization implementation, covered by #TASK-18.
- Encrypted token/session persistence, covered by #TASK-24.
- Template connection orchestration and review/generation handoff, covered by #TASK-22.
- Organization administration and billing, moved to a future numbered issue.

## Constraints

- Follow Google’s OAuth web-server guidance, use authorization code flow with
  `state` and offline access, and keep tokens on the backend.
- Use the narrowest approved scopes and sanitized/disposable Google resources.
- Follow `_docs/operations.md`, `_docs/api.md`, and
  `_docs/testing-guidelines.md`; do not add dependencies without approval.

## 26. Repair authenticated PDF generation after successful preview

## Goal

When done, an authenticated user can generate and download a PDF after a
successful template connection and preview. The temporary Google document used
for generation remains addressable through copy, replacement, export, and
cleanup, and provider failures are classified without exposing Google response
details.

## Evidence

- `POST /api/invoices/preview` succeeds with `200`.
- The browser preflight for generation succeeds with `204`.
- `POST /api/invoices/generate` fails with `502` and a `not_found` provider
  response after preview has completed.
- A generation attempt can also return `405 method_not_allowed` with the
  message `Only POST is supported.`, indicating that the client or an
  intermediate retry path is using the wrong HTTP method.
- The failing request was observed as
  `req_RT7xQtw1FoacEmf`; use it only for local log correlation, not as a
  permanent fixture value.

## Acceptance criteria

- [ ] An authenticated end-to-end generation flow succeeds after template
  connection and preview, returning a non-empty `application/pdf` with the
  safe filename and `Cache-Control: no-store`.
- [ ] The frontend sends exactly one credentialed `POST` request to
  `/api/invoices/generate` with the invoice payload and template-selection
  header; it never attempts `GET` for generation and does not retry with a
  different method.
- [ ] The document ID returned by the copy operation is the ID used for value
  replacement, PDF export, and cleanup; the master template is never mutated.
- [ ] Google API responses are inspected per operation so an export or cleanup
  `404` is not misreported as an unexplained generic failure; the client gets a
  stable safe error code and actionable retry or reauthorization guidance.
- [ ] Temporary documents are deleted or trashed after successful generation,
  provider failure, timeout, invalid/empty PDF, and cleanup failure; cleanup
  failure remains observable without hiding the primary error.
- [ ] Regression tests cover authenticated copy, replacement, export, and
  cleanup using the same temporary document ID, plus a provider `404` during
  export and a successful PDF response.
- [ ] Tests prove no invoice values, credentials, Google error payloads, or
  temporary document contents appear in logs or error responses.

## Debug task: Diagnose the remaining generation 404

- [ ] Capture the generation POST response body and `X-Request-ID` in browser
  DevTools. Confirm whether the error code is `template_not_found` or generic
  `not_found`.
- [ ] Verify effective runtime configuration without printing secrets:
  - [ ] OAuth scopes include `openid`, `email`,
    `https://www.googleapis.com/auth/documents`, and
    `https://www.googleapis.com/auth/drive.file`.
  - [ ] The user re-authenticated after any scope change.
  - [ ] The selected template token resolves to the same template ID used
    during preview.
- [ ] Add temporary sanitized operation logging around `copy_document`,
  `replace_values`, `export_pdf`, and `delete_document`. Log only request ID,
  operation, provider status, and safe error code; never log document IDs,
  tokens, invoice values, or Google error payloads.
- [ ] Reproduce with a disposable Google Doc by connecting the template,
  previewing an invoice, and generating a PDF. Confirm whether the failure
  occurs during Drive copy and that replacement/export are not attempted after
  a copy failure.
- [ ] Validate Google permissions and OAuth scopes specifically for Drive copy.
  If copying returns `404` while Docs reading succeeds, fix the OAuth
  configuration or change the temporary-copy strategy.
- [ ] Add a regression test with a provider that succeeds on Docs read but
  returns a Drive `404` on copy, and verify the response is safe and
  actionable.

Configuration red flag: the local `.env` may contain a standalone
scope-looking line instead of a `GOOGLE_OAUTH_SCOPES=...` assignment. Verify
the effective environment used by the running backend without exposing secret
values.

## Out of scope

- Initial OAuth login, callback, and session persistence, covered by #TASK-18
  and #TASK-24.
- OAuth client, consent screen, and production scope configuration, covered by
  #TASK-25.
- General frontend download behavior and retry UI, covered by #TASK-13.
- New persistence, background jobs, or a second PDF-generation provider.

## Constraints

- Reuse the provider interface and generation orchestration from #TASK-12 and
  the authenticated template-selection boundary from #TASK-22.
- Keep Google API calls and temporary-document cleanup in the backend; never
  expose document IDs, access tokens, or raw provider errors to the browser.
- Read `_docs/api.md`, `_docs/operations.md`, and
  `_docs/testing-guidelines.md`; use synthetic documents/credentials and do
  not add dependencies without approval.
