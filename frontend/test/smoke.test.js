import test from "node:test";
import assert from "node:assert/strict";
import { appName, createInvoiceFormController, invoiceFields, requestPreview } from "../src/app.js";

test("frontend scaffold is importable", () => {
  assert.equal(appName, "invoice-filler");
});

test("invoice form exposes all fields and keeps generation locked before preview", () => {
  const controller = createInvoiceFormController({ preview: async () => ({ ok: true }) });
  assert.equal(invoiceFields.length, 9);
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
    fetchImpl: async (_url, options) => {
      request = options;
      return { ok: true, json: async () => ({ calculation: { total_amount: "1.00" } }) };
    },
  });
  assert.equal(request.method, "POST");
  assert.equal(JSON.parse(request.body).bank_name, "TEST-BANK");
  assert.equal(JSON.parse(request.body).total_amount, undefined);
  assert.equal(result.ok, true);
});
