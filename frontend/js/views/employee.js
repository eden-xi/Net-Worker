// Employee screens: home (browse), recommendations, applications, profile.

import { request, get, postForm, sendJSON } from "../api.js";
import { avatarHTML } from "../avatars.js";
import { icon } from "../icons.js";
import {
    $, chips, closeDrawer, emptyState, escapeHTML, fillSelect, formatDate, matchBlock, matchPill,
    monogram, openDrawer, setMessage, skeletons, splitSkills, statusPill, toast,
} from "../ui.js";

let state = null;
let openProjects = [];
let matches = new Map();     // project id -> match details
let applicationCount = 0;
let sortChosen = false;      // true once the user picks a sort order themselves

export function initEmployeeViews(appState) {
    state = appState;

    $("#project-search").addEventListener("input", renderBrowseList);
    $("#location-filter").addEventListener("change", renderBrowseList);
    $("#sort-order").addEventListener("change", () => {
        sortChosen = true;
        renderBrowseList();
    });

    for (const id of ["#min-score", "#rec-location", "#rec-seniority"]) {
        $(id).addEventListener("change", renderRecommended);
    }

    document.addEventListener("click", event => {
        const button = event.target.closest("[data-project-action]");
        if (!button) return;

        const project = openProjects.find(item => item.id === Number(button.dataset.id));
        if (project) showProject(project);
    });

    setupProfile();
}

function firstName() {
    const name = (state.me?.display_name || "").replace(/\(.*?\)/g, "").trim();
    return name.split(/\s+/)[0] || "there";
}

function greeting() {
    const hour = new Date().getHours();
    return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

// ==========================================
// PROFILE CHECKLIST (home and profile page)
// ==========================================

function profileSteps(me) {
    return [
        { done: Boolean(me.avatar), label: "Add a profile photo", href: "#/profile" },
        { done: me.skills.length >= 3, label: "Add at least 3 skills", href: "#/profile" },
        { done: me.has_resume, label: "Upload your resume", href: "#/profile" },
    ];
}

function checklistHTML(me, title = "Complete your profile") {
    const steps = profileSteps(me);
    const done = steps.filter(step => step.done).length;

    if (done === steps.length) {
        return `
            <div class="checklist">
                <p class="checklist-complete">${icon("check")}Your profile is complete</p>
                <p class="muted small">Keep your skills current to get the best recommendations.</p>
            </div>`;
    }

    return `
        <div class="checklist">
            <div class="checklist-head">
                <strong>${escapeHTML(title)}</strong>
                <span class="muted small">${done} of ${steps.length}</span>
            </div>
            <progress class="progress" max="${steps.length}" value="${done}"
                aria-label="${done} of ${steps.length} steps done"></progress>
            <ul>
                ${steps.map(step => step.done
                    ? `<li><span class="done"><span class="check-dot">${icon("check")}</span>${escapeHTML(step.label)}</span></li>`
                    : `<li><a href="${step.href}"><span class="check-dot"></span>${escapeHTML(step.label)}${icon("arrowRight")}</a></li>`
                ).join("")}
            </ul>
            <p class="muted small">A complete profile means better matches and helps managers get to know you.</p>
        </div>`;
}

// ==========================================
// HOME HERO
// ==========================================

function renderHero() {
    const hero = $("#home-hero");

    if (state.demo || !state.me) {
        hero.innerHTML = "";
        return;
    }

    const strong = [...matches.values()].filter(match => match.score >= 50).length;

    hero.innerHTML = `
        <div class="hero">
            <div class="hero-welcome">
                <div class="hero-greeting">
                    ${avatarHTML(state.me, "lg")}
                    <div>
                        <h1>${greeting()}, ${escapeHTML(firstName())}</h1>
                        <p>Find your next project and see how well you match.</p>
                    </div>
                </div>
                <div class="hero-stats">
                    <a href="#/browse" id="hero-open"><strong>${openProjects.length}</strong><span>Open projects</span></a>
                    <a href="#/recommended"><strong>${strong}</strong><span>Strong matches</span></a>
                    <a href="#/applications"><strong>${applicationCount}</strong><span>Your applications</span></a>
                </div>
            </div>
            <div class="card">${checklistHTML(state.me)}</div>
        </div>`;

    $("#hero-open").addEventListener("click", event => {
        event.preventDefault();
        $("#project-search").focus();
    });
}

// ==========================================
// BROWSE
// ==========================================

function projectCard(project, { showMatch = true } = {}) {
    const match = project.match || matches.get(project.id);
    const required = splitSkills(project.required_skills);

    return `
        <article class="project-card">
            <div class="project-head">
                ${monogram(project.client_project || project.title)}
                <div>
                    <h3>${escapeHTML(project.title)}</h3>
                    <p>${escapeHTML(project.client_project || "Internal project")}</p>
                </div>
                ${project.applied ? `<span class="pill success">${icon("check")}Applied</span>` : ""}
            </div>
            <div class="meta">
                <span>${icon("pin")}${escapeHTML(project.location || "Location TBD")}</span>
                ${project.seniority ? `<span>${icon("layers")}${escapeHTML(project.seniority)}</span>` : ""}
                ${project.start_date ? `<span>${icon("calendar")}Starts ${escapeHTML(formatDate(project.start_date))}</span>` : ""}
            </div>
            ${showMatch === "full" && match
                ? matchBlock(match, { legend: false })
                : `<div class="chips">${chips(required, "", 5)}</div>`}
            <div class="project-foot">
                ${showMatch === true && match ? matchPill(match) : "<span></span>"}
                <button type="button" class="button ${project.applied ? "" : "primary"} small"
                    data-project-action="open" data-id="${Number(project.id)}">
                    ${project.applied ? "View details" : "View and apply"}
                </button>
            </div>
        </article>
    `;
}

async function loadOpenProjects() {
    if (state.demo) {
        openProjects = state.sampleProjects;
        matches = new Map();
    } else {
        const wantsMatches = state.me.skills.length > 0 || state.me.has_resume;
        const [projects, ranked, applications] = await Promise.all([
            get("/projects"),
            wantsMatches ? get("/me/recommendations?min_score=0") : Promise.resolve([]),
            get("/me/applications"),
        ]);

        openProjects = projects;
        matches = new Map(ranked.map(project => [project.id, project.match]));
        applicationCount = applications.length;
    }

    const unique = values => [...new Set(values.filter(Boolean))].sort();
    fillSelect($("#location-filter"), unique(openProjects.map(p => p.location)), "All locations");
    fillSelect($("#rec-location"), unique(openProjects.map(p => p.location)), "All locations");
    fillSelect($("#rec-seniority"), unique(openProjects.map(p => p.seniority)), "All levels");

    const sort = $("#sort-order");
    sort.querySelector('[value="match"]').disabled = matches.size === 0;
    if (matches.size === 0 && sort.value === "match") sort.value = "newest";
    // Default to best match once there's something to match on.
    if (matches.size > 0 && !sortChosen) sort.value = "match";
}

export async function renderBrowse() {
    $("#project-list").innerHTML = skeletons(6);
    $("#browse-count").textContent = "";

    try {
        await loadOpenProjects();
        renderHero();
        renderBrowseList();
    } catch (error) {
        $("#project-list").innerHTML = emptyState("x", "Couldn't load projects", escapeHTML(error.message));
    }
}

function renderBrowseList() {
    const text = $("#project-search").value.trim().toLowerCase();
    const location = $("#location-filter").value;
    const sort = $("#sort-order").value;

    const filtered = openProjects.filter(project => {
        const haystack = [
            project.title, project.client_project, project.required_skills,
            project.nice_to_have_skills, project.description, project.location,
        ].join(" ").toLowerCase();

        return haystack.includes(text) && (!location || project.location === location);
    });

    const score = project => matches.get(project.id)?.score ?? -1;
    const sorters = {
        match: (a, b) => score(b) - score(a),
        newest: (a, b) => String(b.created_at).localeCompare(String(a.created_at)) || b.id - a.id,
        start: (a, b) => String(a.start_date || "9999").localeCompare(String(b.start_date || "9999")),
    };
    filtered.sort(sorters[sort] || sorters.newest);

    $("#browse-count").textContent = filtered.length === openProjects.length
        ? `${openProjects.length} open projects`
        : `Showing ${filtered.length} of ${openProjects.length} open projects`;

    $("#project-list").innerHTML = filtered.length
        ? filtered.map(project => projectCard(project)).join("")
        : emptyState("search", "No projects match your search",
            "Try a different keyword or clear the location filter.");
}

// ==========================================
// PROJECT DETAILS AND APPLYING
// ==========================================

function showProject(project) {
    const match = project.match || matches.get(project.id);
    const canApply = !state.demo && !project.applied;
    const nice = splitSkills(project.nice_to_have_skills);

    const body = openDrawer(project.title, `
        <div class="project-head">
            ${monogram(project.client_project || project.title)}
            <div>
                <h3>${escapeHTML(project.client_project || "Internal project")}</h3>
                <p>${escapeHTML(project.role_id || "")}</p>
            </div>
            ${project.applied ? `<span class="pill success">${icon("check")}Applied</span>` : ""}
        </div>

        <dl class="detail-grid">
            <div><dt>Location</dt><dd>${escapeHTML(project.location || "To be decided")}</dd></div>
            <div><dt>Seniority</dt><dd>${escapeHTML(project.seniority || "Any level")}</dd></div>
            <div><dt>Starts</dt><dd>${escapeHTML(formatDate(project.start_date) || "To be decided")}</dd></div>
            <div><dt>Status</dt><dd>${escapeHTML(project.status || "Open")}</dd></div>
        </dl>

        ${match ? `<section><h3>How you match</h3>${matchBlock(match)}</section>` : `
            <section>
                <h3>Required skills</h3>
                <div class="chips">${chips(splitSkills(project.required_skills))}</div>
            </section>`}

        ${nice.length && !match ? `
            <section><h3>Nice to have</h3><div class="chips">${chips(nice)}</div></section>` : ""}

        <section>
            <h3>About the project</h3>
            <p class="description">${escapeHTML(project.description || "No description provided.")}</p>
        </section>

        ${state.demo ? `<p class="banner">Demo mode: start the API to apply.</p>` : ""}
        ${project.applied ? `<p class="banner">You've applied. Track it under <a href="#/applications">Applications</a>.</p>` : ""}

        ${canApply ? `
            <form class="form apply-box" id="apply-form">
                <h3>Apply for this project</h3>
                <p class="muted small">The project managers will see your name, email,
                    skills (${state.me.skills.length ? escapeHTML(state.me.skills.join(", ")) : "none added yet"})
                    ${state.me.has_resume ? "and resume" : ""}.
                    ${state.me.skills.length ? "" : `<a href="#/profile">Add skills first</a> for a better match.`}</p>
                <label>Why are you interested? <span class="hint">Optional</span>
                    <textarea name="cover_letter" maxlength="5000" rows="4"
                        placeholder="A few sentences about why this project fits you"></textarea>
                </label>
                <label>${state.me.has_resume ? "Use a different resume" : "Attach a resume"} <span class="hint">Optional, PDF or DOCX</span>
                    <input type="file" name="resume" accept=".pdf,.docx">
                </label>
                <div class="actions">
                    <button type="submit" class="button primary">Submit application</button>
                </div>
                <p class="message" id="apply-message"></p>
            </form>` : ""}
    `);

    $("#apply-form", body)?.addEventListener("submit", event => submitApplication(event, project));
}

async function submitApplication(event, project) {
    event.preventDefault();

    const form = event.target;
    const button = form.querySelector("button[type=submit]");
    const data = new FormData(form);
    data.append("project_id", project.id);

    if (!data.get("resume")?.name) data.delete("resume");

    button.disabled = true;
    button.textContent = "Submitting...";

    try {
        const result = await postForm("/applications", data);
        project.applied = 1;
        applicationCount += 1;
        closeDrawer();
        toast(`Application sent for ${project.title}. Skill match: ${result.match_score}%.`);
        await state.refreshMe();
        renderHero();
        renderBrowseList();
        if (!$("[data-view=recommended]").classList.contains("hidden")) renderRecommended();
    } catch (error) {
        setMessage($("#apply-message"), error.message, "error");
        button.disabled = false;
        button.textContent = "Submit application";
    }
}

// ==========================================
// RECOMMENDED
// ==========================================

export async function renderRecommended() {
    const container = $("#recommended-list");

    if (state.me.skills.length === 0 && !state.me.has_resume) {
        container.innerHTML = emptyState("sparkle", "Tell us what you're good at",
            "Add a few skills or upload your resume and we'll rank open projects for you.",
            `<a class="button primary" href="#/profile">Set up my profile</a>`);
        return;
    }

    container.innerHTML = skeletons(6);

    try {
        if (openProjects.length === 0) await loadOpenProjects();

        const params = new URLSearchParams({
            min_score: $("#min-score").value,
            location: $("#rec-location").value,
            seniority: $("#rec-seniority").value,
        });

        const ranked = await get(`/me/recommendations?${params}`);

        for (const project of ranked) {
            matches.set(project.id, project.match);
            const cached = openProjects.find(item => item.id === project.id);
            if (cached) cached.applied = project.applied;
        }

        container.innerHTML = ranked.length
            ? ranked.map(project => projectCard(project, { showMatch: "full" })).join("")
            : emptyState("search", "No matches with these filters",
                "Try a lower minimum match, or add more skills to your profile.",
                `<a class="button" href="#/profile">Edit skills</a>`);

    } catch (error) {
        container.innerHTML = emptyState("x", "Couldn't load recommendations", escapeHTML(error.message));
    }
}

// ==========================================
// MY APPLICATIONS
// ==========================================

function timeline(status) {
    const value = String(status || "Submitted").toLowerCase();
    const reviewing = value === "under review";
    const decided = value === "accepted" || value === "rejected";

    const step = (label, classes) => `<div class="step ${classes}">${escapeHTML(label)}</div>`;

    return `
        <div class="timeline" aria-label="Status: ${escapeHTML(status)}">
            ${step("Submitted", `done ${value === "submitted" ? "current" : ""}`)}
            ${step("Under review", reviewing || decided ? `done ${reviewing ? "current" : ""}` : "")}
            ${value === "accepted" ? step("Accepted", "accepted")
                : value === "rejected" ? step("Not selected", "rejected")
                : step("Decision", "")}
        </div>`;
}

export async function renderApplications() {
    const container = $("#application-list");
    container.innerHTML = skeletons(3, "row");

    try {
        const applications = await get("/me/applications");
        applicationCount = applications.length;

        container.innerHTML = applications.length
            ? applications.map(application => `
                <article class="card application-card">
                    <div class="project-head">
                        ${monogram(application.client_project || application.project_title)}
                        <div>
                            <h3>${escapeHTML(application.project_title)}</h3>
                            <p>${escapeHTML(application.client_project || "")}
                                ${application.location ? ` &middot; ${escapeHTML(application.location)}` : ""}</p>
                            <p class="small">Applied ${escapeHTML(formatDate(application.submitted_at))}
                                &middot; #${Number(application.application_id)}</p>
                        </div>
                    </div>
                    <div>
                        <p>${statusPill(application.status)}</p>
                        ${timeline(application.status)}
                    </div>
                </article>`).join("")
            : emptyState("clipboard", "No applications yet",
                "When you apply to a project, you can follow its progress here.",
                `<a class="button primary" href="#/browse">Browse projects</a>`);

    } catch (error) {
        container.innerHTML = emptyState("x", "Couldn't load your applications", escapeHTML(error.message));
    }
}

// ==========================================
// PROFILE
// ==========================================

let draftSkills = [];

function skillsChanged() {
    const saved = state.me.skills.map(skill => skill.toLowerCase()).join("|");
    return draftSkills.map(skill => skill.toLowerCase()).join("|") !== saved;
}

export function renderProfile() {
    const me = state.me;

    $("#profile-avatar").innerHTML = avatarHTML(me, "xl");
    $("#profile-name").textContent = me.display_name;
    $("#profile-email").textContent = me.email;
    $("#profile-role").innerHTML = `<span class="pill">${escapeHTML(state.roleLabel(me.role))}</span>`;
    $("#photo-button-label").textContent = me.avatar ? "Change photo" : "Add photo";
    $("#remove-photo").classList.toggle("hidden", !me.avatar);
    $("#profile-checklist").innerHTML = checklistHTML(me);

    draftSkills = [...me.skills];
    renderSkillChips();
    setMessage("skills-message", "");
    $("#resume-suggestions").classList.add("hidden");

    const years = me.years_of_experience;
    $("#resume-summary").innerHTML = me.has_resume
        ? `Resume on file${years ? `, showing about <strong>${Number(years)} years</strong> of experience` : ""}. Upload a new one to replace it.`
        : "No resume yet. Uploading one improves your matches.";
}

function renderSkillChips() {
    $("#skill-chips").innerHTML = draftSkills.length
        ? draftSkills.map((skill, index) => `
            <span class="chip">${escapeHTML(skill)}
                <button type="button" data-remove-skill="${index}" aria-label="Remove ${escapeHTML(skill)}">${icon("x")}</button>
            </span>`).join("")
        : `<span class="muted">No skills yet. Add a few below, or upload your resume and we'll suggest some.</span>`;

    $("#skill-count").textContent = draftSkills.length ? `${draftSkills.length} skills` : "";

    const changed = skillsChanged();
    $("#save-skills").disabled = !changed;
    if (changed) setMessage("skills-message", "You have unsaved changes.", "error");
}

function addDraftSkills(skills) {
    const known = new Set(draftSkills.map(skill => skill.toLowerCase()));
    for (const skill of skills) {
        if (!known.has(skill.toLowerCase())) {
            draftSkills.push(skill);
            known.add(skill.toLowerCase());
        }
    }
    renderSkillChips();
}

async function saveSkills() {
    const button = $("#save-skills");
    button.disabled = true;

    try {
        state.me = await sendJSON("PUT", "/me", { skills: draftSkills });
        state.updateNav();
        renderProfile();
        toast("Skills saved. Your recommendations are updated.");
    } catch (error) {
        setMessage("skills-message", error.message, "error");
        button.disabled = false;
    }
}

async function uploadResume(file) {
    if (!file) return;

    const data = new FormData();
    data.append("file", file);
    setMessage("resume-message", `Reading ${file.name}...`);

    try {
        const result = await postForm("/me/resume", data);
        await state.refreshMe();
        renderProfile();

        setMessage("resume-message", result.new_skills.length
            ? `Resume saved. We found ${result.new_skills.length} skill(s) that aren't on your profile yet.`
            : "Resume saved. No new skills found.");

        if (result.new_skills.length) {
            $("#suggestion-list").innerHTML = result.new_skills.map(skill => `
                <label class="chip"><input type="checkbox" value="${escapeHTML(skill)}" checked>
                    ${escapeHTML(skill)}</label>`).join("");
            $("#resume-suggestions").classList.remove("hidden");
        }
    } catch (error) {
        setMessage("resume-message", error.message, "error");
    }
}

async function uploadPhoto(file) {
    if (!file) return;

    const data = new FormData();
    data.append("file", file);
    setMessage("avatar-message", "Uploading...");

    try {
        state.me = await request("/me/avatar", { method: "PUT", body: data });
        state.updateNav();
        renderProfile();
        setMessage("avatar-message", "");
        toast("Profile photo updated.");
    } catch (error) {
        setMessage("avatar-message", error.message, "error");
    }
}

function setupProfile() {
    $("#add-skill-form").addEventListener("submit", event => {
        event.preventDefault();
        addDraftSkills(splitSkills($("#new-skill").value));
        $("#new-skill").value = "";
    });

    $("#skill-chips").addEventListener("click", event => {
        const button = event.target.closest("[data-remove-skill]");
        if (!button) return;
        draftSkills.splice(Number(button.dataset.removeSkill), 1);
        renderSkillChips();
    });

    $("#save-skills").addEventListener("click", saveSkills);

    $("#resume-file").addEventListener("change", event => {
        uploadResume(event.target.files[0]);
        event.target.value = "";
    });

    const dropzone = $("#resume-dropzone");
    dropzone.addEventListener("dragover", event => {
        event.preventDefault();
        dropzone.classList.add("dragging");
    });
    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragging"));
    dropzone.addEventListener("drop", event => {
        event.preventDefault();
        dropzone.classList.remove("dragging");
        uploadResume(event.dataTransfer.files[0]);
    });

    $("#add-suggestions").addEventListener("click", async () => {
        const selected = [...document.querySelectorAll("#suggestion-list input:checked")]
            .map(input => input.value);
        addDraftSkills(selected);
        $("#resume-suggestions").classList.add("hidden");
        await saveSkills();
    });

    $("#avatar-file").addEventListener("change", event => {
        uploadPhoto(event.target.files[0]);
        event.target.value = "";
    });

    $("#remove-photo").addEventListener("click", async () => {
        try {
            state.me = await request("/me/avatar", { method: "DELETE" });
            state.updateNav();
            renderProfile();
            toast("Profile photo removed.");
        } catch (error) {
            setMessage("avatar-message", error.message, "error");
        }
    });
}
