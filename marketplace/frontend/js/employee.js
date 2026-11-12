// ==========================================
// EMPLOYEE DASHBOARD  (Option A: seeking projects)
// Built from the shared components in components.js.
// ==========================================

const EmployeeDashboard = {
    tabs: [
        { id: "browse", label: "Browse projects" },
        { id: "applications", label: "My applications" }
    ],

    // Called by the router in app.js whenever the tab changes.
    show(tabId, root, user) {
        if (tabId === "applications") {
            showMyApplications(root, user);
        } else {
            showEmployeeFeed(root, user);
        }
    }
};

// ---------- Browse: the shared job feed with employee buttons ----------

function showEmployeeFeed(root, user) {
    renderJobFeed(root, {
        title: "Open projects",
        subtitle: "Every active listing across the platform. Find one that fits and apply.",
        actionsFor: () => [
            { label: "View details", action: "details" },
            { label: "Apply", action: "apply", primary: true }
        ],
        onAction: (action, project) => {
            if (action === "details") showEmployeeDetails(project, user);
            if (action === "apply") showApplyForm(project, user);
        }
    });
}

function showEmployeeDetails(project, user) {
    openModal(`
        ${ProjectMetadata(project)}
        <button type="button" class="primary-button" id="details-apply">Apply to this project</button>
    `);

    document.getElementById("details-apply")
        .addEventListener("click", () => showApplyForm(project, user));
}

// ---------- Apply: sends the form + resume to the team's existing endpoint ----------

function showApplyForm(project, user) {
    openModal(`
        <h2>Apply: ${escapeHTML(project.title)}</h2>
        <form id="apply-form" class="stacked-form">
            <label>Full name <input name="name" required value="${escapeHTML(user.name)}"></label>
            <label>Email (from your login) <input name="email" readonly value="${escapeHTML(user.email)}"></label>
            <label>Your skills <textarea name="skills" rows="2" placeholder="Python, SQL, Azure..."></textarea></label>
            <label>Why this project? <textarea name="cover_letter" rows="4"></textarea></label>
            <label>Resume (PDF or DOCX, max 5 MB) <input name="resume" type="file" accept=".pdf,.docx"></label>
            <p id="apply-status" class="status-text"></p>
            <button type="submit" class="primary-button">Submit application</button>
        </form>
    `);

    const form = document.getElementById("apply-form");

    form.addEventListener("submit", async event => {
        event.preventDefault();

        const status = document.getElementById("apply-status");
        const formData = new FormData(form);
        formData.append("project_id", project.id);

        // An empty file box would be sent as a nameless file; leave it out instead.
        if (!form.resume.files.length) formData.delete("resume");

        try {
            setStatus(status, "Submitting...");
            const result = await apiFetch("/api/applications/submit-with-resume", {
                method: "POST",
                body: formData
            });
            setStatus(status, `${result.message} Track it under "My applications".`);
            form.querySelector("button[type=submit]").disabled = true;
        } catch (error) {
            setStatus(status, error.message, true);
        }
    });
}

// ---------- My applications ----------

async function showMyApplications(root, user) {
    root.innerHTML = `
        <section>
            <div class="page-header">
                <h1>My applications</h1>
                <p class="muted">Everything you have applied to as ${escapeHTML(user.email)}.</p>
            </div>
            <div id="my-applications" class="table-wrap"><p class="muted">Loading...</p></div>
        </section>
    `;

    const box = document.getElementById("my-applications");

    try {
        const result = await apiFetch(
            `/api/applications/my-applications?email=${encodeURIComponent(user.email)}`
        );

        if (result.applications.length === 0) {
            box.innerHTML = `<p class="muted">No applications yet. Head to "Browse projects" to find one.</p>`;
            return;
        }

        box.innerHTML = `
            <table>
                <thead><tr><th>Project</th><th>Client</th><th>Location</th><th>Status</th><th>Submitted</th></tr></thead>
                <tbody>
                    ${result.applications.map(item => `
                        <tr>
                            <td>${escapeHTML(item.project_title)}</td>
                            <td>${escapeHTML(item.client_project)}</td>
                            <td>${escapeHTML(item.location)}</td>
                            <td><span class="pill">${escapeHTML(item.status)}</span></td>
                            <td>${escapeHTML(item.submitted_at)}</td>
                        </tr>
                    `).join("")}
                </tbody>
            </table>
        `;
    } catch (error) {
        box.innerHTML = `<p class="status-text error">${escapeHTML(error.message)}</p>`;
    }
}
