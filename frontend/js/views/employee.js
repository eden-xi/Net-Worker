// ==========================================
// EMPLOYEE DASHBOARD  (Option A: seeking projects)
// Built from the shared components in core/components.js.
// ==========================================

const EmployeeDashboard = {
    tabs: [
        { id: "browse", label: "Find projects", icon: "search" },
        { id: "applications", label: "My applications", icon: "inbox" },
        { id: "profile", label: "My skills", icon: "user" }
    ],

    // Called by the router in app.js whenever the page changes.
    show(tabId, root, user) {
        if (tabId === "applications") return showMyApplications(root);
        if (tabId === "profile") return showProfile(root);
        return showEmployeeFeed(root, user);
    }
};

// ---------- Find projects: the shared feed, with "% match" ----------

async function showEmployeeFeed(root, user) {
    let profile = { skills: "", resume_on_file: false };
    try {
        profile = await apiFetch("/api/applications/profile");
    } catch (error) {
        /* the feed still works without a profile */
    }

    const noSkills = !profile.skills && !profile.resume_on_file;

    renderJobFeed(root, {
        title: "Find projects",
        subtitle: "Every open listing across the company, ranked by how well it fits your skills.",
        banner: noSkills ? `<div class="banner"><span>Add your skills to see how well each project fits you.</span>
            <a class="button secondary small" href="#/employee/profile">Add skills</a></div>` : "",
        loadMatches: () => apiFetch("/api/insights/matches"),
        onOpen: (project, match) => showProjectDrawer(project, match, user)
    });
}

function showProjectDrawer(project, match, user) {
    openModal(`
        ${ProjectMetadata(project)}
        ${match && match.score > 0 ? `<div><h3>Your fit</h3>${MatchBreakdown(match)}</div>` : ""}
        <button type="button" class="button primary" id="drawer-apply">Apply to this project</button>
    `);
    document.getElementById("drawer-apply").addEventListener("click", () => showApplyForm(project, user));
}

// ---------- Apply: POST /api/applications (who you are comes from your sign-in) ----------

async function showApplyForm(project, user) {
    let skills = "";
    try {
        skills = (await apiFetch("/api/applications/profile")).skills;
    } catch (error) {
        skills = "";
    }

    openModal(`
        <div class="page-header">
            <h2>Apply: ${escapeHTML(project.title)}</h2>
            <p class="muted">Applying as <strong>${escapeHTML(user.name)}</strong> (${escapeHTML(user.email)}), from your sign-in.</p>
        </div>
        <form id="apply-form" class="stacked-form">
            <label>Your skills <textarea name="skills" rows="2" placeholder="Python, SQL, Azure...">${escapeHTML(skills)}</textarea></label>
            <label>Why this project? <textarea name="cover_letter" rows="5"></textarea></label>
            <label>Resume (PDF or DOCX, max 5 MB) <input name="resume" type="file" accept=".pdf,.docx"></label>
            <p id="apply-status" class="status-text" role="status"></p>
            <button type="submit" class="button primary">Submit application</button>
        </form>
    `);

    const form = document.getElementById("apply-form");

    form.addEventListener("submit", async event => {
        event.preventDefault();
        const button = form.querySelector("button[type=submit]");
        const formData = new FormData(form);
        formData.append("project_id", project.id);
        if (!form.resume.files.length) formData.delete("resume");    // no empty file part

        button.disabled = true;
        setStatus(document.getElementById("apply-status"), "Sending...");

        try {
            await sendForm("/api/applications", formData);
            setStatus(document.getElementById("apply-status"), "Application submitted successfully.");
            toast(`Applied to ${project.title}. Track it under My applications.`);
            setTimeout(closeModal, 900);
        } catch (error) {
            setStatus(document.getElementById("apply-status"), error.message, true);
            button.disabled = false;
        }
    });
}

// ---------- My applications: a live tracker (refreshes every 10 s) ----------

async function showMyApplications(root) {
    root.innerHTML = `
        <section>
            <div class="page-header">
                <h1>My applications</h1>
                <p class="muted">Where each application stands. This page updates by itself when a manager decides.</p>
            </div>
            <div id="tracker" class="tracker-list">${skeletonCards(2)}</div>
        </section>
    `;

    const box = root.querySelector("#tracker");
    const lastStatus = new Map();          // application id -> status, to spot changes between refreshes

    async function refresh() {
        let applications;
        try {
            applications = await apiFetch("/api/applications/mine");
        } catch (error) {
            box.innerHTML = emptyState("Could not load your applications", error.message);
            return;
        }

        applications.forEach(item => {
            const before = lastStatus.get(item.application_id);
            if (before && before !== item.status) toast(`${item.project_title}: now ${item.status}`);
            lastStatus.set(item.application_id, item.status);
        });

        box.innerHTML = applications.length ? applications.map(item => `
            <article class="tracker-card" data-application-id="${Number(item.application_id)}">
                <div class="tracker-head">
                    <div>
                        <h3>${escapeHTML(item.project_title)}</h3>
                        <p class="subtle">${escapeHTML(item.client_project || "")} · applied ${formatDate(item.submitted_at)}</p>
                    </div>
                    ${badge(item.status)}
                </div>
                ${Stepper(item)}
            </article>
        `).join("") : emptyState("No applications yet", "Find a project that fits and apply.",
            `<a class="button primary small" href="#/employee/browse">Find projects</a>`);
    }

    await refresh();
    startPolling(refresh, 10000, root);
}

// ---------- My skills: powers "% match" ----------

async function showProfile(root) {
    root.innerHTML = `
        <section class="narrow">
            <div class="page-header">
                <h1>My skills</h1>
                <p class="muted">Used to rank listings by fit. Your resume text counts too, once you've applied with one.</p>
            </div>
            <form id="profile-form" class="stacked-form">
                <!-- Disabled until the saved skills arrive, so nothing typed early gets overwritten. -->
                <fieldset id="profile-fields" class="stacked-form" disabled>
                    <label>Skills, separated by commas
                        <textarea name="skills" rows="3" placeholder="Loading your skills..."></textarea></label>
                    <div id="skill-preview"></div>
                    <p id="resume-note" class="subtle"></p>
                    <div><button type="submit" class="button primary">Save skills</button></div>
                </fieldset>
            </form>
        </section>
    `;

    const form = root.querySelector("#profile-form");
    const preview = () => { root.querySelector("#skill-preview").innerHTML = SkillChips(form.skills.value, [], 20); };

    try {
        const profile = await apiFetch("/api/applications/profile");
        form.skills.value = profile.skills;
        form.skills.placeholder = "Python, FastAPI, SQL, Power BI";
        root.querySelector("#profile-fields").disabled = false;
        root.querySelector("#resume-note").textContent = profile.resume_on_file
            ? "A resume is on file and its text is used for matching."
            : "No resume on file yet. It is added the first time you apply with one.";
        preview();
    } catch (error) {
        toast(error.message, "bad");
    }

    form.skills.addEventListener("input", preview);
    form.addEventListener("submit", async event => {
        event.preventDefault();
        try {
            await sendJSON("/api/applications/profile", "PUT", { skills: form.skills.value });
            toast("Skills saved. Your matches are updated.");
        } catch (error) {
            toast(error.message, "bad");
        }
    });
}
