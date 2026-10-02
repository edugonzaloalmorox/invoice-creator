import { renderInvoiceForm, renderTemplateConnection, requestPreview, requestTemplate } from "./app.js";
import { requestGeneration } from "./review.js";

const root = document.querySelector("#app");

function renderApplicationError(message) {
  root.innerHTML = `<section class="service-error" aria-labelledby="service-error-title"><p class="eyebrow">Connection problem</p><h2 id="service-error-title">The invoice service is unavailable</h2><p>${message}</p><button class="button button-secondary" type="button" id="retry">Try again</button></section>`;
  root.querySelector("#retry").addEventListener("click", start);
}

async function start() {
  root.innerHTML = '<p class="loading" role="status">Connecting to the invoice service…</p>';
  try {
    const response = await fetch("http://localhost:8000/api/health");
    if (!response.ok) throw new Error("Health check failed");
    renderTemplateConnection(root, {
      connect: requestTemplate,
      onConnected: ({ selection_token: templateToken }) => {
        renderInvoiceForm(root, { preview: (values) => requestPreview(values, { templateToken }) });
        wireGeneration(templateToken);
      },
    });
  } catch {
    renderApplicationError("Start the backend with <code>uv run python -m backend.run</code>, then try again.");
  }
}

function wireGeneration(templateToken) {
  let message = "";
  const update = () => {
    const form = root.querySelector("form");
    if (!form) return;
    let button = form.querySelector(".generate-button") || form.querySelector(".actions button[type=button]");
    if (!button) {
      button = document.createElement("button");
      button.type = "button";
      button.textContent = "Generate PDF";
      form.querySelector(".actions")?.append(button);
    }
    button.classList.add("generate-button", "button", "button-primary");
    if (!button.dataset.bound) {
      button.addEventListener("click", generate);
      button.dataset.bound = "true";
    }
    const hasPreview = Boolean(form.querySelector("output"));
    button.disabled = !hasPreview;
    button.setAttribute("aria-disabled", String(button.disabled));
    let output = form.querySelector(".form-message");
    if (!output) {
      output = document.createElement("p");
      output.className = "form-message";
      output.setAttribute("role", "status");
      form.append(output);
    }
    output.textContent = message;
  };
  async function generate(event) {
    const button = event.currentTarget;
    const form = button.form;
    if (button.disabled) return;
    button.disabled = true;
    message = "Generating your PDF…";
    update();
    const values = Object.fromEntries([...new FormData(form).entries()]);
    try {
      const result = await requestGeneration(values, { templateToken });
      message = `${result.filename} downloaded.`;
    } catch (error) {
      message = error.message;
    }
    update();
  }
  const observer = new MutationObserver(update);
  observer.observe(root, { childList: true, subtree: true });
  update();
}

start();
