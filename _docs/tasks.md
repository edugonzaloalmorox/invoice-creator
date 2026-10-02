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

- [ ] Reviewer loads detected fields, corrects values, previews total, confirms fields, generates PDF, and downloads it successfully.
- [ ] Reviewer simulates generation failure, verifies a clear error, retries without losing values, and confirms no master-template mutation.
- [ ] Review records template version, environment, date, commands/results, and artifact outcome without sensitive data.
- [ ] Every deviation/deferred feature links to an existing follow-up (#TASK-18 through #TASK-21 or a newly numbered issue).
- [ ] Explicit exclusions—authentication, multiple templates, persistence, unsupported structures—are verified as excluded.
- [ ] MVP is accepted only when prior criteria and security/privacy checks pass; otherwise owning issue is reopened or linked.

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

When done, invoice data and generation are available only to authorized users under a documented account and access model.

## Acceptance criteria

- [ ] The supported identity provider, session lifecycle, authorization rule, and unauthenticated behavior are documented.
- [ ] Unauthorized users cannot read template fields, generate PDFs, or access another user’s artifacts.
- [ ] Session expiry, logout, revoked access, and provider outage have visible safe behavior.
- [ ] Tests cover authorization boundaries without real personal or bank data.

## Out of scope

- MVP unauthenticated flow, covered by #TASK-1 through #TASK-17.
- Organization roles and billing, moved to a future numbered issue.

## Constraints

- Do not add authentication to the MVP acceptance flow; use least-privilege storage and redact identity/bank data.

## 19. Add credential rotation and incident response operations

## Goal

When done, operators can rotate Google credentials, revoke compromised access, and respond to sensitive-data incidents with documented, tested procedures.

## Acceptance criteria

- [ ] Credential issuance, storage, rotation, revocation, and emergency disablement steps are documented.
- [ ] Incident steps identify containment, evidence preservation, notification/escalation, and recovery owners.
- [ ] Rotation can occur without committing secrets or exposing invoice/bank data in logs.
- [ ] A tabletop or automated check records that the procedures are executable.

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
