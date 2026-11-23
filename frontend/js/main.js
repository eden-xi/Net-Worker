// ProjectHub startup: detect Teams, sign in, then route by URL hash
// (#/browse, #/pm, ...) so Teams tabs and links can open any screen.

import { configureApi, get, publicRequest } from "./api.js";
import {
    authMode, devSignIn, getToken, isSignedIn, lastDevUser, setAuthMode, signOut,
} from "./auth.js";
import { avatarHTML, watchAvatars } from "./avatars.js";
import { renderStaticIcons } from "./icons.js";
import { initTeams, isInTeams, teamsStartRoute } from "./teams.js";
import { $, closeDrawer, escapeHTML, setMessage, setupDrawer } from "./ui.js";
import { initAdminView, renderAdmin } from "./views/admin.js";
import {
    initEmployeeViews, renderApplications, renderBrowse, renderProfile, renderRecommended,
} from "./views/employee.js";
import { initPmViews, renderPm } from "./views/pm.js";

const THEME_KEY = "projecthub.theme";
const ROLE_LABELS = { employee: "Employee", pm: "Project manager", admin: "Admin" };

const state = {
    me: null,
    config: null,
    demo: false,
    sampleProjects: [],

    isPm() {
        return Boolean(this.me) && ["pm", "admin"].includes(this.me.role);
    },

    roleLabel(role) {
        return ROLE_LABELS[role] || role;
    },

    async refreshMe() {
        this.me = await get("/me");
        this.updateNav();
    },

    updateNav,
};

const ROUTES = {
    browse: { render: renderBrowse, title: "Browse" },
    recommended: { render: renderRecommended, needsApi: true, title: "For you" },
    applications: { render: renderApplications, needsApi: true, title: "My applications" },
    profile: { render: renderProfile, needsApi: true, title: "My profile" },
    "post-project": {
        render: () => {}, needsApi: true, title: "Post a project",
        allowed: () => state.me?.can_become_pm,
    },
    pm: { render: renderPm, needsApi: true, allowed: canSeePm, title: "PM dashboard" },
    admin: { render: renderAdmin, needsApi: true, allowed: () => state.me?.role === "admin", title: "Admin" },
};

function canSeePm() {
    return state.isPm() || Number(state.me?.managed_projects) > 0;
}

// ==========================================
// THEME (outside Teams; Teams sets its own)
// ==========================================

function savedTheme() {
    try {
        return localStorage.getItem(THEME_KEY) || "system";
    } catch {
        return "system";
    }
}

function applyTheme(choice) {
    if (isInTeams()) return;

    if (choice === "light" || choice === "dark") {
        document.documentElement.dataset.theme = choice;
    } else {
        delete document.documentElement.dataset.theme;
    }

    document.querySelectorAll("[data-theme-choice]").forEach(button => {
        button.setAttribute("aria-checked", String(button.dataset.themeChoice === choice));
    });
}

function setupThemeSwitch() {
    applyTheme(savedTheme());

    $("#theme-switch").addEventListener("click", event => {
        const button = event.target.closest("[data-theme-choice]");
        if (!button) return;

        const choice = button.dataset.themeChoice;
        try {
            localStorage.setItem(THEME_KEY, choice);
        } catch {
            // Storage blocked: the choice lasts until the page reloads.
        }
        applyTheme(choice);
    });
}

// ==========================================
// NAVIGATION
// ==========================================

function updateNav() {
    const me = state.me;
    const signedIn = Boolean(me);
    const showPm = canSeePm();
    const showPost = Boolean(me?.can_become_pm);
    const showAdmin = me?.role === "admin";

    $("#nav-pm").classList.toggle("hidden", !showPm);
    $("#nav-post").classList.toggle("hidden", !showPost);
    $("#nav-admin").classList.toggle("hidden", !showAdmin);
    $("#nav-manage-label").classList.toggle("hidden", !(showPm || showPost || showAdmin));

    for (const route of ["recommended", "applications", "profile"]) {
        document.querySelector(`[data-route="${route}"]`).classList.toggle("hidden", state.demo);
    }

    $("#nav-user").classList.toggle("hidden", !signedIn);
    $("#sign-out").classList.toggle("hidden", authMode() !== "dev");

    if (signedIn) {
        $("#user-card-avatar").innerHTML = avatarHTML(me, "sm");
        $("#nav-user-name").textContent = me.display_name;
        $("#nav-user-role").textContent = state.roleLabel(me.role);
        $("#user-card").title = `${me.display_name}, ${me.email}`;
    }
}

function currentRoute() {
    const name = window.location.hash.replace(/^#\/?/, "").split(/[?/]/)[0];
    return ROUTES[name] ? name : "browse";
}

async function showRoute() {
    closeDrawer();

    if (!state.demo && !isSignedIn()) {
        showView("signin");
        return;
    }

    let name = currentRoute();
    const route = ROUTES[name];

    if ((route.needsApi && state.demo) || (route.allowed && !route.allowed())) {
        name = "browse";
        if (window.location.hash !== "#/browse") {
            window.location.hash = "#/browse";
            return;
        }
    }

    showView(name);
    document.title = `${ROUTES[name].title} | ProjectHub`;

    document.querySelectorAll("[data-route]").forEach(link => {
        link.classList.toggle("active", link.dataset.route === name);
        if (link.dataset.route === name) link.setAttribute("aria-current", "page");
        else link.removeAttribute("aria-current");
    });

    await ROUTES[name].render();
}

function showView(name) {
    document.querySelectorAll(".view").forEach(view => {
        view.classList.toggle("hidden", view.dataset.view !== name);
    });
    $("#nav-user").classList.toggle("hidden", name === "signin" || !state.me);
    window.scrollTo(0, 0);
}

function showBanner(html) {
    const banner = $("#banner");
    banner.innerHTML = html;
    banner.classList.toggle("hidden", !html);
}

// ==========================================
// SIGN-IN
// ==========================================

function renderDevSignIn() {
    const last = lastDevUser();
    const users = state.config.dev_users || [];

    $("#dev-user-list").innerHTML = users.map(user => `
        <button type="button" class="signin-user ${user.email === last ? "last" : ""}"
            data-dev-email="${escapeHTML(user.email)}">
            ${avatarHTML({ display_name: user.display_name }, "sm")}
            <span class="person-text">
                <strong>${escapeHTML(user.display_name)}</strong>
                <span>${escapeHTML(user.email)}</span>
            </span>
            <span class="pill ${user.role === "employee" ? "neutral" : ""}">${escapeHTML(state.roleLabel(user.role))}</span>
        </button>`).join("");
}

async function completeSignIn() {
    await state.refreshMe();
    await showRoute();
}

async function handleDevSignIn(email) {
    try {
        await devSignIn(email);
        setMessage("signin-message", "");
        await completeSignIn();
    } catch (error) {
        setMessage("signin-message", error.message, "error");
    }
}

function setupSignIn() {
    $("#dev-user-list").addEventListener("click", event => {
        const button = event.target.closest("[data-dev-email]");
        if (button) handleDevSignIn(button.dataset.devEmail);
    });

    $("#dev-login-form").addEventListener("submit", event => {
        event.preventDefault();
        handleDevSignIn($("#dev-email").value.trim());
    });

    $("#sign-out").addEventListener("click", showSignedOut);
}

async function showSignedOut(message = "") {
    signOut();
    $("#toasts").replaceChildren();
    state.me = null;
    updateNav();

    try {
        state.config = await publicRequest("/auth/config");
    } catch {
        // Keep the previous list of test users.
    }

    renderDevSignIn();
    setMessage("signin-message", typeof message === "string" ? message : "", "error");
    showView("signin");
}

function onUnauthorized() {
    if (authMode() === "dev" && state.me) {
        showSignedOut("Your session ended. Please sign in again.");
    }
}

// ==========================================
// STARTUP
// ==========================================

async function enterDemoMode() {
    state.demo = true;

    try {
        const response = await fetch("sample-projects.json");
        state.sampleProjects = (await response.json())
            .filter(project => String(project.status).toLowerCase() === "open");
    } catch {
        state.sampleProjects = [];
    }

    showBanner(`<strong>Demo mode:</strong> the ProjectHub server isn't running, so these are the
        built-in sample projects. Start it with <code>run.bat</code> to sign in and apply.`);
}

async function start() {
    renderStaticIcons();
    setupDrawer();
    setupSignIn();
    configureApi({ getToken, unauthorized: onUnauthorized });
    initEmployeeViews(state);
    initPmViews(state);
    initAdminView(state);
    watchAvatars();

    await initTeams();
    document.documentElement.classList.toggle("in-teams", isInTeams());
    setupThemeSwitch();

    if (isInTeams() && !window.location.hash) {
        const route = teamsStartRoute();
        if (route) window.location.hash = `#/${route}`;
    }

    try {
        state.config = await publicRequest("/auth/config");
    } catch {
        await enterDemoMode();
        updateNav();
        window.addEventListener("hashchange", showRoute);
        await showRoute();
        return;
    }

    setAuthMode(state.config.mode);
    window.addEventListener("hashchange", showRoute);

    if (state.config.mode === "entra" && !isInTeams()) {
        $("#signin-intro").textContent = "Open ProjectHub from Microsoft Teams to sign in with your work account.";
        $("#dev-user-list").innerHTML = "";
        $("#dev-login-form").classList.add("hidden");
        showView("signin");
        return;
    }

    if (state.config.mode === "dev") {
        renderDevSignIn();
        showView("signin");
        return;
    }

    try {
        await completeSignIn();
    } catch (error) {
        showBanner(`Sign-in failed: ${escapeHTML(error.message)}`);
    }
}

start();
