# Invoice Filler Testing Guidelines

## Purpose

These guidelines define how to test the invoice filler MVP from a test engineer’s
perspective. The goal is not only to prove that the happy path works, but also to
protect the values users care about most: correct totals, unchanged templates,
accurate PDFs, safe handling of bank data, and reliable cleanup of temporary Google
documents.

## Quality principles

### 1. Test user outcomes, not implementation details

Tests should verify what the user can observe or what the system must guarantee:
correct validation, correct totals, preserved layout, accurate PDF content, safe error
messages, and cleanup. Avoid coupling tests to private functions, framework internals,
or incidental response formatting unless those details are part of the API contract.

### 2. Use risk-based coverage

Prioritize testing where a defect could cause financial, privacy, or trust damage:

- Incorrect monetary calculations or rounding
- Wrong field replacement or altered template content
- Bank details appearing in logs, URLs, errors, or temporary names
- Generated PDFs containing stale or missing values
- The master template being modified
- Temporary Google documents remaining after failure
- Ambiguous field detection being treated as confirmed

Lower-risk presentation details should not delay coverage of these guarantees.

### 3. Keep tests deterministic and isolated

Tests must not depend on the current date, local timezone, network timing, shared
Google documents, or another test’s data. Use fixed clocks, explicit timezones,
controlled fixtures, unique test identifiers, and cleanup that runs even after a test
failure. Tests should be safe to run repeatedly and in parallel where practical.

### 4. Prefer the smallest test that proves the behavior

Use unit tests for pure calculations and transformations, contract tests for API
boundaries, integration tests for provider behavior, and end-to-end tests for the
critical user journey. Do not use a slow Google-backed test to prove behavior that can
be proved with a local fixture.

### 5. Every failure must be actionable

Failures should identify the request or fixture, expected behavior, actual behavior,
and relevant provider operation without exposing bank details or credentials. Tests
should distinguish a user-correctable validation error from a provider or deployment
failure.

## Test levels

### Unit tests

Use unit tests for deterministic domain behavior with no network or filesystem
dependency. Cover:

- Decimal multiplication, precision, rounding, and zero values
- Date parsing and normalization
- Required and optional field validation
- Currency and input-length validation
- Field-map lookup and ambiguity detection
- Document structure normalization
- Safe filename generation
- Error classification and sensitive-value redaction

### Component and frontend tests

Test form and review behavior through user-visible interactions. Cover accessible
labels, required-field feedback, confidence warnings, preservation of user edits,
preview loading and error states, disabled duplicate submissions, and successful PDF
download handling.

### API contract tests

Verify request and response schemas independently of Google. Cover valid input,
invalid input, decimal serialization, field-level errors, request IDs, content types,
safe filenames, no-store headers, and the distinction between 4xx validation errors
and 5xx provider errors.

### Integration tests

Use a fake or fixture-backed document provider to verify orchestration across services.
Cover copy, read, detection, replacement, export, and cleanup sequencing. Assert that
the calculated total is recomputed by the backend and that a client-supplied total or
template identifier cannot override server configuration.

### Google integration tests

Run Google-backed tests only against a disposable test document or isolated test
folder. Never use the production master template for mutation tests. Verify service
account permissions, document reading, table/header/footer handling, split text runs,
copying, export, and deletion/trashing. Keep these tests separately identifiable so
they can be skipped when credentials are unavailable without hiding failures in local
tests.

### End-to-end tests

Maintain at least one complete scenario that starts with loading detected fields and
ends with downloading a PDF. The scenario should confirm the PDF contains the edited
values and calculated total, the original template remains unchanged, and the
temporary document is removed.

## Required behavior coverage

### Monetary calculations

Test representative, boundary, and adversarial values:

- Whole numbers and decimal workdays where supported
- Smallest supported monetary unit
- Values requiring rounding
- Zero values if allowed
- Excessive precision
- Negative, blank, malformed, and extremely large values
- Currency formatting independent of the arithmetic result

The expected result must be calculated independently of the implementation under
test; do not use the same helper to calculate both expected and actual values.

### Dates and input validation

Test valid dates, invalid calendar dates, timezone-neutral handling, reversed ranges,
missing dates, maximum lengths, whitespace normalization, and unsupported currency
codes. Explicitly verify that `days_worked` is not silently inferred from a date range
unless that rule is deliberately added to the product.

### Field detection and review

Test high-confidence matches, low-confidence matches, missing fields, duplicate
labels, repeated values, already-filled fields, split text runs, table cells, headers,
footers, and unrelated text that resembles a label. Detection must produce warnings
for ambiguity and must never silently replace every matching string.

### Document preservation

Compare the generated document or PDF against the template’s expected structure.
Verify that replacements do not change unrelated text, tables, formatting, page
layout, headers, footers, or static legal/payment wording. Confirm that the master
template’s content and metadata are unchanged after every generation scenario.

### PDF generation

Verify that successful responses are non-empty, readable PDFs with the expected
content type, safe filename, and caching behavior. Test export timeout, empty output,
malformed output, provider permission failure, and a response that contains stale
values. A failed generation must never be presented as a successful download.

### Temporary-document lifecycle

For every path after a temporary copy is created, verify that cleanup is attempted:
success, replacement failure, export failure, timeout, client disconnect where the
runtime supports detection, and unexpected exceptions. Cleanup failures must be
observable without exposing document IDs or user data in public errors.

### Security and privacy

Use synthetic bank details in all automated tests. Add checks that sensitive values do
not appear in URLs, query strings, logs, request IDs, exception responses, analytics
payloads, filenames, test reports, screenshots, or committed fixtures. Test CORS,
request-size limits, rate limiting, credential isolation, and no-store behavior for
generated PDFs.

## Test data principles

- Use clearly synthetic values such as `TEST-IBAN-0001`; never use real bank details.
- Keep fixtures minimal and focused on one behavior.
- Include sanitized templates for each supported structural case.
- Version fixtures with the field-map or template version they represent.
- Make malformed and adversarial data intentional and clearly labeled.
- Do not place secrets in environment files committed to the repository.
- Remove generated documents and files even when assertions fail.

## Reliability and failure testing

Provider calls should be tested with controlled failures, including authentication
failure, permission denial, rate limiting, timeout, transient server error, malformed
response, and cleanup failure. Verify bounded retries where retries are allowed and
ensure retries do not create uncontrolled duplicate temporary documents.

Test repeated submissions, browser refresh during generation, concurrent generation
requests, and duplicate-click prevention. The MVP does not need durable job recovery,
but it must fail clearly and leave no normal-path orphaned artifacts.

## Acceptance criteria for the MVP

The MVP should not be considered ready until all of the following are demonstrated:

- A valid invoice can be previewed and generated end to end.
- Server-side totals match independently calculated expected values.
- Invalid and ambiguous input is blocked or clearly requires correction.
- The generated PDF contains the confirmed values and preserves the template layout.
- The original Google Docs template is never modified.
- Temporary documents are cleaned up on success and normal failure paths.
- Provider and validation errors are safe, distinguishable, and actionable.
- Automated tests cover sensitive-data redaction and no-store PDF handling.
- Tests run reliably without Google credentials, with Google-backed tests isolated.
- The deployment and test commands are documented and reproducible.

## Defect reporting

Every defect report should include:

- Short title describing the user-visible failure
- Environment and build/commit identifier
- Reproduction data using synthetic values only
- Exact steps to reproduce
- Expected and actual behavior
- Severity and impact, especially financial or privacy impact
- Relevant request ID or sanitized logs
- Whether the issue reproduces with the local provider, Google provider, or both

Never attach real invoices, bank details, credentials, or unredacted production logs
to a defect report.
