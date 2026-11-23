// Sign-in providers. The rest of the app calls getToken() and never knows
// which provider is active:
//   dev    a test user picked on the sign-in screen (local development)
//   entra  Microsoft Entra ID through Teams SSO
// Tokens live in memory only, never in browser storage.

import { publicRequest } from "./api.js";
import { getTeamsToken, isInTeams } from "./teams.js";

const LAST_DEV_USER_KEY = "projecthub.lastDevUser";

let mode = "dev";
let devToken = null;
let cachedTeamsToken = null;

function tokenExpiry(token) {
    try {
        const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
        return (payload.exp || 0) * 1000;
    } catch {
        return 0;
    }
}

export function authMode() {
    return mode;
}

export function setAuthMode(value) {
    mode = value;
}

export async function getToken({ forceRefresh = false } = {}) {
    if (mode === "dev") return devToken;

    if (!isInTeams()) return null;

    const fresh = cachedTeamsToken && tokenExpiry(cachedTeamsToken) - Date.now() > 5 * 60 * 1000;
    if (!fresh || forceRefresh) {
        cachedTeamsToken = await getTeamsToken();
    }
    return cachedTeamsToken;
}

export function isSignedIn() {
    return mode === "dev" ? Boolean(devToken) : isInTeams();
}

export async function devSignIn(email, displayName = "") {
    const result = await publicRequest("/auth/dev-login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, display_name: displayName })
    });

    devToken = result.token;

    try {
        localStorage.setItem(LAST_DEV_USER_KEY, email);
    } catch {
        // Storage may be blocked; this only pre-selects the user next time.
    }

    return result.user;
}

export function lastDevUser() {
    try {
        return localStorage.getItem(LAST_DEV_USER_KEY) || "";
    } catch {
        return "";
    }
}

export function signOut() {
    devToken = null;
    cachedTeamsToken = null;
}
