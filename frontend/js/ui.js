// Shared rendering helpers. Everything inserted as HTML goes through
// escapeHTML; nothing uses alert() or confirm(), which Teams can suppress.

import { icon } from "./icons.js";

export function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, character => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
    })[character]);
}

export function $(selector, root = document) {
    return root.querySelector(selector);
}

export function splitSkills(value) {
    const seen = new Set();

    return String(value || "")
        .split(/[,;|\n]/)
        .map(skill => skill.trim())
        .filter(skill => {
            const key = skill.toLowerCase();
            if (!skill || seen.has(key)) return false;
            seen.add(key);
            return true;
        });
}

export function setMessage(element, text, kind = "success") {
    if (typeof element === "string") element = document.getElementById(element);
    if (!element) return;

    element.textContent = text || "";
    element.classList.toggle("success", Boolean(text) && kind === "success");
    element.classList.toggle("error", Boolean(text) && kind === "error");
}

export function toast(text, kind = "success") {
    const container = document.getElementById("toasts");
    const item = document.createElement("div");

    item.className = `toast ${kind === "error" ? "error" : ""}`;
    item.setAttribute("role", kind === "error" ? "alert" : "status");
    item.innerHTML = `${icon(kind === "error" ? "x" : "check")}<span></span>
        <button type="button" aria-label="Dismiss">&times;</button>`;
    item.querySelector("span").textContent = text;
    item.querySelector("button").addEventListener("click", () => item.remove());
    container.appendChild(item);

    setTimeout(() => item.remove(), kind === "error" ? 7000 : 4000);
}

export function formatDate(value, options = { month: "short", day: "numeric", year: "numeric" }) {
    if (!value) return "";
    const text = String(value);
    // SQLite timestamps are UTC without a zone marker; plain dates are local.
    const date = /^\d{4}-\d{2}-\d{2}$/.test(text)
        ? new Date(`${text}T00:00:00`)
        : new Date(text.replace(" ", "T") + (/[zZ]|[+-]\d\d:?\d\d$/.test(text) ? "" : "Z"));
    return Number.isNaN(date.getTime()) ? text : date.toLocaleDateString(undefined, options);
}

const STATUS_PILLS = {
    open: "success",
    accepted: "success",
    submitted: "",
    "under review": "warning",
    "on hold": "warning",
    rejected: "danger",
    filled: "neutral",
    closed: "neutral",
};

export function statusPill(status) {
    const kind = STATUS_PILLS[String(status || "").trim().toLowerCase()] ?? "neutral";
    return `<span class="pill ${kind}">${escapeHTML(status || "")}</span>`;
}

export function chips(skills, kind = "", limit = Infinity) {
    const list = skills || [];
    const shown = list.slice(0, limit)
        .map(skill => `<span class="chip ${kind}">${escapeHTML(skill)}</span>`)
        .join("");
    const extra = list.length > limit ? `<span class="chip more">+${list.length - limit} more</span>` : "";
    return shown + extra;
}

export function monogram(text) {
    const words = String(text || "?").split(/[\s\-–—]+/).filter(word => /^[A-Za-z0-9]/.test(word));
    const letters = words.length > 1 ? words[0][0] + words[1][0] : (words[0] || "?").slice(0, 2);
    return `<span class="monogram" aria-hidden="true">${escapeHTML(letters.toUpperCase())}</span>`;
}

export function experienceNote(experience) {
    if (!experience || experience.fit === "unknown") return "";

    const years = `about ${Number(experience.years)} yrs on your resume`;
    const needed = `${Number(experience.required_years)}+ yrs expected`;

    return experience.fit === "below"
        ? `<p class="experience-note below">${icon("layers")}${needed}, ${years} (-${Number(experience.penalty)} pts)</p>`
        : `<p class="experience-note">${icon("check")}${needed}, ${years}</p>`;
}

export function matchPill(match) {
    if (!match) return "";
    const score = Number(match.score) || 0;
    const kind = score >= 75 ? "strong" : score >= 40 ? "" : "neutral";
    return `<span class="pill ${kind}" title="Skill match">${score}% match</span>`;
}

export function matchBlock(match, { legend = true } = {}) {
    if (!match) return "";

    const score = Math.max(0, Math.min(100, Number(match.score) || 0));
    const matched = (match.matched_required || []).length + (match.matched_nice_to_have || []).length;

    return `
        <div class="match">
            <progress max="100" value="${score}" aria-label="Match ${score}%"></progress>
            <strong>${score}%</strong>
        </div>
        <div class="chips">
            ${chips(match.matched_required, "matched")}
            ${chips(match.matched_nice_to_have, "bonus")}
            ${chips(match.missing_required, "missing")}
        </div>
        ${legend && (matched || (match.missing_required || []).length) ? `
            <p class="match-legend">
                <span>Green: you have it</span><span>Purple: bonus skill</span><span>Dashed: missing</span>
            </p>` : ""}
        ${experienceNote(match.experience)}
    `;
}

export function emptyState(iconName, title, text, action = "") {
    return `
        <div class="empty-state">
            <span class="empty-icon">${icon(iconName)}</span>
            <h3>${escapeHTML(title)}</h3>
            <p>${text}</p>
            ${action}
        </div>`;
}

export function skeletons(count = 6, kind = "") {
    return Array.from({ length: count }, () => `<div class="skeleton ${kind}" aria-hidden="true"></div>`).join("");
}

/**
 * A two-step button for destructive actions: the first click asks
 * "Confirm?", a second click within a few seconds runs the action.
 */
export function confirmClick(button, confirmLabel, action) {
    if (button.classList.contains("confirming")) {
        button.classList.remove("confirming");
        clearTimeout(button.confirmTimer);
        action();
        return;
    }

    const original = button.innerHTML;
    button.classList.add("confirming");
    button.textContent = confirmLabel;
    button.confirmTimer = setTimeout(() => {
        button.classList.remove("confirming");
        button.innerHTML = original;
    }, 4000);
}

// ==========================================
// SIDE PANEL
// ==========================================

let drawerCloseHandler = null;
let lastFocus = null;

export function openDrawer(title, html, onClose = null) {
    const body = document.getElementById("drawer-body");
    // Each panel installs its own handlers; drop the previous panel's.
    body.onclick = null;
    body.onchange = null;

    if (document.getElementById("drawer").classList.contains("hidden")) {
        lastFocus = document.activeElement;
    }

    document.getElementById("drawer-title").textContent = title;
    body.innerHTML = html;
    body.scrollTop = 0;
    document.getElementById("drawer").classList.remove("hidden");
    document.getElementById("drawer-backdrop").classList.remove("hidden");
    drawerCloseHandler = onClose;

    document.getElementById("drawer-close").focus();
    return body;
}

export function closeDrawer() {
    const drawer = document.getElementById("drawer");
    const wasOpen = !drawer.classList.contains("hidden");

    drawer.classList.add("hidden");
    document.getElementById("drawer-backdrop").classList.add("hidden");

    const handler = drawerCloseHandler;
    drawerCloseHandler = null;
    if (handler) handler();

    if (wasOpen && lastFocus && document.contains(lastFocus)) lastFocus.focus();
}

export function setupDrawer() {
    document.getElementById("drawer-close").addEventListener("click", closeDrawer);
    document.getElementById("drawer-backdrop").addEventListener("click", closeDrawer);
    document.addEventListener("keydown", event => {
        if (event.key === "Escape" && !document.getElementById("drawer").classList.contains("hidden")) {
            closeDrawer();
        }
    });
}

export function fillSelect(select, values, placeholder) {
    const current = select.value;
    select.innerHTML = `<option value="">${escapeHTML(placeholder)}</option>` +
        values.map(value => `<option>${escapeHTML(value)}</option>`).join("");
    select.value = values.includes(current) ? current : "";
}
