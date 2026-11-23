// Profile pictures. Pictures need the sign-in token, so they are fetched
// with it and shown from a blob: URL. Until then (or with no picture) the
// person's initials appear on a purple background.

import { request } from "./api.js";
import { escapeHTML } from "./ui.js";

// Purples only, so avatars stay within the color scheme.
const SHADES = ["#A100FF", "#7A1FC9", "#8E44D6", "#5B2A86", "#B145F0", "#6C18B5"];

const cache = new Map();  // "userId:version" -> Promise<objectURL>

export function initials(name) {
    const parts = String(name || "?").replace(/\(.*?\)/g, "").trim().split(/[\s@._-]+/).filter(Boolean);
    const letters = parts.length > 1 ? parts[0][0] + parts[parts.length - 1][0] : (parts[0] || "?").slice(0, 2);
    return letters.toUpperCase();
}

function shade(name) {
    let hash = 0;
    for (const character of String(name)) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
    return SHADES[hash % SHADES.length];
}

/**
 * Avatar markup. `person` needs a name and, for a picture, `id` (or
 * `user_id`) and `avatar` (the picture version from the API).
 */
export function avatarHTML(person, size = "md") {
    const name = person.display_name || person.name || person.email || "";
    const id = person.user_id ?? person.id;
    const picture = person.avatar && id != null
        ? `data-avatar-user="${Number(id)}" data-avatar-version="${escapeHTML(person.avatar)}"`
        : "";

    return `<span class="avatar avatar-${size} shade-${SHADES.indexOf(shade(name))}" ${picture}
        role="img" aria-label="${escapeHTML(name)}">${escapeHTML(initials(name))}</span>`;
}

function load(userId, version) {
    const key = `${userId}:${version}`;

    if (!cache.has(key)) {
        cache.set(key, request(`/users/${userId}/avatar?v=${encodeURIComponent(version)}`)
            .then(response => response.blob())
            .then(blob => URL.createObjectURL(blob))
            .catch(() => null));
    }

    return cache.get(key);
}

async function hydrate(element) {
    element.dataset.avatarLoading = "1";
    const url = await load(element.dataset.avatarUser, element.dataset.avatarVersion);
    if (!url) return;

    const image = document.createElement("img");
    image.src = url;
    image.alt = "";
    element.replaceChildren(image);
    element.classList.add("has-picture");
}

/** Load pictures for avatars as they appear anywhere on the page. */
export function watchAvatars() {
    const scan = () => {
        document.querySelectorAll("[data-avatar-version]:not([data-avatar-loading])").forEach(hydrate);
    };

    new MutationObserver(scan).observe(document.body, { childList: true, subtree: true });
    scan();
}
