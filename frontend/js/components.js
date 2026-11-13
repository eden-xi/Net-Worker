// ==========================================
// SHARED COMPONENTS
// Used by BOTH EmployeeDashboard (employee.js) and ManagerAdminDashboard (manager.js).
// A "component" here is just a function that returns HTML or fills a container.
// ==========================================

// ---------- small helpers ----------

function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, character => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
    })[character]);
}

function splitSkills(value) {
    return String(value || "")
        .split(/[,;|]/)
        .map(skill => skill.trim())
        .filter(Boolean);
}

function setStatus(element, message, isError = false) {
    if (!element) return;
    element.textContent = message;
    element.className = isError ? "status-text error" : "status-text success";
}

// ---------- talking to the server ----------

// One place for every request. Cookies (the session) are sent automatically because
// the page and the API live on the same address. A 401 means the session ended,
// so we send the person back to the login wall (showLoginWall lives in app.js).
async function apiFetch(url, options = {}) {
    const response = await fetch(url, { credentials: "same-origin", ...options });
    let body = null;

    try {
        body = await response.json();
    } catch (error) {
        body = null;
    }

    if (response.status === 401 && !url.startsWith("/api/auth/")) {
        showLoginWall("Your session ended. Please log in again.");
    }

    if (!response.ok) {
        throw new Error((body && body.detail) || `Request failed (${response.status}).`);
    }

    return body;
}

function sendJSON(url, method, data) {
    return apiFetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data)
    });
}

// ---------- listing card ----------

// actions: [{ label: "Apply", action: "apply", primary: true }]
function ListingCard(project, actions) {
    const skills = splitSkills(project.required_skills).slice(0, 5);

    return `
        <article class="listing-card">
            <div class="listing-card-top">
                <span class="pill">${escapeHTML(project.seniority || "Any level")}</span>
                <span class="muted">${escapeHTML(project.location || "Location TBD")}</span>
            </div>
            <h3>${escapeHTML(project.title)}</h3>
            <p class="muted">${escapeHTML(project.client_project || "Internal project")}</p>
            <div class="skill-row">
                ${skills.map(skill => `<span class="skill">${escapeHTML(skill)}</span>`).join("")}
            </div>
            <div class="card-actions">
                ${actions.map(item => `
                    <button
                        type="button"
                        class="${item.primary ? "primary-button" : "secondary-button"}"
                        data-action="${escapeHTML(item.action)}"
                        data-id="${Number(project.id)}"
                    >${escapeHTML(item.label)}</button>
                `).join("")}
            </div>
        </article>
    `;
}

// ---------- listing metadata block (details pop-up AND the manager's document viewer) ----------

function ProjectMetadata(project) {
    const rows = [
        ["Role ID", project.role_id],
        ["Client / project", project.client_project],
        ["Required skills", project.required_skills],
        ["Nice to have", project.nice_to_have_skills],
        ["Seniority", project.seniority],
        ["Location", project.location],
        ["Start date", project.start_date],
        ["Status", project.status]
    ];

    return `
        <div class="metadata">
            <h3>${escapeHTML(project.title)}</h3>
            <dl>
                ${rows.filter(([, value]) => value).map(([label, value]) => `
                    <dt>${escapeHTML(label)}</dt><dd>${escapeHTML(value)}</dd>
                `).join("")}
            </dl>
            ${project.description ? `<p class="description">${escapeHTML(project.description)}</p>` : ""}
        </div>
    `;
}

// ---------- job feed: search + location filter + grid of cards ----------

// options:
//   title, subtitle    - heading text
//   actionsFor(project) - which buttons each card gets (this is what differs per role)
//   onAction(action, project) - what happens when one is clicked
async function renderJobFeed(container, options) {
    container.innerHTML = `
        <section class="feed">
            <div class="page-header">
                <h1>${escapeHTML(options.title)}</h1>
                <p class="muted">${escapeHTML(options.subtitle || "")}</p>
            </div>
            <div class="feed-toolbar">
                <input type="search" class="feed-search" placeholder="Search title, skill, or client...">
                <select class="feed-location"><option value="">All locations</option></select>
                <span class="feed-count muted"></span>
            </div>
            <div class="listing-grid"><p class="muted">Loading projects...</p></div>
        </section>
    `;

    // A fresh <section> each time, so click listeners never pile up between tab switches.
    const feed = container.querySelector(".feed");
    const grid = feed.querySelector(".listing-grid");
    const search = feed.querySelector(".feed-search");
    const location = feed.querySelector(".feed-location");
    const count = feed.querySelector(".feed-count");

    let projects = [];

    try {
        projects = await apiFetch("/api/projects");          // Open listings only
    } catch (error) {
        grid.innerHTML = `<p class="status-text error">${escapeHTML(error.message)}</p>`;
        return;
    }

    const locations = [...new Set(projects.map(p => p.location).filter(Boolean))].sort();
    location.innerHTML += locations
        .map(name => `<option value="${escapeHTML(name)}">${escapeHTML(name)}</option>`)
        .join("");

    function draw() {
        const term = search.value.trim().toLowerCase();
        const place = location.value;

        const visible = projects.filter(project => {
            const text = [project.title, project.client_project, project.required_skills, project.description]
                .join(" ")
                .toLowerCase();
            return text.includes(term) && (!place || project.location === place);
        });

        count.textContent = `${visible.length} of ${projects.length} open listings`;
        grid.innerHTML = visible.length
            ? visible.map(project => ListingCard(project, options.actionsFor(project))).join("")
            : `<p class="muted">No listings match your search.</p>`;
    }

    search.addEventListener("input", draw);
    location.addEventListener("change", draw);

    feed.addEventListener("click", event => {
        const button = event.target.closest("[data-action]");
        if (!button) return;

        const project = projects.find(item => Number(item.id) === Number(button.dataset.id));
        if (project) options.onAction(button.dataset.action, project);
    });

    draw();
}

// ---------- pop-up window ----------

function openModal(html) {
    document.getElementById("modal-body").innerHTML = html;
    document.getElementById("modal").classList.remove("hidden");
}

function closeModal() {
    document.getElementById("modal").classList.add("hidden");
    document.getElementById("modal-body").innerHTML = "";
}
