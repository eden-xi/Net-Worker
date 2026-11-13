// ==========================================
// APP: login wall + role-based routing
//
// Addresses look like  #/employee/browse  or  #/manager/review
//   role part -> which dashboard (must match the signed-in role)
//   page part -> which page inside it
// The server enforces the real rules; this file only decides what to draw.
// ==========================================

const DASHBOARDS = {
    employee: EmployeeDashboard,
    manager: ManagerAdminDashboard
};

const ROLE_LABELS = {
    employee: "Employee",
    manager: "Project Manager"
};

let currentUser = null;      // { email, name, role } once signed in
let chosenRole = null;       // which option was clicked on the login wall

// ---------- login wall ----------

function showLoginWall(message = "") {
    currentUser = null;
    stopPolling();
    closeModal();
    document.getElementById("app-shell").classList.add("hidden");
    document.getElementById("login-wall").classList.remove("hidden");
    showRoleOptions();
    setStatus(document.getElementById("login-status"), message, Boolean(message));
}

function showRoleOptions() {
    chosenRole = null;
    document.getElementById("role-options").classList.remove("hidden");
    document.getElementById("login-form").classList.add("hidden");
}

function chooseRole(role) {
    chosenRole = role;
    document.getElementById("role-options").classList.add("hidden");
    document.getElementById("login-form").classList.remove("hidden");
    document.getElementById("login-role-label").textContent = `Sign in as ${ROLE_LABELS[role]}`;
    setStatus(document.getElementById("login-status"), "");
    document.getElementById("login-email").focus();
    showTestAccountHint(role);
}

async function showTestAccountHint(role) {
    const hint = document.getElementById("login-hint");
    hint.innerHTML = "";

    try {
        const { login_mode } = await apiFetch("/api/auth/mode");

        if (login_mode === "open") {
            hint.textContent = "Open demo mode: any email and password will work.";
            return;
        }

        const demo = role === "manager"
            ? { email: "manager@networker.test", password: "manager-demo" }
            : { email: "employee@networker.test", password: "employee-demo" };

        hint.innerHTML = `Test account: <code>${demo.email}</code> / <code>${demo.password}</code>
            <button type="button" class="link-button" id="fill-demo">Fill in</button>`;

        document.getElementById("fill-demo").addEventListener("click", () => {
            document.getElementById("login-email").value = demo.email;
            document.getElementById("login-password").value = demo.password;
        });
    } catch (error) {
        hint.textContent = "";
    }
}

async function submitLogin(event) {
    event.preventDefault();
    const status = document.getElementById("login-status");

    try {
        setStatus(status, "Signing in...");
        const { user } = await sendJSON("/api/auth/login", "POST", {
            email: document.getElementById("login-email").value,
            password: document.getElementById("login-password").value,
            role: chosenRole
        });

        document.getElementById("login-form").reset();
        setStatus(status, "");
        enterApp(user);
    } catch (error) {
        setStatus(status, error.message, true);
    }
}

async function logout() {
    try {
        await apiFetch("/api/auth/logout", { method: "POST" });
    } finally {
        location.hash = "";
        showLoginWall("You have been signed out.");
    }
}

// ---------- light / dark (remembered in this browser only) ----------

function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    document.getElementById("theme-toggle").textContent = theme === "dark" ? "Light mode" : "Dark mode";
    try {
        localStorage.setItem("networker-theme", theme);
    } catch (error) {
        /* private browsing: the choice just isn't remembered */
    }
}

function savedTheme() {
    try {
        return localStorage.getItem("networker-theme") || "light";
    } catch (error) {
        return "light";
    }
}

// ---------- routing ----------

function enterApp(user) {
    currentUser = user;
    ManagerAdminDashboard.selectedProjectId = null;

    document.getElementById("login-wall").classList.add("hidden");
    document.getElementById("app-shell").classList.remove("hidden");
    document.getElementById("user-name").textContent = user.name;
    document.getElementById("user-role").textContent = ROLE_LABELS[user.role];
    document.getElementById("user-avatar").textContent = initials(user.name);
    document.body.dataset.role = user.role;

    route();
}

function route() {
    if (!currentUser) return;

    const dashboard = DASHBOARDS[currentUser.role];
    const [, role, page] = location.hash.split("/");      // "#/manager/review" -> ["#", "manager", "review"]
    const validPage = dashboard.tabs.some(item => item.id === page);

    // Wrong dashboard for this role, or unknown page: go to this role's first page.
    if (role !== currentUser.role || !validPage) {
        location.replace(`#/${currentUser.role}/${dashboard.tabs[0].id}`);
        return;                                          // the hashchange event calls route() again
    }

    document.getElementById("dashboard-nav").innerHTML = dashboard.tabs.map(item => `
        <a href="#/${currentUser.role}/${item.id}" class="nav-link ${item.id === page ? "active" : ""}"
           ${item.id === page ? 'aria-current="page"' : ""}>${icon(item.icon)}${escapeHTML(item.label)}</a>
    `).join("");

    stopPolling();                                       // the old page's timer must not keep running
    closeModal();
    window.scrollTo(0, 0);

    // Each page draws into its OWN fresh box. If you leave a page before it finishes loading,
    // its late answer lands in a box that is no longer on screen, instead of over the new page.
    const box = document.createElement("div");
    document.getElementById("dashboard-root").replaceChildren(box);
    dashboard.show(page, box, currentUser);
}

// ---------- start ----------

document.addEventListener("DOMContentLoaded", async () => {
    document.querySelectorAll("[data-icon]").forEach(element => { element.innerHTML = icon(element.dataset.icon, 20); });
    document.querySelectorAll("[data-role-option]").forEach(button => {
        button.addEventListener("click", () => chooseRole(button.dataset.roleOption));
    });

    document.getElementById("login-back").addEventListener("click", showRoleOptions);
    document.getElementById("login-form").addEventListener("submit", submitLogin);
    document.getElementById("logout-button").addEventListener("click", logout);
    document.getElementById("modal-close").addEventListener("click", closeModal);
    document.getElementById("modal").addEventListener("click", event => {
        if (event.target.id === "modal") closeModal();                // click outside the drawer
    });
    document.addEventListener("keydown", event => { if (event.key === "Escape") closeModal(); });
    document.getElementById("theme-toggle").addEventListener("click", () =>
        applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
    window.addEventListener("hashchange", route);
    applyTheme(savedTheme());

    // Already signed in (cookie still valid)? Skip the wall.
    try {
        const { user } = await apiFetch("/api/auth/me");
        enterApp(user);
    } catch (error) {
        showLoginWall();
    }
});
