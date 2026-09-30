# Invoice Filler MVP Backlog

## 1. Set up an empty project with a passing test
Goal: Create the minimal project structure and verify that the test runner works.
Description: Set up the backend and frontend project directories, basic dependency/configuration files, and a documented local test command. Add the smallest passing backend and frontend tests supported by the chosen stack; do not connect to Google or implement product behavior.

## 2. Set up application configuration and health checks
Goal: Make the empty application runnable and observable in local, test, and production-like environments.
Description: Add typed settings for environment name, frontend origin, Google credentials reference, configured template ID, request limits, and provider timeouts. Add health and readiness endpoints, document required environment variables with placeholders, and test missing-configuration behavior without exposing secrets.

## 3. Implement invoice validation and calculation
Goal: Calculate a correct invoice total from validated input on the server.
Description: Define the invoice input, normalized response, and API error schemas for dates, workdays, daily pay, currency, and bank details. Validate required fields, non-negative values, maximum lengths, supported currency, decimal precision, and rounding; calculate `days_worked * pay_per_day` with decimal arithmetic and add boundary tests.

## 4. Implement the invoice preview endpoint
Goal: Let the backend validate invoice input and return the authoritative calculated total.
Description: Implement `POST /api/invoices/preview` using the shared invoice schemas and calculation service. Return normalized values, the calculated total, and field-level errors without creating Google documents or storing invoice data; add endpoint tests for valid, invalid, and boundary inputs.

## 5. Build the invoice form and connect preview
Goal: Let a user enter invoice details and see the server-calculated total before generation.
Description: Build the accessible React form for service dates, workdays, daily pay, currency, bank name, account holder, IBAN/account number, and SWIFT/BIC. Connect it to the preview endpoint, display normalized values and errors, and prevent generation while required input is invalid.

## 6. Define a document-provider interface and local test provider
Goal: Make document generation testable without Google credentials.
Description: Define the provider operations needed by the MVP: read the template, copy a document, replace values, export a PDF, and delete a temporary copy. Implement a deterministic fixture-backed provider and tests for successful operations, missing fields, duplicate matches, provider errors, and cleanup calls.

## 7. Inspect the supported template and create a field map
Goal: Capture the exact structure of the one invoice template supported by the MVP.
Description: Inspect a disposable or test copy of the Google Docs template and record each supported field’s label, value location, document structure, expected formatting, and required/optional status. Store sanitized fixtures and a template-specific field map covering any body text, table cells, headers, footers, or split text runs needed by the real template; do not commit real bank or invoice data.

## 8. Add Google authentication and template reading
Goal: Allow the backend to read the configured Google Docs template securely.
Description: Configure service-account authentication with the narrowest practical scopes and document the required sharing permissions. Implement template reading through the Google Docs API, normalize the supported document structures while preserving locations, and add an integration check that confirms the master template is never mutated and permission errors are safe.

## 9. Implement field detection and the template-fields endpoint
Goal: Return editable detected invoice fields with enough metadata for user review.
Description: Implement detection using the configured field map, with limited label/synonym matching only where required by the supported template. Return stable field names, types, values, source locations, required/calculated status, confidence, and warnings from `GET /api/template/fields`; handle missing, duplicate, already-filled, and ambiguous matches explicitly instead of silently choosing one.

## 10. Build the detected-field review interface
Goal: Let users review and correct detected template values before generation.
Description: Load detected fields from the backend and display them in an editable review form with confidence warnings, ambiguous candidates, missing-required-field errors, and a clear confirmation state. Preserve user edits across validation or preview failures and distinguish detected, user-edited, and calculated values.

## 11. Implement temporary document copying and value replacement
Goal: Apply confirmed values to an isolated copy without modifying the master template.
Description: Copy the configured template with a unique short-lived name, then replace only the mapped fields in the temporary document, including supported table, header, footer, and split-run cases. Test missing, duplicate, stale, and ambiguous fields, verify unrelated content and formatting remain intact, and ensure temporary names contain no sensitive user input.

## 12. Implement PDF export and generation orchestration
Goal: Generate a complete PDF from confirmed invoice data and clean up temporary documents.
Description: Implement `POST /api/invoices/generate` so the backend recalculates the total, copies the template, applies replacements, exports a non-empty PDF, and deletes or trashes the temporary copy on success and failure. Return `application/pdf` with a safe date-based filename, request ID, bounded provider timeouts, no-store headers, and safe errors for copy, update, export, or cleanup failures.

## 13. Connect the review flow to PDF download
Goal: Let a user generate and download the completed invoice from the browser.
Description: Add the generate action to the reviewed form with disabled, loading, success, and failure states. Download only successful PDF responses, preserve form values on retryable failures, prevent duplicate submissions, and show a clear message when the backend cannot complete generation.

## 14. Add MVP security and privacy controls
Goal: Protect bank data, credentials, generated PDFs, and the generation endpoint.
Description: Configure production HTTPS assumptions, restrictive CORS, request/body limits, and rate limiting or an equivalent abuse control. Add redacted structured logging and verify that bank details never appear in URLs, analytics, request IDs, exception messages, logs, temporary filenames, or provider error responses.

## 15. Add automated integration and failure-path tests
Goal: Verify the complete MVP workflow without risking the master template.
Description: Test the flow from detected fields through calculation, review payload, temporary copy, replacement, PDF export, response handling, and cleanup using fixtures or a disposable Google document. Cover invalid input, low-confidence detection, provider timeouts, empty/corrupt exports, retry behavior, cleanup failures, and the invariant that the original template is unchanged.

## 16. Document deployment and operational setup
Goal: Make the MVP deployable and maintainable by someone other than its author.
Description: Document build and test commands, environment variables, frontend/backend deployment topology, CORS configuration, Google API scopes, service-account sharing, template configuration, and cleanup permissions. Add a short runbook for credential failures, template changes, provider outages, orphaned temporary documents, and sensitive-data incidents.

## 17. Perform MVP acceptance review
Goal: Confirm that the first version meets the product definition of done.
Description: Walk through the unauthenticated user flow with the supported template: load fields, correct values, preview the total, confirm fields, generate the PDF, download it, and retry after a simulated failure. Record any deviations or deferred features, verify the explicit MVP exclusions, and only then mark the MVP complete.
