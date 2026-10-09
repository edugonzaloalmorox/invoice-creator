import test from "node:test";
import assert from "node:assert/strict";
import { apiOrigin, createInvoiceFormController, invoiceFields, renderTemplateConnection, requestLogout, requestPreview, requestSession, requestTemplate } from "../src/app.js";
import { requestGeneration } from "../src/review.js";

test("invoice form exposes all fields and keeps generation locked before preview", () => {
  const controller = createInvoiceFormController({ preview: async () => ({ ok: true }) });
  assert.equal(invoiceFields.length, 16);
  assert.deepEqual(invoiceFields.find(({ name }) => name === "invoice_number"), {
    name: "invoice_number", label: "Invoice number", type: "text", required: true, autocomplete: "off",
  });
  assert.deepEqual(new Set(invoiceFields.map(({ name }) => name)), new Set([
    "invoice_number", "service_start_date", "week_ending", "days_worked",
    "start_date_service", "finish_date_service", "pay_per_day", "currency",
    "amount", "subtotal", "total", "bank_name", "account_holder", "iban",
    "swift", "payment_reference",
  ]));
  assert.equal(controller.getState().canGenerate, false);
  controller.setValue("currency", "EUR");
  assert.equal(controller.getState().values.currency, "EUR");
});

test("pending preview prevents duplicate submissions and preserves values on errors", async () => {
  let resolvePreview;
  let calls = 0;
  const controller = createInvoiceFormController({
    preview: () => { calls += 1; return new Promise((resolve) => { resolvePreview = resolve; }); },
  });
  controller.setValue("bank_name", "TEST-BANK");
  const first = controller.submit();
  const second = controller.submit();
  assert.equal(calls, 1);
  assert.equal(controller.getState().status, "pending");
  resolvePreview({ ok: false, error: { fields: [{ name: "currency", message: "Use EUR." }] } });
  await first;
  await second;
  assert.equal(controller.getState().values.bank_name, "TEST-BANK");
  assert.equal(controller.getState().errors.currency, "Use EUR.");
  assert.equal(controller.getState().canGenerate, false);
});

test("preview request sends only the form payload", async () => {
  let request;
  const result = await requestPreview({ currency: "EUR", bank_name: "TEST-BANK" }, {
    fetchImpl: async (url, options) => {
      request = options;
      assert.equal(url, "http://localhost:8000/api/invoices/preview");
      return { ok: true, json: async () => ({ calculation: { total_amount: "1.00" } }) };
    },
  });
  assert.equal(request.method, "POST");
  assert.equal(JSON.parse(request.body).bank_name, "TEST-BANK");
  assert.equal(JSON.parse(request.body).total_amount, undefined);
  assert.equal(result.ok, true);
});

test("template connection sends only the link and returns the sanitized response", async () => {
  let request;
  const result = await requestTemplate("https://docs.google.com/document/d/fixture-template/edit", {
    fetchImpl: async (url, options) => {
      request = { url, options };
      return { ok: true, json: async () => ({ selection_token: "tpl_opaque", fields: [] }) };
    },
  });
  assert.equal(request.url, "http://localhost:8000/api/template/connect");
  assert.equal(request.options.method, "POST");
  assert.deepEqual(JSON.parse(request.options.body), { url: "https://docs.google.com/document/d/fixture-template/edit" });
  assert.equal(result.selection_token, "tpl_opaque");
});

test("template connection shows account authorization and reauthorization action", () => {
  let rendered = "";
  const form = { addEventListener: () => {} };
  const input = { addEventListener: () => {} };
  const root = {
    set innerHTML(value) { rendered = value; },
    querySelector(selector) { return selector === "form" ? form : input; },
  };
  renderTemplateConnection(root, { user: { email: "synthetic@example.test" } });
  assert.match(rendered, /synthetic@example\.test/);
  assert.match(rendered, /Google Drive access is authorized/);
  assert.match(rendered, /Re-authorize Google Drive/);
  assert.match(rendered, /auth\/google/);
});

test("session and logout requests carry browser credentials", async () => {
  let sessionRequest;
  const session = await requestSession({
    fetchImpl: async (_url, options) => { sessionRequest = options; return { ok: true, json: async () => ({ authenticated: true, auth_required: true, user: { email: "synthetic@example.test" } }) }; },
  });
  assert.equal(session.authenticated, true);
  assert.equal(sessionRequest.credentials, "include");
  let logoutRequest;
  assert.equal(await requestLogout({ fetchImpl: async (_url, options) => { logoutRequest = options; return { ok: true }; } }), true);
  assert.equal(logoutRequest.method, "POST");
  assert.equal(logoutRequest.credentials, "include");
});

test("API origin follows the page hostname so auth cookies stay same-site", () => {
  const previousLocation = globalThis.location;
  globalThis.location = { protocol: "http:", hostname: "127.0.0.1" };
  assert.equal(apiOrigin(), "http://127.0.0.1:8000");
  if (previousLocation === undefined) delete globalThis.location;
  else globalThis.location = previousLocation;
});

test("preview and generation requests carry the opaque template selection", async () => {
  let previewHeaders;
  await requestPreview({ currency: "EUR" }, {
    templateToken: "tpl_opaque",
    fetchImpl: async (_url, options) => {
      previewHeaders = options.headers;
      return { ok: true, json: async () => ({}) };
    },
  });
  assert.equal(previewHeaders["X-Template-Selection"], "tpl_opaque");
});

test("template connection prevents duplicate submissions and preserves the link on failure", async () => {
  let resolveConnection;
  let calls = 0;
  let rendered = "";
  const form = { addEventListener: (_type, listener) => { form.submit = listener; } };
  const input = { addEventListener: (_type, listener) => { input.input = listener; } };
  const root = {
    set innerHTML(value) { rendered = value; },
    querySelector(selector) { return selector === "form" ? form : input; },
  };
  renderTemplateConnection(root, {
    connect: () => { calls += 1; return new Promise((resolve) => { resolveConnection = resolve; }); },
  });
  input.input({ target: { value: "https://docs.google.com/document/d/fixture-template/edit" } });
  const event = { preventDefault() {} };
  const first = form.submit(event);
  const second = form.submit(event);
  assert.equal(calls, 1);
  resolveConnection({ ok: false, error: { message: "Access denied." } });
  await first;
  await second;
  assert.match(rendered, /https:\/\/docs\.google\.com\/document\/d\/fixture-template\/edit/);
});

test("generation downloads only a successful PDF with the safe server filename", async () => {
  let clicked = false;
  let appended = false;
  let revoke;
  const response = {
    ok: true,
    headers: { get: (name) => name === "content-type" ? "application/pdf" : 'attachment; filename="invoice-2026-09-01.pdf"' },
    blob: async () => new Blob(["pdf"]),
  };
  const result = await requestGeneration({ bank_name: "TEST-BANK" }, {
    fetchImpl: async () => response,
    urlImpl: { createObjectURL: () => "blob:fixture", revokeObjectURL: (url) => { revoke = url; } },
    setTimeoutImpl: (callback) => { callback(); },
    documentImpl: {
      body: { appendChild: () => { appended = true; } },
      createElement: () => ({ set href(_) {}, set download(_) { clicked = true; }, click() {} }),
    },
  });
  assert.equal(result.filename, "invoice-2026-09-01.pdf");
  assert.equal(clicked, true);
  assert.equal(appended, true);
  assert.equal(revoke, "blob:fixture");
});

test("generation sends exactly one credentialed POST with the selected template", async () => {
  let calls = 0;
  let request;
  const response = {
    ok: true,
    headers: { get: (name) => name === "content-type" ? "application/pdf" : 'attachment; filename="invoice.pdf"' },
    blob: async () => new Blob(["pdf"]),
  };
  await requestGeneration({ currency: "EUR" }, {
    templateToken: "tpl_opaque",
    fetchImpl: async (url, options) => { calls += 1; request = { url, options }; return response; },
    urlImpl: { createObjectURL: () => "blob:fixture", revokeObjectURL: () => {} },
    documentImpl: { createElement: () => ({ click() {}, set href(_) {}, set download(_) {} }) },
  });
  assert.equal(calls, 1);
  assert.equal(request.url, "http://localhost:8000/api/invoices/generate");
  assert.equal(request.options.method, "POST");
  assert.equal(request.options.credentials, "include");
  assert.equal(request.options.headers["X-Template-Selection"], "tpl_opaque");
});

test("non-PDF success responses fail without downloading", async () => {
  await assert.rejects(() => requestGeneration({}, {
    fetchImpl: async () => ({ ok: true, headers: { get: () => "application/json" } }),
  }), /invalid PDF response/);
});

test("generation surfaces the backend's safe provider guidance", async () => {
  await assert.rejects(() => requestGeneration({}, {
    fetchImpl: async () => ({
      ok: false,
      headers: { get: () => "application/json" },
      json: async () => ({ error: { code: "temporary_document_not_found", message: "Try generating again." } }),
    }),
  }), /Try generating again/);
});
