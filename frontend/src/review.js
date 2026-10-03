const BLOCKING_WARNINGS = new Set(["missing_field", "ambiguous_field", "low_confidence"]);

function apiOrigin() {
  return globalThis.INVOICE_API_ORIGIN || "http://localhost:8000";
}

export function createFieldReviewController({ loadFields, preview }) {
  const state = { status: "idle", fields: [], edits: {}, error: "", preview: null, download: null };
  const listeners = new Set();
  const snapshot = () => {
    const fields = state.fields.map((field) => ({ ...field, value: state.edits[field.name] ?? field.value, edited: field.name in state.edits }));
    const unresolved = fields.some((field) => field.required && (
      !field.value || field.warnings?.some((warning) => BLOCKING_WARNINGS.has(warning))
    ));
    return {
      status: state.status, fields, error: state.error, preview: state.preview, download: state.download,
      canConfirm: state.status === "ready" && !unresolved && state.preview !== null,
      canGenerate: state.status === "ready" && !unresolved && state.preview !== null,
      unresolved,
    };
  };
  const notify = () => listeners.forEach((listener) => listener(snapshot()));
  const load = async () => {
    state.status = "loading"; state.error = ""; notify();
    try {
      const result = await loadFields();
      if (!result || result.ok === false) throw new Error(result?.error?.message || "Fields are unavailable.");
      state.fields = result.fields || [];
      state.status = state.fields.length ? "ready" : "empty";
    } catch (error) {
      state.status = "error"; state.error = error.message || "Fields are unavailable.";
    }
    notify();
    return snapshot();
  };
  return {
    getState: snapshot,
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    load,
    retry: load,
    edit(name, value) {
      if (!state.fields.some((field) => field.name === name)) return;
      state.edits[name] = value;
      const field = state.fields.find((candidate) => candidate.name === name);
      field.warnings = (field.warnings || []).filter((warning) => warning !== "missing_field");
      state.preview = null;
      notify();
    },
    async confirm() {
      const current = snapshot();
      if (!current.fields.length || current.unresolved || typeof preview !== "function") return current;
      state.status = "previewing"; notify();
      try {
        const result = await preview(Object.fromEntries(current.fields.map((field) => [field.name, field.value])));
        if (!result || result.ok === false) {
          state.error = result?.error?.message || "Review could not be validated.";
          state.status = "ready";
        } else {
          state.preview = result;
          state.status = "ready";
        }
      } catch {
        state.error = "Review could not be validated. Try again.";
        state.status = "ready";
      }
      notify();
      return snapshot();
    },
    async generate(generatePdf) {
      const current = snapshot();
      if (!current.canGenerate || typeof generatePdf !== "function" || state.status === "generating") return current;
      state.status = "generating"; state.error = ""; notify();
      try {
        state.download = await generatePdf(Object.fromEntries(current.fields.map((field) => [field.name, field.value])));
      } catch (error) {
        state.download = null;
        state.error = error.message || "PDF generation failed. Try again.";
      }
      state.status = "ready";
      notify();
      return snapshot();
    },
  };
}

export async function requestGeneration(values, { fetchImpl = globalThis.fetch, urlImpl = globalThis.URL, documentImpl = globalThis.document, templateToken } = {}) {
  const response = await fetchImpl(`${apiOrigin()}/api/invoices/generate`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json", ...(templateToken ? { "X-Template-Selection": templateToken } : {}) }, body: JSON.stringify(values),
  });
  const contentType = (response.headers?.get?.("content-type") || "").split(";", 1)[0].toLowerCase();
  if (!response.ok || contentType !== "application/pdf") {
    throw new Error(response.ok ? "The server returned an invalid PDF response." : "PDF generation failed. Try again.");
  }
  const blob = await response.blob();
  const disposition = response.headers?.get?.("content-disposition") || "";
  const match = disposition.match(/filename="([a-zA-Z0-9._-]+\.pdf)"/);
  const filename = match?.[1] || "invoice.pdf";
  const url = urlImpl.createObjectURL(blob);
  const link = documentImpl.createElement("a");
  link.href = url; link.download = filename; link.click();
  urlImpl.revokeObjectURL(url);
  return { filename };
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]));
}

export function renderFieldReview(root, options) {
  const controller = createFieldReviewController(options);
  const render = (state) => {
    if (state.status === "loading") { root.innerHTML = '<p role="status">Loading detected fields…</p>'; return; }
    if (state.status === "empty") { root.innerHTML = '<p role="status">No fields were detected.</p>'; return; }
    if (state.status === "error") { root.innerHTML = `<p class="error" role="alert">${escapeHtml(state.error)}</p><button type="button" data-action="retry">Retry</button>`; return; }
    const rows = state.fields.map((field) => {
      const warning = field.warnings?.length ? `<p class="warning" role="alert">${field.warnings.map(escapeHtml).join(", ")}</p>` : "";
      const source = `${field.source?.section || "unknown"} / ${field.source?.location || "unknown"}`;
      const kind = field.calculated ? "calculated" : (field.edited ? "edited" : "detected");
      return `<article class="field-card ${kind}"><label for="review-${field.name}">${escapeHtml(field.label)} (${escapeHtml(field.type)})</label><input id="review-${field.name}" data-field="${field.name}" value="${escapeHtml(field.value)}" ${field.required ? "required" : ""}><p>${field.required ? "Required" : "Optional"} · ${escapeHtml(source)} · ${kind}</p>${warning}</article>`;
    }).join("");
    root.innerHTML = `<section aria-labelledby="review-heading"><h2 id="review-heading">Review detected fields</h2>${state.error ? `<p class="error" role="alert">${escapeHtml(state.error)}</p>` : ""}${rows}<button type="button" data-action="confirm" ${state.canConfirm ? "" : "disabled"}>Confirm values</button><button type="button" data-action="generate" ${state.canGenerate ? "" : "disabled"}>${state.status === "generating" ? "Generating…" : "Generate PDF"}</button></section>`;
    root.querySelectorAll("[data-field]").forEach((input) => input.addEventListener("input", (event) => controller.edit(event.target.dataset.field, event.target.value)));
    root.querySelector("[data-action=confirm]")?.addEventListener("click", () => controller.confirm());
    root.querySelector("[data-action=generate]")?.addEventListener("click", () => controller.generate(options.generate));
  };
  controller.subscribe(render);
  render(controller.getState());
  return controller;
}
