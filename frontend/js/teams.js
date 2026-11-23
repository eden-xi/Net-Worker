// Microsoft Teams integration. The Teams library (a pinned copy in
// /vendor) is loaded only when the page runs inside Teams.

let teamsSdk = null;
let teamsContext = null;

export function looksLikeTeams() {
    const params = new URLSearchParams(window.location.search);
    return params.get("inTeams") === "1" || window.self !== window.top;
}

function loadScript(src) {
    return new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = src;
        script.onload = resolve;
        script.onerror = () => reject(new Error(`Could not load ${src}`));
        document.head.appendChild(script);
    });
}

function withTimeout(promise, ms) {
    return Promise.race([
        promise,
        new Promise((_, reject) => setTimeout(() => reject(new Error("Timed out")), ms))
    ]);
}

/**
 * Initialize the Teams SDK. Resolves to the Teams context, or null when the
 * page is not actually hosted by Teams (for example, framed elsewhere).
 */
export async function initTeams() {
    if (!looksLikeTeams()) return null;

    try {
        await loadScript("vendor/MicrosoftTeams.min.js");
        teamsSdk = window.microsoftTeams;
        await withTimeout(teamsSdk.app.initialize(), 5000);
        teamsContext = await teamsSdk.app.getContext();
    } catch (error) {
        console.warn("Not running inside Microsoft Teams.", error);
        teamsSdk = null;
        return null;
    }

    applyTeamsTheme(teamsContext.app?.theme);
    teamsSdk.app.registerOnThemeChangeHandler(applyTeamsTheme);
    teamsSdk.app.notifySuccess();

    return teamsContext;
}

export function isInTeams() {
    return teamsSdk !== null;
}

export function applyTeamsTheme(theme) {
    const map = { default: "light", dark: "dark", contrast: "contrast" };
    document.documentElement.dataset.theme = map[theme] || "light";
}

/** Teams SSO: an Entra ID token for this app's API (see teams/README.md). */
export async function getTeamsToken() {
    if (!teamsSdk) throw new Error("Not running inside Microsoft Teams.");
    return teamsSdk.authentication.getAuthToken();
}

/** Teams deep links can carry a route in the page or sub-page ID. */
export function teamsStartRoute() {
    const id = teamsContext?.page?.subPageId || "";
    return /^[a-z-]+$/.test(id) ? id : "";
}
