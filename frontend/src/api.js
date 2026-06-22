// All requests go through /api, which nginx (prod) or Vite (dev) proxies to
// the FastAPI backend. The JWT lives in memory only (cleared on reload/logout).

let token = null;

export function setToken(t) {
  token = t;
}
export function getToken() {
  return token;
}

async function request(path, { method = "GET", body, form, isFile } = {}) {
  const headers = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let payload;
  if (form) {
    payload = form; // URLSearchParams or FormData; let browser set content-type
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  const res = await fetch(`/api${path}`, { method, headers, body: payload });

  if (res.status === 401) {
    setToken(null);
    throw new ApiError("Session expired. Please sign in again.", 401);
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (data.detail) detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {}
    throw new ApiError(detail, res.status);
  }
  if (res.status === 204) return null;
  if (isFile) return res.blob();
  return res.json();
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

// Full-page navigation (not fetch) — the backend 302-redirects to the IdP.
export const SSO_LOGIN_URL = "/api/auth/sso/login";

// After SSO the backend redirects back with the result in the URL fragment
// (#sso_token=... or #sso_error=...). Read it once on load, then scrub the URL
// so the token isn't left in the address bar / history.
export function consumeSsoRedirect() {
  const hash = window.location.hash || "";
  const tok = hash.match(/sso_token=([^&]+)/);
  const err = hash.match(/sso_error=([^&]+)/);
  if (tok || err) {
    history.replaceState(null, "", window.location.pathname + window.location.search);
  }
  if (tok) {
    setToken(decodeURIComponent(tok[1]));
    return { token: true };
  }
  if (err) return { error: decodeURIComponent(err[1]) };
  return null;
}

export const api = {
  getAuthConfig: () => request("/auth/config"),
  me: () => request("/auth/me"),
  // SSO group -> role mappings (admin-only)
  listIdpRoleMaps: () => request("/idp-role-maps"),
  createIdpRoleMap: (body) => request("/idp-role-maps", { method: "POST", body }),
  deleteIdpRoleMap: (id) => request(`/idp-role-maps/${id}`, { method: "DELETE" }),
  async login(email, password) {
    const form = new URLSearchParams();
    form.set("username", email);
    form.set("password", password);
    const data = await request("/auth/login", { method: "POST", form });
    setToken(data.access_token);
    return data;
  },
  // Tests
  listTests: () => request("/tests"),
  getTest: (id) => request(`/tests/${id}`),
  createTest: (body) => request("/tests", { method: "POST", body }),
  updateTest: (id, body) => request(`/tests/${id}`, { method: "PATCH", body }),
  // Findings
  listFindings: (testId) =>
    request(`/findings${testId ? `?test_id=${testId}` : ""}`),
  updateFinding: (id, body) => request(`/findings/${id}`, { method: "PATCH", body }),
  createFinding: (body) => request("/findings", { method: "POST", body }),
  // Bookings (BAU schedule)
  listBookings: () => request("/bookings"),
  createBooking: (body) => request("/bookings", { method: "POST", body }),
  updateBooking: (id, body) => request(`/bookings/${id}`, { method: "PATCH", body }),
  deleteBooking: (id) => request(`/bookings/${id}`, { method: "DELETE" }),
  reorderBookings: (orderedIds) =>
    request("/bookings/reorder", { method: "POST", body: { ordered_ids: orderedIds } }),
  // Scopes
  listScopes: () => request("/scopes"),
  createScope: (body) => request("/scopes", { method: "POST", body }),
  updateScope: (id, body) => request(`/scopes/${id}`, { method: "PATCH", body }),
  deleteScope: (id) => request(`/scopes/${id}`, { method: "DELETE" }),
  listScopeAttachments: (id) => request(`/scopes/${id}/attachments`),
  uploadScopeAttachment: (id, file) => {
    const fd = new FormData();
    fd.append("file", file);
    return request(`/scopes/${id}/attachments`, { method: "POST", form: fd });
  },
  deleteScopeAttachment: (attId) =>
    request(`/scope-attachments/${attId}`, { method: "DELETE" }),
  async downloadScopeAttachment(attId, filename) {
    const blob = await request(`/scope-attachments/${attId}/download`, { isFile: true });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename || "attachment";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
  // Teams / users
  listTeams: () => request("/teams"),
  listUsers: () => request("/users"),
  // Attachments
  listFindingAttachments: (id) => request(`/findings/${id}/attachments`),
  uploadFindingAttachment: (id, file) => {
    const fd = new FormData();
    fd.append("file", file);
    return request(`/findings/${id}/attachments`, { method: "POST", form: fd });
  },
  deleteFindingAttachment: (attId) =>
    request(`/finding-attachments/${attId}`, { method: "DELETE" }),
  // Imports
  importFields: () => request("/imports/fields"),
  importPreview: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return request("/imports/preview", { method: "POST", form: fd });
  },
  importCommit: (file, mapping, mode) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("mapping", JSON.stringify(mapping));
    fd.append("mode", mode);
    return request("/imports/commit", { method: "POST", form: fd });
  },
  async downloadFindingAttachment(attId, filename) {
    const blob = await request(`/finding-attachments/${attId}/download`, {
      isFile: true,
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename || "attachment";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
};
