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

export async function requestPreview(values, { fetchImpl = globalThis.fetch } = {}) {
  const response = await fetchImpl("/api/invoices/preview", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(values),
  });
  const payload = await response.json();
  return response.ok ? { ok: true, ...payload } : { ok: false, error: payload.error };
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
