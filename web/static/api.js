// Thin fetch wrapper. All URLs are relative so the app works behind any prefix.
export class ApiError extends Error {
  constructor(status, type, message) { super(message); this.status = status; this.type = type; }
}

export async function api(path, options) {
  const response = await fetch(path, options);
  let body = {};
  try { body = await response.json(); } catch { /* not JSON */ }
  if (!response.ok) {
    const e = body.error || {};
    throw new ApiError(response.status, e.type || "error", e.message || `request failed (${response.status})`);
  }
  return body;
}

export const postJson = (path, data) => api(path, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
});
