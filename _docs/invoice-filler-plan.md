# Invoice Filler Product Plan

## Product summary

This is a single-purpose invoice workflow, not a document-management or accounting
platform. The MVP helps one person fill one configured invoice template and download
the resulting PDF without creating an account.

## 1. Product goal

Build a small web application that uses an invoice template stored in Google Docs, collects invoice and bank details, calculates the total amount, and lets the user download the completed invoice as a PDF.

The initial product will not require user accounts or invoice history. A single Google Docs template will be configured by the application owner.

### MVP success criteria

The MVP is successful when a user can:

1. Open the app without an account.
2. Review the fields detected from the configured template.
3. Correct or complete invoice and bank details.
4. See a server-calculated total before generation.
5. Generate and download a valid PDF that preserves the template layout.

Suggested measurements include download completion rate, generation failure rate,
time from opening the form to download, and field-detection accuracy for the
supported template.

## 2. MVP user flow

1. User opens the web application.
2. The application loads the configured Google Docs invoice template.
3. The backend analyzes the document and detects likely fields, including:
   - Invoice date or service dates
   - Days worked
   - Pay per day
   - Total amount
   - Bank name
   - Account number or IBAN
   - SWIFT/BIC
   - Account holder
4. The frontend displays the detected values in an editable form.
5. The user enters or changes the dates, days worked, daily pay, and bank details.
6. The backend calculates the total:

   ```text
   total_amount = days_worked * pay_per_day
   ```

7. The backend creates a temporary copy of the Google Docs template.
8. It replaces the detected values in the copy.
9. It exports the completed document to PDF.
10. The frontend provides the PDF for download.

### Required user decision points

- Detection results are suggestions, not authoritative values.
- The user must confirm or edit detected fields before generation.
- Missing required fields block generation with an actionable error.
- The displayed total is calculated by the backend and is a preview until generation succeeds.

### Generation failure behavior

If copying, updating, exporting, or cleaning up fails, the API returns a safe,
user-readable error with a request ID. It must not return partial files, expose
Google API details, or silently claim that an invoice was generated. Cleanup should
run on every path after a temporary copy is created and should separately record
cleanup failures for operations follow-up.

## 3. Proposed architecture

```text
React frontend
    |
    | HTTPS/JSON
    v
Python FastAPI backend
    |
    +-- Google Drive API: copy and export template
    +-- Google Docs API: read and update document text
    +-- Field detection service
    +-- Invoice calculation service
    +-- Temporary document/PDF processing
```

### Frontend

- React with TypeScript.
- Form for invoice and bank details.
- Loading, validation, and error states.
- Review of detected fields, confidence warnings, and validation state before generation.
- Download button for the generated PDF.

### Backend

- Python 3.12+.
- FastAPI for HTTP endpoints.
- Pydantic models for request validation.
- Google API Python client libraries.
- Decimal arithmetic for monetary calculations.
- Temporary files only; no permanent invoice storage in the MVP.

### Boundary between frontend and backend

The browser may hold form state, but the backend is the source of truth for field
detection, the configured template, validation, normalization, monetary calculations,
Google credentials, document operations, and cleanup. The frontend must never send a
trusted total, template ID, Google document ID, or credentials as an authority-bearing
value.

## 4. Google Docs integration

The backend should use a configured Google Docs document ID as the master template.

- Use the Google Drive API to copy the template for each invoice.
- Use the Google Docs API to inspect document text and update the copied document.
- Export the copied Google document to PDF through the Drive API.
- Never modify the original template.
- Delete or trash the temporary copy after the PDF has been returned, subject to the chosen Google permissions model.

### Document lifecycle and replacement rules

1. Read the master template without changing it.
2. Create a uniquely identifiable, short-lived temporary copy.
3. Apply replacements to the copy in one controlled update operation where possible.
4. Export only after the update completes successfully.
5. Return the PDF with a safe filename derived from the invoice date.
6. Delete or trash the temporary copy after export, including error paths.

The replacement layer must account for Google Docs text runs being split across
structural elements. Define behavior for missing fields, duplicate matches, and fields
in headers, footers, or table cells. Ambiguous replacements must be surfaced for
review rather than silently changing every matching string.

Official references:

- [Google Drive API: download and export files](https://developers.google.com/workspace/drive/api/guides/manage-downloads)
- [Google Docs API: requests and responses](https://developers.google.com/workspace/docs/api/concepts/request-response)
- [Google Docs API: batchUpdate](https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/batchUpdate)

### Authentication options

For the simplest MVP, use a service account with access to one shared template document. If users later need to select templates from their own Google Drives, add Google OAuth and per-user Drive permissions.

## 5. Field detection strategy

Because the invoice may not contain placeholders, detection should use a layered approach:

1. Read paragraphs, tables, headers, and footers from the Google Doc.
2. Match known labels and synonyms, for example:
   - `days worked`, `days`, `number of days`
   - `daily rate`, `rate per day`, `pay per day`
   - `total`, `amount due`, `invoice total`
   - `IBAN`, `account number`, `bank`, `SWIFT`, `BIC`
3. Read the value near each matched label.
4. Return detected fields with confidence scores.
5. Require the user to review and correct fields before generation.

If detection is unreliable for a particular template, add a template-specific field configuration in the backend rather than requiring users to manually place markers.

### Detection contract

Each detected field should include a stable name and type, extracted value, source
location, confidence level and reason, required/optional/calculated status, and any
alternative candidates. The UI should make low-confidence and ambiguous matches
visible. A stored field map for the single supported template is the preferred
production path; heuristic detection can remain a setup or fallback path.

## 6. Data model

```text
InvoiceInput
- service_start_date: date
- service_end_date: date | optional
- days_worked: Decimal
- pay_per_day: Decimal
- currency: string
- bank_name: string | optional
- account_holder: string | optional
- iban_or_account_number: string | optional
- swift_or_bic: string | optional
```

The calculated total should not be accepted from the browser. The backend must calculate it from validated input.

Use decimal-safe representations at the API boundary, normalize currency and dates
explicitly, and define precision and rounding mode before implementation. Do not infer
`days_worked` from a date range unless a business-day rule is explicitly chosen; in
the MVP it is an independent user-entered value.

## 7. Suggested API

```text
GET  /api/template/fields
     Returns detected fields and their current values.

POST /api/invoices/preview
     Validates input and returns the calculated total.

POST /api/invoices/generate
     Copies the template, fills the values, creates a PDF, and returns it.
```

Recommended API behavior:

- `GET /api/template/fields` returns template metadata and detection warnings without exposing credentials.
- `POST /api/invoices/preview` returns normalized values, the calculated total, and validation errors without creating a document copy.
- `POST /api/invoices/generate` accepts the same validated input, recalculates the total, and returns `application/pdf` with a safe `Content-Disposition` filename.
- Use consistent 4xx responses for user-correctable issues and 5xx responses for provider failures.
- Add request IDs and bounded timeouts to provider calls so retries are diagnosable.

## 8. Security and privacy

- Use HTTPS in production.
- Keep Google credentials only on the backend.
- Do not expose the Google service-account key to React.
- Treat bank data as sensitive.
- Avoid logging bank details or complete invoice contents.
- Delete temporary document copies and generated files after download or after a short retention period.
- Encrypt stored secrets and use the narrowest Google API scopes possible.
- Validate dates, numeric values, currency, and maximum input lengths.
- Apply rate limiting or another abuse control to generation endpoints.
- Avoid putting bank details in URLs, query strings, analytics events, exception messages, or request IDs.
- Redact sensitive values in structured logs and error monitoring.
- Set upload/body size limits for future attachment support.
- Treat generated PDFs as sensitive responses: use no-store caching headers where appropriate and never persist them in logs.
- Define and test whether the Google service account may trash temporary files.

## 9. Implementation phases

### Phase 1: Project setup

- Create React and FastAPI projects.
- Add environment-based configuration.
- Add health-check endpoint and basic frontend page.
- Decide deployment topology, CORS policy, environment names, and secret injection.
- Add a local/mock provider so form and calculation work without live Google credentials.

### Phase 2: Calculation and form

- Implement invoice form.
- Validate dates, days worked, and daily pay.
- Calculate totals with `Decimal`.
- Add bank-detail fields and editing.
- Define required versus optional fields, date format, currency list, precision, and rounding behavior.
- Add a review state distinguishing detected values, user edits, validation errors, and calculated values.

### Phase 3: Google Docs template integration

- Configure Google credentials and template ID.
- Copy the template document.
- Read document content and detect fields.
- Replace values in the temporary copy.
- Inspect the real template and record a fixture/field map for every supported field, including table/header/footer locations.
- Verify missing, duplicate, split-run, and already-filled values.

### Phase 4: PDF generation

- Export the completed Google Doc as PDF.
- Return the file as a download response.
- Delete temporary artifacts.
- Set download metadata and verify that the PDF is non-empty and readable.
- Exercise provider timeouts, retries, partial failures, and cleanup failures.

### Phase 5: Review and hardening

- Add field-confidence warnings.
- Test multiple invoice layouts.
- Add automated tests for calculations and field detection.
- Add integration tests using a test Google document.
- Deploy frontend and backend separately.
- Add redacted operational logging, dependency health checks, and a short runbook for credential/template failures.
- Run an end-to-end test against a disposable Google document and a production-like template copy.

## 10. Testing requirements

- `days_worked * pay_per_day` produces the correct monetary total.
- Decimal values do not suffer from floating-point rounding errors.
- Invalid or negative values are rejected.
- Bank details can be changed without changing unrelated invoice content.
- The original Google Docs template is never modified.
- Generated PDFs contain the edited bank details and calculated total.
- Temporary files and document copies are removed.
- Boundary tests cover dates, currency, precision, rounding, and maximum lengths.
- Detection reports confidence and does not silently overwrite ambiguous or unrelated text.
- Header, footer, table-cell, multi-run, repeated-label, and missing-label cases are covered.
- Provider errors produce safe responses without leaking credentials or sensitive form values.
- Retries do not create uncontrolled temporary documents.
- PDF response headers, filename handling, no-store behavior, and empty/corrupt exports are tested.

## 11. Important MVP limitation

Automatic detection is the least predictable part of the product because invoice layouts vary. The application should always show the detected fields for confirmation before creating the PDF. A single known template can later receive a stored field map for more reliable replacement while keeping the user-facing workflow unchanged.

The MVP also deliberately supports one configured template and one invoice at a time.
There is no durable invoice history, draft recovery, collaboration, payment status, tax
engine, accounting export, or user-specific template selection.

## 12. Explicitly excluded from the MVP

- User accounts, teams, permissions, and invoice history.
- Multiple templates or user-owned Google Drive browsing.
- Automatic email delivery or accounting integrations.
- Tax/VAT calculation, discounts, currency conversion, and regional compliance rules unless added to the input contract.
- Invoice numbering, duplicate detection, payment tracking, reminders, or recurring invoices.
- OCR or arbitrary PDF/image template support.
- Permanent storage of generated PDFs or bank details.
- Automatic submission without user review.

## 13. Suggested repository structure

```text
invoice-filler/
  backend/
    app/
      main.py
      config.py
      schemas.py
      routes/
        template.py
        invoices.py
      services/
        google_docs.py
        field_detection.py
        invoice_calculator.py
        pdf_generator.py
    tests/
  frontend/
    src/
      components/
      pages/
      services/
      types/
  README.md
```

## 14. Definition of done for the MVP

- A user can open the app without creating an account.
- The app loads the configured Google Docs invoice template.
- The user can edit dates, workdays, daily pay, and bank data.
- The backend calculates the total correctly.
- The completed invoice preserves the template layout.
- The user can download a valid PDF.
- The original template and sensitive data are protected.
- Low-confidence or missing field detection is visible and actionable.
- Provider failures are recoverable or clearly reported, with no orphaned artifacts left by normal error paths.
- Automated tests cover calculation, detection, replacement, PDF generation, cleanup, and sensitive-data redaction.
- Deployment configuration, Google permissions, required environment variables, and a short operations runbook are documented.
