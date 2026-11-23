// Project manager screens. The API only ever returns projects this user
// owns or co-manages; the UI adds no access rules of its own.

import { download, get, postForm, request, sendJSON } from "../api.js";
import { avatarHTML } from "../avatars.js";
import { icon } from "../icons.js";
import {
    $, chips, closeDrawer, confirmClick, emptyState, escapeHTML, formatDate, matchBlock, monogram,
    openDrawer, setMessage, skeletons, splitSkills, statusPill, toast,
} from "../ui.js";

const PROJECT_STATUSES = ["Open", "On Hold", "Filled", "Closed"];
const APPLICATION_STATUSES = ["Submitted", "Under Review", "Accepted", "Rejected"];
const TABS = [
    ["all", "All"],
    ["open", "Open"],
    ["on hold", "On hold"],
    ["filled", "Filled"],
    ["closed", "Closed"],
];

let state = null;
let projects = [];
let activeTab = "all";

const statusKey = project => String(project.status || "").trim().toLowerCase();

export function initPmViews(appState) {
    state = appState;

    $("#new-project").addEventListener("click", () => showProjectForm(null));
    $("#upload-csv").addEventListener("click", uploadCsv);
    $("#pm-search").addEventListener("input", renderProjectRows);

    $("#pm-tabs").addEventListener("click", event => {
        const tab = event.target.closest("[data-tab]");
        if (!tab) return;
        activeTab = tab.dataset.tab;
        renderTabs();
        renderProjectRows();
    });

    $("#pm-project-list").addEventListener("click", event => {
        const button = event.target.closest("[data-pm-action]");
        if (!button) return;

        const project = projects.find(item => item.id === Number(button.dataset.id));
        if (!project) return;

        const actions = {
            edit: () => showProjectForm(project),
            applicants: () => showApplicants(project),
            managers: () => showManagers(project),
            close: () => confirmClick(button, "Confirm close", () => setOpen(project, false)),
            reopen: () => setOpen(project, true),
        };
        actions[button.dataset.pmAction]?.();
    });

    $("#become-pm").addEventListener("click", becomePm);
}

// ==========================================
// DASHBOARD
// ==========================================

export async function renderPm() {
    $("#new-project").classList.toggle("hidden", !state.isPm());
    $("#pm-project-list").innerHTML = skeletons(4, "row");

    try {
        projects = await get("/pm/projects");
    } catch (error) {
        $("#pm-project-list").innerHTML = emptyState("x", "Couldn't load your projects", escapeHTML(error.message));
        return;
    }

    $("#pm-open").textContent = projects.filter(project => statusKey(project) === "open").length;
    $("#pm-applicants").textContent = projects.reduce((sum, p) => sum + Number(p.applicant_count), 0);
    $("#pm-new").textContent = projects.reduce((sum, p) => sum + Number(p.new_applicant_count || 0), 0);

    renderTabs();
    renderProjectRows();
}

function renderTabs() {
    const count = key => key === "all"
        ? projects.length
        : projects.filter(project => statusKey(project) === key).length;

    $("#pm-tabs").innerHTML = TABS
        .filter(([key]) => key === "all" || key === "open" || count(key) > 0)
        .map(([key, label]) => `
            <button type="button" role="tab" data-tab="${key}" aria-selected="${key === activeTab}">
                ${escapeHTML(label)} <span class="count">${count(key)}</span>
            </button>`).join("");
}

function renderProjectRows() {
    const container = $("#pm-project-list");

    if (projects.length === 0) {
        container.innerHTML = state.isPm()
            ? emptyState("briefcase", "Post your first project",
                "Create a posting and we'll show you matching applicants as they apply.",
                `<button type="button" class="button primary" id="empty-new-project">${icon("plus")}New project</button>`)
            : emptyState("briefcase", "No projects yet",
                "Projects you're added to as a co-manager will appear here.");
        $("#empty-new-project")?.addEventListener("click", () => showProjectForm(null));
        return;
    }

    const text = $("#pm-search").value.trim().toLowerCase();
    const visible = projects.filter(project =>
        (activeTab === "all" || statusKey(project) === activeTab) &&
        [project.title, project.role_id, project.client_project].join(" ").toLowerCase().includes(text));

    container.innerHTML = visible.length
        ? visible.map(project => {
            const isOpen = statusKey(project) === "open";
            const total = Number(project.applicant_count);
            const fresh = Number(project.new_applicant_count || 0);

            return `
                <article class="project-row">
                    <div class="project-head">
                        ${monogram(project.client_project || project.title)}
                        <div>
                            <h3>${escapeHTML(project.title)}</h3>
                            <p>${escapeHTML(project.role_id)}${project.client_project
                                ? ` &middot; ${escapeHTML(project.client_project)}` : ""}</p>
                        </div>
                    </div>
                    <div class="row-cell status-cell">
                        <span class="label">Status</span>
                        ${statusPill(project.status)}
                        <span class="muted small">${project.my_role === "owner" ? "You own this" : "Co-manager"}</span>
                    </div>
                    <div class="row-cell">
                        <span class="label">Applicants</span>
                        <div class="row-applicants">
                            <strong>${total}</strong>
                            ${fresh ? `<span class="pill strong">${fresh} new</span>` : ""}
                            <span class="hide-wide">${statusPill(project.status)}</span>
                        </div>
                    </div>
                    <div class="row-actions">
                        <button type="button" class="button ${fresh ? "primary" : ""} small" data-pm-action="applicants"
                            data-id="${Number(project.id)}" ${total ? "" : "disabled"}>
                            ${icon("users")}${fresh ? "Review" : "Applicants"}</button>
                        <button type="button" class="button small" data-pm-action="edit" data-id="${Number(project.id)}">
                            ${icon("edit")}Edit</button>
                        <button type="button" class="button small" data-pm-action="managers" data-id="${Number(project.id)}">
                            Managers</button>
                        ${isOpen
                            ? `<button type="button" class="button ghost small" data-pm-action="close"
                                data-id="${Number(project.id)}">Close</button>`
                            : `<button type="button" class="button ghost small" data-pm-action="reopen"
                                data-id="${Number(project.id)}">Reopen</button>`}
                    </div>
                </article>`;
        }).join("")
        : emptyState("search", "No projects here", "Try another tab or search.");
}

async function setOpen(project, open) {
    try {
        await request(`/pm/projects/${project.id}/${open ? "reopen" : "close"}`, { method: "POST" });
        toast(open ? `${project.title} is open again.` : `${project.title} closed. Employees no longer see it.`);
        renderPm();
    } catch (error) {
        toast(error.message, "error");
    }
}

// ==========================================
// CREATE AND EDIT
// ==========================================

function field(name, label, value = "", attributes = "", hint = "") {
    return `<label>${label}${hint ? ` <span class="hint">${hint}</span>` : ""}
        <input name="${name}" value="${escapeHTML(value)}" ${attributes}></label>`;
}

function showProjectForm(project) {
    const value = key => (project ? project[key] || "" : "");
    const status = project ? project.status : "Open";

    const body = openDrawer(project ? `Edit project` : "New project", `
        <form class="form" id="project-form">
            ${field("title", "Project title", value("title"), 'required maxlength="200" placeholder="e.g. Data Engineer"')}
            <div class="form-row">
                ${field("role_id", "Role ID", value("role_id"),
                    project ? "disabled" : 'required maxlength="64" placeholder="e.g. DATA-104"',
                    project ? "" : "Must be unique")}
                <label>Status
                    <select name="status">
                        ${PROJECT_STATUSES.map(option =>
                            `<option ${option === status ? "selected" : ""}>${option}</option>`).join("")}
                    </select>
                </label>
            </div>
            ${field("client_project", "Client or team", value("client_project"), 'maxlength="200"')}
            ${field("required_skills", "Required skills", value("required_skills"),
                'maxlength="1000" placeholder="SQL, Python, Power BI"', "Separate with commas")}
            ${field("nice_to_have_skills", "Nice-to-have skills", value("nice_to_have_skills"), 'maxlength="1000"')}
            <div class="form-row">
                ${field("seniority", "Seniority", value("seniority"), 'maxlength="50" list="seniority-options"')}
                ${field("location", "Location", value("location"), 'maxlength="100" placeholder="Remote, Dallas TX..."')}
                ${field("start_date", "Start date", value("start_date"), 'type="date"')}
            </div>
            <datalist id="seniority-options">
                <option>Junior</option><option>Mid</option><option>Senior</option><option>Lead</option>
            </datalist>
            <label>Description
                <textarea name="description" rows="6" maxlength="10000"
                    placeholder="What will the person work on? Who's on the team?">${escapeHTML(value("description"))}</textarea>
            </label>
            <div class="actions">
                <button type="submit" class="button primary">${project ? "Save changes" : "Publish project"}</button>
                <button type="button" class="button ghost" id="cancel-project">Cancel</button>
            </div>
            <p class="message" id="project-form-message"></p>
        </form>
    `);

    $("#cancel-project", body).addEventListener("click", closeDrawer);
    $("#project-form", body).addEventListener("submit", async event => {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(event.target));

        try {
            if (project) {
                delete data.role_id;
                await sendJSON("PATCH", `/pm/projects/${project.id}`, data);
            } else {
                await sendJSON("POST", "/pm/projects", data);
            }
            closeDrawer();
            toast(project ? "Changes saved." : `${data.title} is published.`);
            renderPm();
        } catch (error) {
            setMessage($("#project-form-message"), error.message, "error");
        }
    });
}

// ==========================================
// APPLICANTS
// ==========================================

async function showApplicants(project) {
    const body = openDrawer(project.title, skeletons(2, "row"));

    let applicants;
    try {
        applicants = await get(`/pm/projects/${project.id}/applications`);
    } catch (error) {
        body.innerHTML = `<p class="message error">${escapeHTML(error.message)}</p>`;
        return;
    }

    const fresh = applicants.filter(a => a.application_status === "Submitted").length;

    body.innerHTML = applicants.length
        ? `
            <div class="summary-bar">
                <span class="pill neutral">${applicants.length} applicant${applicants.length === 1 ? "" : "s"}</span>
                ${fresh ? `<span class="pill strong">${fresh} new</span>` : ""}
                <span class="pill neutral">Best match first</span>
            </div>
            ${applicants.map(applicant => `
                <article class="applicant">
                    <div class="applicant-head">
                        ${avatarHTML(applicant, "md")}
                        <div class="person-text">
                            <strong>${escapeHTML(applicant.name)}</strong>
                            <span>${escapeHTML(applicant.email)} &middot; applied ${escapeHTML(formatDate(applicant.submitted_at))}</span>
                        </div>
                        ${statusPill(applicant.application_status)}
                    </div>
                    ${matchBlock(applicant.match)}
                    ${applicant.cover_letter ? `<p class="quote">${escapeHTML(applicant.cover_letter)}</p>` : ""}
                    <details>
                        <summary class="muted small">All profile skills</summary>
                        <div class="chips">${chips(splitSkills(applicant.skills)) || "<span class='muted'>None listed</span>"}</div>
                    </details>
                    <div class="applicant-actions">
                        <label class="field-label">Status
                            <select data-application-status="${Number(applicant.id)}">
                                ${APPLICATION_STATUSES.map(status =>
                                    `<option ${status === applicant.application_status ? "selected" : ""}>${status}</option>`
                                ).join("")}
                            </select>
                        </label>
                        ${applicant.has_resume
                            ? `<button type="button" class="button" data-resume="${Number(applicant.id)}">
                                ${icon("download")}Resume</button>` : ""}
                    </div>
                </article>`).join("")}`
        : emptyState("users", "No applicants yet", "You'll see people here as soon as they apply.");

    body.onchange = async event => {
        const select = event.target.closest("[data-application-status]");
        if (!select) return;

        select.disabled = true;
        try {
            await sendJSON("PATCH", `/pm/applications/${select.dataset.applicationStatus}/status`,
                { status: select.value });
            select.closest(".applicant").querySelector(".applicant-head .pill").outerHTML = statusPill(select.value);
            toast(`Marked as ${select.value}.`);
            renderPm();
        } catch (error) {
            toast(error.message, "error");
        } finally {
            select.disabled = false;
        }
    };

    body.onclick = async event => {
        const button = event.target.closest("[data-resume]");
        if (!button) return;

        try {
            await download(`/pm/applications/${button.dataset.resume}/resume`, "resume");
        } catch (error) {
            toast(error.message, "error");
        }
    };
}

// ==========================================
// CO-MANAGERS
// ==========================================

async function showManagers(project) {
    const isOwner = project.my_role === "owner";
    const body = openDrawer(`Managers: ${project.title}`, skeletons(2, "row"));

    async function render() {
        let managers;
        try {
            managers = await get(`/pm/projects/${project.id}/managers`);
        } catch (error) {
            body.innerHTML = `<p class="message error">${escapeHTML(error.message)}</p>`;
            return;
        }

        body.innerHTML = `
            <p class="muted">Co-managers can edit this project and review its applicants.
                ${isOwner ? "" : "Only the owner can add or remove other managers."}</p>
            <div class="stack-list">
                ${managers.map(manager => `
                    <div class="applicant">
                        <div class="applicant-head">
                            ${avatarHTML(manager, "sm")}
                            <div class="person-text">
                                <strong>${escapeHTML(manager.display_name)}</strong>
                                <span>${escapeHTML(manager.email)}</span>
                            </div>
                            <span class="pill ${manager.role === "owner" ? "" : "neutral"}">
                                ${manager.role === "owner" ? "Owner" : "Co-manager"}</span>
                        </div>
                        ${manager.role !== "owner" && (isOwner || manager.user_id === state.me.id) ? `
                            <div>
                                <button type="button" class="button danger small" data-remove-manager="${Number(manager.user_id)}">
                                    ${manager.user_id === state.me.id ? "Leave project" : "Remove"}</button>
                            </div>` : ""}
                    </div>`).join("")}
            </div>
            ${isOwner ? `
                <form class="form apply-box" id="add-manager-form">
                    <label>Add a co-manager
                        <span class="hint">Enter their work email. They need to have opened ProjectHub once.</span>
                        <input type="email" name="email" required placeholder="name@company.com">
                    </label>
                    <div class="actions"><button type="submit" class="button primary">${icon("plus")}Add co-manager</button></div>
                    <p class="message" id="manager-message"></p>
                </form>` : ""}
        `;

        $("#add-manager-form", body)?.addEventListener("submit", async event => {
            event.preventDefault();
            try {
                await sendJSON("POST", `/pm/projects/${project.id}/managers`,
                    { email: new FormData(event.target).get("email") });
                toast("Co-manager added.");
                render();
            } catch (error) {
                setMessage($("#manager-message"), error.message, "error");
            }
        });
    }

    body.onclick = event => {
        const button = event.target.closest("[data-remove-manager]");
        if (!button) return;

        const userId = Number(button.dataset.removeManager);
        const leaving = userId === state.me.id;

        confirmClick(button, leaving ? "Confirm leave" : "Confirm remove", async () => {
            try {
                await request(`/pm/projects/${project.id}/managers/${userId}`, { method: "DELETE" });
                if (leaving) {
                    closeDrawer();
                    toast(`You left ${project.title}.`);
                    await state.refreshMe();
                    renderPm();
                } else {
                    toast("Co-manager removed.");
                    render();
                }
            } catch (error) {
                toast(error.message, "error");
            }
        });
    };

    render();
}

// ==========================================
// CSV IMPORT
// ==========================================

async function uploadCsv() {
    const file = $("#csv-file").files[0];

    if (!file) {
        setMessage("csv-message", "Choose a CSV file first.", "error");
        return;
    }

    const data = new FormData();
    data.append("file", file);

    try {
        const result = await postForm("/pm/projects/upload-csv", data);
        const conflicts = result.conflict_rows.length
            ? ` Rows ${result.conflict_rows.join(", ")} use a Role ID that belongs to someone else's project and were skipped.`
            : "";

        setMessage("csv-message",
            `Added ${result.imported}, updated ${result.updated}, skipped ${result.skipped}.${conflicts}`);
        $("#csv-file").value = "";
        renderPm();
    } catch (error) {
        setMessage("csv-message", error.message, "error");
    }
}

// ==========================================
// SELF-SERVICE PM ACCESS
// ==========================================

async function becomePm() {
    const button = $("#become-pm");
    button.disabled = true;

    try {
        state.me = await request("/me/become-pm", { method: "POST" });
        state.updateNav();
        toast("You're set up as a project manager.");
        window.location.hash = "#/pm";
    } catch (error) {
        setMessage("become-pm-message", error.message, "error");
    } finally {
        button.disabled = false;
    }
}
