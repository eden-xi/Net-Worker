// ==========================================
// API CLIENT: the one place the page talks to the server.
//
// Every request goes through apiFetch(), so error handling is written once:
//   - the login cookie is sent automatically (page and API share one address)
//   - 401 means the session ended: back to the login wall (showLoginWall is in app.js)
//   - any other error throws an Error with the server's message ("detail")
// ==========================================

async function apiFetch(url, options = {}) {
    const response = await fetch(url, { credentials: "same-origin", ...options });
    let body = null;

    try {
        body = await response.json();
    } catch (error) {
        body = null;                     // e.g. an empty response
    }

    if (response.status === 401 && !url.startsWith("/api/auth/")) {
        showLoginWall("Your session ended. Please sign in again.");
    }

    if (!response.ok) {
        throw new Error((body && body.detail && typeof body.detail === "string")
            ? body.detail
            : `Request failed (${response.status}).`);
    }

    return body;
}

// Send JSON (create a listing, change a status, save skills, sign in).
function sendJSON(url, method, data) {
    return apiFetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data)
    });
}

// Send a form with files (apply with a resume, upload a CSV).
function sendForm(url, formData) {
    return apiFetch(url, { method: "POST", body: formData });
}
