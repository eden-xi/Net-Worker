// ==========================================
// APP: login wall + role-based routing
//
// Addresses look like  #/employee/browse  or  #/manager/review
//   role part -> which dashboard (must match the logged-in role)
//   tab part  -> which tab inside it
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

let currentUser = null;      // { email, name, role } once logged in
let chosenRole = null;       // which option was clicked on the login wall

// ---------- login wall ----------

function showLoginWall(message = "") {
    currentUser = null;
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

// ---------- routing ----------

function enterApp(user) {
    currentUser = user;
    ManagerAdminDashboard.selectedProjectId = null;

    document.getElementById("login-wall").classList.add("hidden");
    document.getElementById("app-shell").classList.remove("hidden");
    document.getElementById("user-name").textContent = user.name;
    document.getElementById("user-role").textContent = ROLE_LABELS[user.role];
    document.body.dataset.role = user.role;

    route();
}

function route() {
    if (!currentUser) return;

    const dashboard = DASHBOARDS[currentUser.role];
    const [, role, tab] = location.hash.split("/");     // "#/manager/review" -> ["#", "manager", "review"]
    const validTab = dashboard.tabs.some(item => item.id === tab);

    // Wrong dashboard for this role, or unknown tab: go to this role's first tab.
    if (role !== currentUser.role || !validTab) {
        location.replace(`#/${currentUser.role}/${dashboard.tabs[0].id}`);
        return;                                          // the hashchange event calls route() again
    }

    document.getElementById("dashboard-nav").innerHTML = dashboard.tabs.map(item => `
        <a href="#/${currentUser.role}/${item.id}" class="nav-link ${item.id === tab ? "active" : ""}">${escapeHTML(item.label)}</a>
    `).join("");

    closeModal();
    dashboard.show(tab, document.getElementById("dashboard-root"), currentUser);
}

// ---------- start ----------

document.addEventListener("DOMContentLoaded", async () => {
    document.querySelectorAll("[data-role-option]").forEach(button => {
        button.addEventListener("click", () => chooseRole(button.dataset.roleOption));
    });

    document.getElementById("login-back").addEventListener("click", showRoleOptions);
    document.getElementById("login-form").addEventListener("submit", submitLogin);
    document.getElementById("logout-button").addEventListener("click", logout);
    document.getElementById("modal-close").addEventListener("click", closeModal);
    window.addEventListener("hashchange", route);

    // Already logged in (cookie still valid)? Skip the wall.
    try {
        const { user } = await apiFetch("/api/auth/me");
        enterApp(user);
    } catch (error) {
        showLoginWall();
    }
});
