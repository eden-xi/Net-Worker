// Project manager screens:
//   #/pm                       list of projects you own or co-manage
//   #/pm/project/<id>          one project: applicants, review, status changes
//   #/pm/project/<id>/details  one project: details and co-managers
// The API only returns projects this user manages; the UI adds no access
// rules of its own.

import { download, get, postForm, request, sendJSON } from "../api.js";
import { avatarHTML } from "../avatars.js";
import { icon } from "../icons.js";
import {
    $, chips, closeDrawer, confirmClick, emptyState, escapeHTML, formatDate, matchBlock, monogram,
    openDrawer, setMessage, skeletons, splitSkills, statusPill, toast,
} from "../ui.js";

const PROJECT_STATUSES = ["Open", "On Hold", "Filled", "Closed"];
const REVIEW_FILTERS = ["New", "Shortlisted", "Accepted", "Rejected", "All"];
const PROJECT_TABS = [
    ["all", "All"],
    ["open", "Open"],
    ["on hold", "On hold"],
    ["filled", "Filled"],
    ["closed", "Closed"],
];

let state = null;
let projects = [];
let activeTab = "all";

// Project page state
let page = null;   // { project, applicants, filter, selectedId, detailOpen }

const statusKey = project => String(project.status || "").trim().toLowerCase();
const isOpen = project => statusKey(project) === "open";

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

    $("#pm-project-page").addEventListener("click", onProjectPageClick);
    $("#become-pm").addEventListener("click", becomePm);

    // Close the "More" menu when clicking elsewhere.
    document.addEventListener("click", event => {
        document.querySelectorAll("details.menu[open]").forEach(menu => {
            if (!menu.contains(event.target)) menu.open = false;
        });
    });
}

// ==========================================
// PROJECT LIST
// ==========================================

export async function renderPm(params = []) {
    if (params[0] === "project" && /^\d+$/.test(params[1] || "")) {
        return renderProjectPage(Number(params[1]), params[2] === "details" ? "details" : "applicants");
    }

    $("#new-project").classList.toggle("hidden", !state.isPm());
    $("#pm-project-list").innerHTML = skeletons(4, "row");

    try {
        projects = await get("/pm/projects");
    } catch (error) {
        $("#pm-project-list").innerHTML = emptyState("x", "Couldn't load your projects", escapeHTML(error.message));
        return;
    }

    $("#pm-open").textContent = projects.filter(isOpen).length;
    $("#pm-applicants").textContent = projects.reduce((sum, p) => sum + Number(p.applicant_count), 0);
    $("#pm-new").textContent = projects.reduce((sum, p) => sum + Number(p.new_applicant_count || 0), 0);

    renderTabs();
    renderProjectRows();
}

function renderTabs() {
    const count = key => key === "all"
        ? projects.length
        : projects.filter(project => statusKey(project) === key).length;

    $("#pm-tabs").innerHTML = PROJECT_TABS
        .filter(([key]) => key === "all" || key === "open" || count(key) > 0)
        .map(([key, label]) => `
            <button type="button" role="tab" data-tab="${key}" aria-selected="${key === activeTab}">
                ${escapeHTML(label)} <span class="count">${count(key)}</span>
            </button>`).join("");
}

function filledText(project) {
    const openings = Number(project.openings) || 1;
    const accepted = Number(project.accepted_count) || 0;
    return `${Math.min(accepted, openings)} of ${openings} filled`;
}

function renderProjectRows() {
    const container = $("#pm-project-list");

    if (projects.length === 0) {
        container.innerHTML = state.isPm()
            ? emptyState("briefcase", "Post your first project",
                "Create a posting and you'll see matching applicants here as they apply.",
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
        ? `<div class="row-header" aria-hidden="true">
                <span>Project</span><span>Status</span><span>Openings</span><span>Applicants</span><span></span>
           </div>` +
          visible.map(project => {
            const fresh = Number(project.new_applicant_count || 0);
            return `
                <a class="project-row" href="#/pm/project/${Number(project.id)}"
                    aria-label="${escapeHTML(project.title)}, ${escapeHTML(project.status)}, ${Number(project.applicant_count)} applicants${fresh ? `, ${fresh} new` : ""}">
                    <div class="project-head">
                        ${monogram(project.client_project || project.title)}
                        <div>
                            <h2>${escapeHTML(project.title)}</h2>
                            <p>${escapeHTML(project.role_id)}${project.client_project
                                ? ` &middot; ${escapeHTML(project.client_project)}` : ""}</p>
                        </div>
                    </div>
                    <div class="row-cell">${statusPill(project.status)}
                        ${project.my_role === "owner" ? "" : `<span class="muted small">Co-manager</span>`}</div>
                    <div class="row-cell"><span>${escapeHTML(filledText(project))}</span></div>
                    <div class="row-cell row-applicants">
                        <strong>${Number(project.applicant_count)}</strong>
                        ${fresh ? `<span class="pill strong">${fresh} new</span>` : ""}
                    </div>
                    <span class="row-chevron">${icon("arrowRight")}</span>
                </a>`;
        }).join("")
        : emptyState("search", "No projects here", "Try another tab or search.");
}

// ==========================================
// PROJECT PAGE
// ==========================================

async function renderProjectPage(projectId, tab) {
    const container = $("#pm-project-page");

    if (!page || page.project.id !== projectId) {
        container.innerHTML = `<a class="back-link" href="#/pm">${icon("arrowRight")}All projects</a>` + skeletons(2, "row");
    }

    let project;
    let applicants;
    try {
        [project, applicants] = await Promise.all([
            get(`/pm/projects/${projectId}`),
            get(`/pm/projects/${projectId}/applications`),
        ]);
    } catch (error) {
        page = null;
        container.innerHTML = `<a class="back-link" href="#/pm">${icon("arrowRight")}All projects</a>` +
            emptyState("briefcase", error.status === 404 ? "Project not found" : "Couldn't load this project",
                error.status === 404
                    ? "It may have been deleted, or you don't manage it."
                    : escapeHTML(error.message),
                `<a class="button" href="#/pm">Back to your projects</a>`);
        return;
    }

    const samePage = page && page.project.id === projectId;
    const newCount = applicants.filter(a => a.application_status === "New").length;

    page = {
        project,
        applicants,
        tab,
        filter: samePage ? page.filter : (newCount ? "New" : "All"),
        selectedId: samePage ? page.selectedId : null,
        detailOpen: samePage ? page.detailOpen : false,
    };

    document.title = `${project.title} | ProjectHub`;
    renderProjectShell();
}

function renderProjectShell() {
    const { project, applicants, tab } = page;
    const owner = project.my_role === "owner";
    const base = `#/pm/project/${Number(project.id)}`;

    $("#pm-project-page").innerHTML = `
        <a class="back-link" href="#/pm">${icon("arrowRight")}All projects</a>

        <header class="page-head">
            ${monogram(project.client_project || project.title)}
            <div class="page-head-text">
                <h1>${escapeHTML(project.title)}</h1>
                <p class="meta">
                    <span>${escapeHTML(project.role_id)}</span>
                    ${project.client_project ? `<span>${escapeHTML(project.client_project)}</span>` : ""}
                    <span>${escapeHTML(filledText({ ...project, accepted_count: applicants.filter(a => a.application_status === "Accepted").length }))}</span>
                </p>
            </div>
            <div class="page-head-actions">
                ${statusPill(project.status)}
                <button type="button" class="button small" data-page-action="edit">${icon("edit")}Edit</button>
                <details class="menu">
                    <summary class="button small" aria-label="More actions">More</summary>
                    <div class="menu-items" role="menu">
                        ${isOpen(project)
                            ? `<button type="button" role="menuitem" data-page-action="close">Close project</button>`
                            : `<button type="button" role="menuitem" data-page-action="reopen">Reopen project</button>`}
                        <a role="menuitem" href="${base}/details">Manage co-managers</a>
                        ${owner && applicants.length === 0
                            ? `<button type="button" role="menuitem" class="danger" data-page-action="delete">Delete project</button>`
                            : ""}
                    </div>
                </details>
            </div>
        </header>

        <nav class="page-tabs" aria-label="Project sections">
            <a href="${base}" ${tab === "applicants" ? 'aria-current="page"' : ""}>
                Applicants <span class="count">${applicants.length}</span></a>
            <a href="${base}/details" ${tab === "details" ? 'aria-current="page"' : ""}>Details and managers</a>
        </nav>

        <div id="project-tab"></div>
    `;

    if (tab === "details") renderDetailsTab();
    else renderApplicantsTab();
}

// ----- Applicants tab -----

function filteredApplicants() {
    return page.filter === "All"
        ? page.applicants
        : page.applicants.filter(a => a.application_status === page.filter);
}

function renderApplicantsTab() {
    const target = $("#project-tab");

    if (page.applicants.length === 0) {
        target.innerHTML = emptyState("users", "No applicants yet",
            isOpen(page.project)
                ? "People will appear here as soon as they apply. Applicants are ranked by how well they match."
                : "This project isn't open, so employees can't apply right now.");
        return;
    }

    const list = filteredApplicants();
    if (!list.some(a => a.id === page.selectedId)) {
        page.selectedId = list[0]?.id ?? null;
    }

    const count = status => status === "All"
        ? page.applicants.length
        : page.applicants.filter(a => a.application_status === status).length;

    target.innerHTML = `
        <div class="tabs review-filters" role="tablist" aria-label="Filter applicants by status">
            ${REVIEW_FILTERS.map(status => `
                <button type="button" role="tab" data-filter="${status}" aria-selected="${status === page.filter}">
                    ${status} <span class="count">${count(status)}</span>
                </button>`).join("")}
        </div>

        <div class="review ${page.detailOpen ? "detail-open" : ""}">
            <div class="review-list" role="listbox" aria-label="Applicants">
                ${list.length ? list.map(applicant => `
                    <button type="button" class="review-item ${applicant.id === page.selectedId ? "selected" : ""}"
                        role="option" aria-selected="${applicant.id === page.selectedId}"
                        data-applicant="${Number(applicant.id)}">
                        ${avatarHTML(applicant, "sm")}
                        <span class="person-text">
                            <strong>${escapeHTML(applicant.name)}</strong>
                            <span>${escapeHTML(applicant.application_status)} &middot; ${escapeHTML(formatDate(applicant.submitted_at, { month: "short", day: "numeric" }))}</span>
                        </span>
                        <span class="pill ${Number(applicant.match?.score) >= 75 ? "strong" : ""}">${Number(applicant.match?.score) || 0}%</span>
                    </button>`).join("")
                : `<p class="muted review-empty">No ${escapeHTML(page.filter.toLowerCase())} applicants.</p>`}
            </div>
            <div class="review-detail" id="review-detail">${renderApplicantDetail()}</div>
        </div>
    `;
}

function renderApplicantDetail() {
    const applicant = page.applicants.find(a => a.id === page.selectedId);
    if (!applicant) {
        return `<p class="muted">Select an applicant to see their details.</p>`;
    }

    const status = applicant.application_status;
    const decision = (value, label, kind) => `
        <button type="button" class="button ${status === value ? `active ${kind}` : ""}"
            data-set-status="${value}" ${status === value ? 'aria-pressed="true" disabled' : 'aria-pressed="false"'}>
            ${label}</button>`;

    return `
        <button type="button" class="link-button review-back" data-page-action="back-to-list">
            ${icon("arrowRight")}All applicants</button>

        <div class="applicant-head">
            ${avatarHTML(applicant, "lg")}
            <div class="person-text">
                <strong class="large-name">${escapeHTML(applicant.name)}</strong>
                <span>${escapeHTML(applicant.email)}</span>
                <span>Applied ${escapeHTML(formatDate(applicant.submitted_at))}</span>
            </div>
            ${statusPill(status)}
        </div>

        <div class="decision-bar" role="group" aria-label="Set status">
            ${decision("Shortlisted", "Shortlist", "")}
            ${decision("Accepted", "Accept", "success")}
            ${decision("Rejected", "Reject", "danger")}
            ${status !== "New" ? `<button type="button" class="button ghost small" data-set-status="New">Move back to New</button>` : ""}
            ${applicant.has_resume
                ? `<button type="button" class="button" data-resume="${Number(applicant.id)}">${icon("download")}Resume</button>`
                : `<span class="muted small">No resume attached</span>`}
        </div>

        <section>
            <h2>Skill match</h2>
            ${matchBlock(applicant.match)}
        </section>

        ${applicant.cover_letter ? `
            <section>
                <h2>Why they're interested</h2>
                <p class="quote">${escapeHTML(applicant.cover_letter)}</p>
            </section>` : ""}

        <section>
            <h2>All skills on their profile</h2>
            <div class="chips">${chips(splitSkills(applicant.skills)) || "<span class='muted'>None listed</span>"}</div>
        </section>
    `;
}

async function setApplicantStatus(applicant, status, { quiet = false } = {}) {
    const previous = applicant.application_status;

    try {
        await sendJSON("PATCH", `/pm/applications/${applicant.id}/status`, { status });
    } catch (error) {
        toast(error.message, "error");
        return;
    }

    applicant.application_status = status;
    // If they no longer fit the current filter, move on to the next one.
    if (page.filter !== "All" && page.filter !== status) {
        const list = filteredApplicants();
        page.selectedId = list[0]?.id ?? null;
    }
    renderProjectShell();
    state.refreshMe();

    if (!quiet) {
        toast(`${applicant.name}: ${status}.`, "success", {
            label: "Undo",
            onClick: () => setApplicantStatus(applicant, previous, { quiet: true }),
        });
    }
}

// ----- Details tab -----

async function renderDetailsTab() {
    const { project } = page;
    const target = $("#project-tab");

    target.innerHTML = `
        <div class="details-layout">
            <div class="card">
                <dl class="detail-grid">
                    <div><dt>Status</dt><dd>${escapeHTML(project.status)}</dd></div>
                    <div><dt>Openings</dt><dd>${Number(project.openings) || 1}</dd></div>
                    <div><dt>Location</dt><dd>${escapeHTML(project.location || "Not set")}</dd></div>
                    <div><dt>Seniority</dt><dd>${escapeHTML(project.seniority || "Not set")}</dd></div>
                    <div><dt>Starts</dt><dd>${escapeHTML(formatDate(project.start_date) || "Not set")}</dd></div>
                    <div><dt>Posted</dt><dd>${escapeHTML(formatDate(project.created_at))}</dd></div>
                </dl>
                <section>
                    <h2>Required skills</h2>
                    <div class="chips">${chips(splitSkills(project.required_skills)) || "<span class='muted'>None listed</span>"}</div>
                </section>
                <section>
                    <h2>Nice to have</h2>
                    <div class="chips">${chips(splitSkills(project.nice_to_have_skills)) || "<span class='muted'>None listed</span>"}</div>
                </section>
                <section>
                    <h2>Description</h2>
                    <p class="description">${escapeHTML(project.description || "No description yet. Add one with Edit so applicants know what the work involves.")}</p>
                </section>
            </div>
            <div class="card" id="managers-card">${skeletons(1, "row")}</div>
        </div>
    `;

    renderManagers();
}

async function renderManagers() {
    const { project } = page;
    const card = $("#managers-card");
    const owner = project.my_role === "owner";

    let managers;
    try {
        managers = await get(`/pm/projects/${project.id}/managers`);
    } catch (error) {
        card.innerHTML = `<p class="message error">${escapeHTML(error.message)}</p>`;
        return;
    }

    card.innerHTML = `
        <h2>Managers</h2>
        <p class="muted small">Co-managers can edit this project and review its applicants.
            ${owner ? "" : "Only the owner can add or remove other managers."}</p>
        <div class="stack-list managers">
            ${managers.map(manager => `
                <div class="person">
                    ${avatarHTML(manager, "sm")}
                    <div class="person-text">
                        <strong>${escapeHTML(manager.display_name)}</strong>
                        <span>${escapeHTML(manager.email)} &middot; ${manager.role === "owner" ? "Owner" : "Co-manager"}</span>
                    </div>
                    ${manager.role !== "owner" && (owner || manager.user_id === state.me.id) ? `
                        <button type="button" class="button ghost small" data-remove-manager="${Number(manager.user_id)}">
                            ${manager.user_id === state.me.id ? "Leave" : "Remove"}</button>` : ""}
                </div>`).join("")}
        </div>
        ${owner ? `
            <form class="form" id="add-manager-form">
                <label>Add a co-manager
                    <span class="hint">Their work email. They need to have opened ProjectHub once.</span>
                    <input type="email" name="email" required placeholder="name@company.com" autocomplete="off">
                </label>
                <div><button type="submit" class="button primary">${icon("plus")}Add co-manager</button></div>
                <p class="message" id="manager-message"></p>
            </form>` : ""}
    `;

    $("#add-manager-form", card)?.addEventListener("submit", async event => {
        event.preventDefault();
        const button = event.target.querySelector("button[type=submit]");
        button.disabled = true;
        try {
            await sendJSON("POST", `/pm/projects/${project.id}/managers`,
                { email: new FormData(event.target).get("email") });
            toast("Co-manager added.");
            renderManagers();
        } catch (error) {
            setMessage($("#manager-message"), error.message, "error");
            button.disabled = false;
        }
    });
}

// ----- Page actions -----

function onProjectPageClick(event) {
    if (!page) return;

    const filter = event.target.closest("[data-filter]");
    if (filter) {
        page.filter = filter.dataset.filter;
        page.detailOpen = false;
        renderApplicantsTab();
        return;
    }

    const item = event.target.closest("[data-applicant]");
    if (item) {
        page.selectedId = Number(item.dataset.applicant);
        page.detailOpen = true;
        renderApplicantsTab();
        $("#review-detail")?.scrollIntoView({ block: "nearest" });
        return;
    }

    const statusButton = event.target.closest("[data-set-status]");
    if (statusButton) {
        const applicant = page.applicants.find(a => a.id === page.selectedId);
        if (applicant) setApplicantStatus(applicant, statusButton.dataset.setStatus);
        return;
    }

    const resume = event.target.closest("[data-resume]");
    if (resume) {
        download(`/pm/applications/${resume.dataset.resume}/resume`, "resume")
            .catch(error => toast(error.message, "error"));
        return;
    }

    const remove = event.target.closest("[data-remove-manager]");
    if (remove) {
        const userId = Number(remove.dataset.removeManager);
        const leaving = userId === state.me.id;
        confirmClick(remove, leaving ? "Confirm leave" : "Confirm remove", async () => {
            try {
                await request(`/pm/projects/${page.project.id}/managers/${userId}`, { method: "DELETE" });
                if (leaving) {
                    toast(`You left ${page.project.title}.`);
                    page = null;
                    await state.refreshMe();
                    window.location.hash = "#/pm";
                } else {
                    toast("Co-manager removed.");
                    renderManagers();
                }
            } catch (error) {
                toast(error.message, "error");
            }
        });
        return;
    }

    const action = event.target.closest("[data-page-action]");
    if (!action) return;

    const project = page.project;
    switch (action.dataset.pageAction) {
        case "edit":
            showProjectForm(project);
            break;
        case "back-to-list":
            page.detailOpen = false;
            renderApplicantsTab();
            break;
        case "close":
            confirmClick(action, "Confirm close", () => setOpen(project, false));
            break;
        case "reopen":
            setOpen(project, true);
            break;
        case "delete":
            confirmClick(action, "Confirm delete", async () => {
                try {
                    await request(`/pm/projects/${project.id}`, { method: "DELETE" });
                    toast(`${project.title} deleted.`);
                    page = null;
                    await state.refreshMe();
                    window.location.hash = "#/pm";
                } catch (error) {
                    toast(error.message, "error");
                }
            });
            break;
    }
}

async function setOpen(project, open) {
    try {
        await request(`/pm/projects/${project.id}/${open ? "reopen" : "close"}`, { method: "POST" });
        toast(open ? `${project.title} is open again.` : `${project.title} closed. Employees no longer see it.`);
        refresh();
    } catch (error) {
        toast(error.message, "error");
    }
}

function refresh() {
    if (page && window.location.hash.startsWith(`#/pm/project/${page.project.id}`)) {
        renderProjectPage(page.project.id, page.tab);
    } else {
        renderPm();
    }
}

// ==========================================
// CREATE AND EDIT
// ==========================================

function field(name, label, value = "", attributes = "", hint = "") {
    return `<label>${label}${hint ? ` <span class="hint">${hint}</span>` : ""}
        <input name="${name}" id="project-${name}" value="${escapeHTML(value)}" ${attributes}></label>`;
}

function showProjectForm(project) {
    const value = key => (project ? project[key] ?? "" : "");
    const status = project ? project.status : "Open";

    const body = openDrawer(project ? "Edit project" : "New project", `
        <form class="form" id="project-form" novalidate>
            ${field("title", "Project title", value("title"), 'required maxlength="200" placeholder="e.g. Data Engineer"')}
            <div class="form-row">
                ${field("role_id", "Role ID", value("role_id"),
                    project ? "disabled" : 'required maxlength="64" placeholder="e.g. DATA-104"',
                    project ? "" : "Must be unique")}
                <label>Status
                    <select name="status" id="project-status">
                        ${PROJECT_STATUSES.map(option =>
                            `<option ${option === status ? "selected" : ""}>${option}</option>`).join("")}
                    </select>
                </label>
                ${field("openings", "Openings", project ? value("openings") : 1,
                    'type="number" min="1" max="500" required', "People needed")}
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
                <textarea name="description" id="project-description" rows="6" maxlength="10000"
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
        const form = event.target;

        const invalid = [...form.elements].find(element => element.willValidate && !element.checkValidity());
        if (invalid) {
            const label = invalid.closest("label")?.childNodes[0]?.textContent.trim() || "This field";
            setMessage($("#project-form-message"),
                invalid.validity.valueMissing ? `${label} is required.` : `${label}: ${invalid.validationMessage}`, "error");
            invalid.focus();
            return;
        }

        const data = Object.fromEntries(new FormData(form));
        data.openings = Number(data.openings) || 1;
        const button = form.querySelector("button[type=submit]");
        button.disabled = true;

        try {
            if (project) {
                delete data.role_id;
                await sendJSON("PATCH", `/pm/projects/${project.id}`, data);
                closeDrawer();
                toast("Changes saved.");
                refresh();
            } else {
                const created = await sendJSON("POST", "/pm/projects", data);
                closeDrawer();
                toast(`${data.title} is published.`);
                await state.refreshMe();
                window.location.hash = `#/pm/project/${created.id}`;
            }
        } catch (error) {
            setMessage($("#project-form-message"), error.message, "error");
            button.disabled = false;
        }
    });
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
        await state.refreshMe();
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
