export const appName = "invoice-filler";

export const invoiceFields = [
  { name: "service_start_date", label: "Service start date", type: "date", required: true },
  { name: "service_end_date", label: "Service end date", type: "date", required: false },
  { name: "days_worked", label: "Days worked", type: "number", required: true, step: "0.01", min: "0" },
  { name: "pay_per_day", label: "Pay per day", type: "number", required: true, step: "0.01", min: "0" },
  { name: "currency", label: "Currency", type: "text", required: true, autocomplete: "off" },
  { name: "bank_name", label: "Bank name", type: "text", required: false },
  { name: "account_holder", label: "Account holder", type: "text", required: false },
  { name: "iban_or_account_number", label: "IBAN or account number", type: "text", required: false, autocomplete: "off" },
  { name: "swift_or_bic", label: "SWIFT/BIC", type: "text", required: false, autocomplete: "off" },
];

const initialValues = Object.fromEntries(invoiceFields.map(({ name }) => [name, ""]));

export function createInvoiceFormController({ preview } = {}) {
  if (typeof preview !== "function") throw new TypeError("A preview function is required");
  const state = { values: { ...initialValues }, errors: {}, status: "idle", preview: null };
  const listeners = new Set();
  const getState = () => ({
    values: { ...state.values }, errors: { ...state.errors }, status: state.status,
    preview: state.preview, canGenerate: state.status === "success" && state.preview !== null,
  });
  const notify = () => listeners.forEach((listener) => listener(getState()));

  return {
    getState,
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    setValue(name, value) {
      if (!(name in state.values) || state.status === "pending") return;
      state.values[name] = value;
      state.errors = { ...state.errors, [name]: undefined };
      state.preview = null;
      state.status = "idle";
      notify();
    },
    async submit() {
      if (state.status === "pending") return getState();
      state.status = "pending";
      state.errors = {};
      notify();
      try {
        const result = await preview({ ...state.values });
        if (!result || result.ok !== true) {
          state.errors = Object.fromEntries((result?.error?.fields || []).map((field) => [field.name, field.message]));
          state.preview = null;
          state.status = "error";
        } else {
          state.preview = result;
          state.status = "success";
        }
      } catch {
        state.errors = { form: "Preview is unavailable. Try again." };
        state.preview = null;
        state.status = "error";
      }
      notify();
      return getState();
    },
  };
}

export async function requestTemplate(url, { fetchImpl = globalThis.fetch } = {}) {
  const response = await fetchImpl(`${apiOrigin()}/api/template/connect`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url }),
  });
  const payload = await response.json();
  return response.ok ? { ok: true, ...payload } : { ok: false, error: payload.error };
}

export function renderTemplateConnection(root, { connect = requestTemplate, onConnected } = {}) {
  let url = "";
  let status = "idle";
  let error = "";
  const render = () => {
    const pending = status === "pending";
    root.innerHTML = `<section class="template-connect" aria-labelledby="template-heading"><p class="eyebrow">Start with a template</p><h1 id="template-heading">Where is your template?</h1><p class="template-help">Paste the link to the Google Docs template you want to fill.</p><form><label for="template-url">Google Docs template link</label><input id="template-url" name="template-url" type="url" value="${escapeHtml(url)}" placeholder="https://docs.google.com/document/d/..." autocomplete="off" required ${pending ? "disabled" : ""} ${error ? 'aria-invalid="true" aria-describedby="template-error"' : ""}>${error ? `<p id="template-error" class="error" role="alert">${escapeHtml(error)}</p>` : ""}<button class="button button-primary" type="submit" ${pending ? "disabled" : ""}>${pending ? "Checking template…" : "Load template"}</button></form></section>`;
    const form = root.querySelector("form");
    const input = root.querySelector("#template-url");
    input?.addEventListener("input", (event) => { url = event.target.value; error = ""; });
    form?.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (status === "pending" || !url.trim()) return;
      status = "pending"; error = ""; render();
      try {
        const result = await connect(url);
        if (!result || result.ok === false) throw new Error(result?.error?.message || "The template could not be loaded.");
        onConnected?.(result);
      } catch (connectionError) {
        status = "error"; error = connectionError.message || "The template could not be loaded. Try again."; render();
      }
    });
  };
  render();
  return { getValue: () => url, render };
}

export async function requestPreview(values, { fetchImpl = globalThis.fetch, templateToken } = {}) {
  const response = await fetchImpl(`${apiOrigin()}/api/invoices/preview`, {
    method: "POST", headers: { "Content-Type": "application/json", ...(templateToken ? { "X-Template-Selection": templateToken } : {}) }, body: JSON.stringify(values),
  });
  const payload = await response.json();
  return response.ok ? { ok: true, ...payload } : { ok: false, error: payload.error };
}

export function apiOrigin() {
  return globalThis.INVOICE_API_ORIGIN || "http://localhost:8000";
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]));
}

function fieldMarkup(field, state) {
  const error = state.errors[field.name];
  const attributes = [
    `id="${field.name}"`, `name="${field.name}"`, `type="${field.type}"`,
    `value="${escapeHtml(state.values[field.name])}"`, field.required ? "required" : "",
    field.step ? `step="${field.step}"` : "", field.min ? `min="${field.min}"` : "",
    field.autocomplete ? `autocomplete="${field.autocomplete}"` : "",
    error ? 'aria-invalid="true"' : "", error ? `aria-describedby="${field.name}-error"` : "",
  ].filter(Boolean).join(" ");
  return `<div class="field"><label for="${field.name}">${field.label}${field.required ? " *" : ""}</label><input ${attributes}>${error ? `<p id="${field.name}-error" class="error" role="alert">${escapeHtml(error)}</p>` : ""}</div>`;
}

export function renderInvoiceForm(root, { preview = requestPreview } = {}) {
  const controller = createInvoiceFormController({ preview });
  function render(state) {
    const pending = state.status === "pending";
    const formError = state.errors.form || "";
    const total = state.preview?.calculation?.total_amount;
    root.innerHTML = `<form aria-labelledby="invoice-heading"><h1 id="invoice-heading">Create invoice</h1><p>Enter your invoice details to review the calculated total.</p><fieldset><legend>Invoice details</legend>${invoiceFields.map((field) => fieldMarkup(field, state)).join("")}</fieldset>${formError ? `<p class="error" role="alert">${escapeHtml(formError)}</p>` : ""}${total ? `<output aria-live="polite">Total: ${escapeHtml(total)} ${escapeHtml(state.preview.calculation.currency)}</output>` : ""}<div class="actions"><button type="submit" ${pending ? "disabled" : ""}>${pending ? "Checking…" : "Preview invoice"}</button><button type="button" disabled aria-disabled="true">Generate PDF</button></div></form>`;
    const form = root.querySelector("form");
    form.addEventListener("submit", (event) => { event.preventDefault(); controller.submit(); });
    invoiceFields.forEach(({ name }) => form.elements[name].addEventListener("input", (event) => controller.setValue(name, event.target.value)));
  }
  controller.subscribe(render);
  render(controller.getState());
  return controller;
}
