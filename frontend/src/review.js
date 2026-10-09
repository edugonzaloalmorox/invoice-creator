import { apiOrigin } from "./app.js";

/* The invoice form owns field review; this module only owns PDF download. */

export async function requestGeneration(values, { fetchImpl = globalThis.fetch, urlImpl = globalThis.URL, documentImpl = globalThis.document, setTimeoutImpl = globalThis.setTimeout, templateToken } = {}) {
  const response = await fetchImpl(`${apiOrigin()}/api/invoices/generate`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json", ...(templateToken ? { "X-Template-Selection": templateToken } : {}) }, body: JSON.stringify(values),
  });
  const contentType = (response.headers?.get?.("content-type") || "").split(";", 1)[0].toLowerCase();
  if (!response.ok || contentType !== "application/pdf") {
    if (!response.ok) {
      let payload = null;
      try {
        payload = await response.json();
      } catch {
        payload = null;
      }
      throw new Error(payload?.error?.message || "PDF generation failed. Try again.");
    }
    throw new Error(response.ok ? "The server returned an invalid PDF response." : "PDF generation failed. Try again.");
  }
  const blob = await response.blob();
  const disposition = response.headers?.get?.("content-disposition") || "";
  const match = disposition.match(/filename="([a-zA-Z0-9._-]+\.pdf)"/);
  const filename = match?.[1] || "invoice.pdf";
  const url = urlImpl.createObjectURL(blob);
  const link = documentImpl.createElement("a");
  link.href = url;
  link.download = filename;
  link.textContent = "Download PDF";
  link.className = "download-link";
  documentImpl.body?.appendChild(link);
  try {
    link.click();
  } finally {
    // Keep the link available for browsers that block downloads started after
    // an awaited fetch. The user can click it normally in that case.
    const cleanupTimer = setTimeoutImpl(() => urlImpl.revokeObjectURL(url), 60_000);
    cleanupTimer?.unref?.();
  }
  return { filename };
}
