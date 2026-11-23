// API client. Every request carries the token from the active sign-in
// provider (see auth.js); business code never deals with tokens.

// The API lives on the server that served this page. The exceptions are
// pages opened from disk (file://) and VS Code Live Server (port 5500),
// which reach a locally running API instead.
const API_BASE = window.location.protocol.startsWith("http") && window.location.port !== "5500"
    ? ""
    : "http://127.0.0.1:8000";

let tokenProvider = async () => null;
let onUnauthorized = () => {};

export function configureApi({ getToken, unauthorized }) {
    tokenProvider = getToken;
    onUnauthorized = unauthorized || onUnauthorized;
}

export class ApiError extends Error {
    constructor(message, status) {
        super(message);
        this.status = status;
    }
}

async function send(path, options, forceRefresh = false) {
    const token = await tokenProvider({ forceRefresh });
    const headers = new Headers(options.headers || {});

    if (token) headers.set("Authorization", `Bearer ${token}`);

    return fetch(`${API_BASE}${path}`, { ...options, headers });
}

export async function request(path, options = {}) {
    let response = await send(path, options);

    // One retry with a fresh token, in case it expired.
    if (response.status === 401) {
        response = await send(path, options, true);
    }

    if (response.status === 401) {
        onUnauthorized();
    }

    if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        const detail = Array.isArray(body.detail)
            ? body.detail.map(item => item.msg).join(" ")
            : body.detail;
        throw new ApiError(detail || `Request failed (${response.status}).`, response.status);
    }

    const type = response.headers.get("content-type") || "";
    return type.includes("application/json") ? response.json() : response;
}

export function get(path) {
    return request(path);
}

export function sendJSON(method, path, body) {
    return request(path, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body ?? {})
    });
}

export function postForm(path, formData) {
    return request(path, { method: "POST", body: formData });
}

/** Unauthenticated calls (health, sign-in config). */
export async function publicRequest(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, options);
    const body = await response.json().catch(() => ({}));

    if (!response.ok) {
        throw new ApiError(body.detail || `Request failed (${response.status}).`, response.status);
    }

    return body;
}

/** Download an authenticated file (such as a resume) and save it. */
export async function download(path, fallbackName) {
    const response = await request(path);
    const blob = await response.blob();

    const disposition = response.headers.get("content-disposition") || "";
    const match = disposition.match(/filename="?([^";]+)"?/i);

    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = match ? match[1] : fallbackName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}
