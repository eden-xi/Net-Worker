// ==========================================
// UI HELPERS: small functions that return HTML or show feedback.
// Used by every screen, for both roles.
// ==========================================

// ---------- text ----------

function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, character => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
    })[character]);
}

function splitSkills(value) {
    return String(value || "").split(/[,;|\n]/).map(skill => skill.trim()).filter(Boolean);
}

// The database stores UTC times without a "Z". Add it, so the browser shows local time correctly.
function toDate(value) {
    const text = String(value || "");
    const hasZone = /(Z|[+-]\d\d:?\d\d)$/.test(text);
    return new Date(hasZone ? text : text.replace(" ", "T") + "Z");
}

function formatDate(value) {
    return value ? toDate(value).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "";
}

function timeAgo(value) {
    const seconds = Math.max(0, (Date.now() - toDate(value).getTime()) / 1000);
    if (seconds < 45) return "just now";
    if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
    if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
    return formatDate(value);
}

function initials(name) {
    return String(name || "?").split(/\s+/).map(part => part[0]).join("").slice(0, 2).toUpperCase();
}

// ---------- badges: one color per status, always with the word ----------

const STATUS_STYLE = {
    "Open": "ok", "Closed": "neutral", "Filled": "info",
    "Submitted": "neutral", "Under Review": "warn", "Accepted": "ok", "Rejected": "bad"
};

function badge(status) {
    return `<span class="badge badge-${STATUS_STYLE[status] || "neutral"}">${escapeHTML(status)}</span>`;
}

function matchPill(score) {
    const level = score >= 75 ? "high" : score >= 40 ? "mid" : "low";
    return `<span class="match match-${level}">${Number(score)}% match</span>`;
}

// ---------- loading, empty, feedback ----------

function skeletonCards(count = 6) {
    const card = `
        <article class="listing-card skeleton" aria-hidden="true">
            <div class="skeleton-line short"></div>
            <div class="skeleton-line wide"></div>
            <div class="skeleton-line mid"></div>
            <div class="skeleton-line"></div>
        </article>`;
    return card.repeat(count);
}

function emptyState(title, text, actionHTML = "") {
    return `<div class="empty"><h3>${escapeHTML(title)}</h3><p class="muted">${escapeHTML(text)}</p>${actionHTML}</div>`;
}

function toast(message, kind = "ok") {
    const item = document.createElement("div");
    item.className = `toast ${kind}`;
    item.textContent = message;
    document.getElementById("toasts").appendChild(item);
    setTimeout(() => item.remove(), 4000);
}

function setStatus(element, message, isError = false) {
    if (!element) return;
    element.textContent = message;
    element.className = isError ? "status-text error" : "status-text success";
}

// ---------- drawer ----------

function openModal(html) {
    document.getElementById("modal-body").innerHTML = html;
    document.getElementById("modal").classList.remove("hidden");
}

function closeModal() {
    document.getElementById("modal").classList.add("hidden");
    document.getElementById("modal-body").innerHTML = "";
}

// ---------- polling: one timer at a time; the router stops it on every page change ----------

let pollTimer = null;

// owner: the page's box. If it is no longer on screen (you left the page), polling stops itself.
function startPolling(task, milliseconds, owner) {
    stopPolling();
    if (owner && !owner.isConnected) return;
    pollTimer = setInterval(() => {
        if (owner && !owner.isConnected) return stopPolling();
        if (!document.hidden) task();          // don't poll from a background tab
    }, milliseconds);
}

function stopPolling() {
    clearInterval(pollTimer);
    pollTimer = null;
}

// ---------- icons (simple line icons, inline so there is nothing to download) ----------

const ICON_PATHS = {
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    briefcase: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"/>',
    inbox: '<path d="M3 13h5l2 3h4l2-3h5"/><path d="M5 5h14l2 8v6H3v-6z"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
    activity: '<path d="M3 12h4l3 8 4-16 3 8h4"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    review: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>'
};

function icon(name, size = 18) {
    return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON_PATHS[name] || ""}</svg>`;
}
