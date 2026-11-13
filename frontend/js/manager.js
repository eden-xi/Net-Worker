// ==========================================
// MANAGER / ADMIN DASHBOARD  (Option B: posting projects)
// Same shared feed + cards as the employee view, plus manager-only tabs.
// The server re-checks the manager role on every one of these calls.
// ==========================================

const ManagerAdminDashboard = {
    tabs: [
        { id: "browse", label: "All active listings" },
        { id: "manage", label: "Manage listings" },
        { id: "create", label: "Post a project" },
        { id: "review", label: "Applicants & documents" }
    ],

    // Remembered so "Applicants" on a card can jump straight to that listing.
    selectedProjectId: null,

    show(tabId, root, user) {
        if (tabId === "manage") return showManageListings(root);
        if (tabId === "create") return showCreateListing(root);
        if (tabId === "review") return showReview(root);
        return showManagerFeed(root);
    }
};

function applicantLabel(count) {
    return Number(count) === 1 ? "1 applicant" : `${Number(count)} applicants`;
}

function openApplicantsFor(projectId) {
    ManagerAdminDashboard.selectedProjectId = projectId;
    location.hash = "#/manager/review";
}

// ---------- Browse: the SAME feed component, different buttons ----------

function showManagerFeed(root) {
    renderJobFeed(root, {
        title: "All active listings",
        subtitle: "Exactly what employees see. Use Applicants to review submissions.",
        actionsFor: () => [
            { label: "View details", action: "details" },
            { label: "Applicants", action: "applicants", primary: true }
        ],
        onAction: (action, project) => {
            if (action === "details") openModal(ProjectMetadata(project));
            if (action === "applicants") openApplicantsFor(project.id);
        }
    });
}

// ---------- Manage listings: every status, change status, see applicant counts ----------

async function showManageListings(root) {
    root.innerHTML = `
        <section>
            <div class="page-header">
                <h1>Manage listings</h1>
                <p class="muted">Every listing in any status. Closed and Filled listings disappear from the feed.</p>
            </div>
            <p id="manage-status" class="status-text"></p>
            <div id="manage-table" class="table-wrap"><p class="muted">Loading...</p></div>
        </section>
    `;

    const box = document.getElementById("manage-table");
    let listings = [];

    try {
        listings = await apiFetch("/api/projects/manage");
    } catch (error) {
        box.innerHTML = `<p class="status-text error">${escapeHTML(error.message)}</p>`;
        return;
    }

    box.innerHTML = `
        <table>
            <thead><tr><th>Role ID</th><th>Title</th><th>Posted by</th><th>Applicants</th><th>Status</th><th></th></tr></thead>
            <tbody>
                ${listings.map(item => `
                    <tr>
                        <td>${escapeHTML(item.role_id)}</td>
                        <td>${escapeHTML(item.title)}</td>
                        <td>${escapeHTML(item.posted_by_name || "CSV import")}</td>
                        <td>${Number(item.applicant_count)}</td>
                        <td>
                            <select data-status-for="${Number(item.id)}">
                                ${["Open", "Closed", "Filled"].map(status => `
                                    <option ${status.toLowerCase() === String(item.status).trim().toLowerCase() ? "selected" : ""}>${status}</option>
                                `).join("")}
                            </select>
                        </td>
                        <td><button type="button" class="secondary-button" data-applicants-for="${Number(item.id)}">Applicants</button></td>
                    </tr>
                `).join("")}
            </tbody>
        </table>
    `;

    box.addEventListener("change", async event => {
        const projectId = event.target.dataset.statusFor;
        if (!projectId) return;

        try {
            await sendJSON(`/api/projects/${projectId}/status`, "PATCH", { status: event.target.value });
            setStatus(document.getElementById("manage-status"), `Listing ${projectId} is now ${event.target.value}.`);
        } catch (error) {
            setStatus(document.getElementById("manage-status"), error.message, true);
        }
    });

    box.addEventListener("click", event => {
        const projectId = event.target.dataset.applicantsFor;
        if (projectId) openApplicantsFor(Number(projectId));
    });
}

// ---------- Post a project ----------

function showCreateListing(root) {
    const field = (name, label, placeholder = "") =>
        `<label>${label} <input name="${name}" placeholder="${placeholder}"></label>`;

    root.innerHTML = `
        <section>
            <div class="page-header">
                <h1>Post a project</h1>
                <p class="muted">Published listings go straight into the shared feed for every employee.</p>
            </div>
            <form id="create-form" class="stacked-form card-form">
                <label>Title <input name="title" required placeholder="e.g. Teams bot developer"></label>
                ${field("client_project", "Client / project", "e.g. Finance - Expense bot")}
                ${field("required_skills", "Required skills", "Python; Azure; SQL")}
                ${field("nice_to_have_skills", "Nice-to-have skills", "Power BI")}
                <div class="form-row">
                    ${field("seniority", "Seniority", "Junior / Mid / Senior")}
                    ${field("location", "Location", "Remote / Hybrid / City")}
                    <label>Start date <input name="start_date" type="date"></label>
                </div>
                <label>Description <textarea name="description" rows="4"></textarea></label>
                <p id="create-status" class="status-text"></p>
                <button type="submit" class="primary-button">Publish listing</button>
            </form>
        </section>
    `;

    const form = document.getElementById("create-form");

    form.addEventListener("submit", async event => {
        event.preventDefault();
        const status = document.getElementById("create-status");

        try {
            const result = await sendJSON("/api/projects", "POST", Object.fromEntries(new FormData(form)));
            setStatus(status, `Published as ${result.role_id}. It is now in the shared feed.`);
            form.reset();
        } catch (error) {
            setStatus(status, error.message, true);
        }
    });
}

// ---------- Applicants & documents: list on the left, viewer pane on the right ----------

async function showReview(root) {
    root.innerHTML = `
        <section>
            <div class="page-header">
                <h1>Applicants & documents</h1>
                <p class="muted">Pick a listing, then an applicant. Their attachment opens beside the listing it was sent to.</p>
            </div>
            <select id="review-listing" class="wide-select"><option value="">Loading listings...</option></select>
            <div class="review-layout">
                <aside id="applicant-list" class="applicant-list"><p class="muted">No listing selected.</p></aside>
                <div id="document-viewer" class="document-viewer"><p class="muted">Select an applicant to open their documents.</p></div>
            </div>
        </section>
    `;

    const picker = document.getElementById("review-listing");
    let listings = [];

    try {
        listings = await apiFetch("/api/projects/manage");
    } catch (error) {
        picker.innerHTML = `<option>${escapeHTML(error.message)}</option>`;
        return;
    }

    picker.innerHTML = `<option value="">Choose a listing...</option>` + listings.map(item => `
        <option value="${Number(item.id)}">${escapeHTML(item.title)} (${applicantLabel(item.applicant_count)}, ${escapeHTML(item.status)})</option>
    `).join("");

    picker.addEventListener("change", () => {
        ManagerAdminDashboard.selectedProjectId = Number(picker.value) || null;
        loadApplicants(ManagerAdminDashboard.selectedProjectId);
    });

    if (ManagerAdminDashboard.selectedProjectId) {
        picker.value = ManagerAdminDashboard.selectedProjectId;
        loadApplicants(ManagerAdminDashboard.selectedProjectId);
    }
}

async function loadApplicants(projectId) {
    const list = document.getElementById("applicant-list");
    document.getElementById("document-viewer").innerHTML = `<p class="muted">Select an applicant to open their documents.</p>`;

    if (!projectId) {
        list.innerHTML = `<p class="muted">No listing selected.</p>`;
        return;
    }

    try {
        // Manager-only: the server refuses this for employees.
        const applicants = await apiFetch(`/api/projects/${projectId}/applications`);

        list.innerHTML = applicants.length ? applicants.map(item => `
            <button type="button" class="applicant" data-application-id="${Number(item.application_id)}">
                <strong>${escapeHTML(item.name)}</strong>
                <span class="muted">${escapeHTML(item.email)}</span>
                <span class="pill">${escapeHTML(item.status)}</span>
            </button>
        `).join("") : `<p class="muted">No applicants yet.</p>`;

        list.onclick = event => {
            const button = event.target.closest("[data-application-id]");
            if (!button) return;

            list.querySelectorAll(".applicant").forEach(item => item.classList.remove("active"));
            button.classList.add("active");
            openDocument(Number(button.dataset.applicationId));
        };
    } catch (error) {
        list.innerHTML = `<p class="status-text error">${escapeHTML(error.message)}</p>`;
    }
}

function attachmentHTML(doc) {
    if (doc.attachment_type === "pdf") {
        return `<iframe class="pdf-frame" src="${doc.attachment_url}" title="Submitted PDF"></iframe>`;
    }

    if (doc.attachment_type === "docx") {
        // Browsers can't draw Word files, so show the text the backend already extracted.
        return `
            <p class="muted">Word document: showing extracted text. <a href="${doc.attachment_url}">Download original</a></p>
            <pre class="doc-text">${escapeHTML(doc.resume_text || "No readable text found.")}</pre>
        `;
    }

    return `<p class="muted">No attachment was submitted with this application.</p>`;
}

async function openDocument(applicationId) {
    const viewer = document.getElementById("document-viewer");
    viewer.innerHTML = `<p class="muted">Opening...</p>`;

    try {
        const doc = await apiFetch(`/api/applications/${applicationId}/document`);

        viewer.innerHTML = `
            <div class="viewer-grid">
                <div class="viewer-meta">
                    ${ProjectMetadata(doc.project)}
                    <div class="metadata">
                        <h3>Applicant</h3>
                        <dl>
                            <dt>Name</dt><dd>${escapeHTML(doc.applicant_name)}</dd>
                            <dt>Email</dt><dd>${escapeHTML(doc.applicant_email)}</dd>
                            <dt>Skills</dt><dd>${escapeHTML(doc.applicant_skills || "-")}</dd>
                            <dt>Submitted</dt><dd>${escapeHTML(new Date(doc.submitted_at).toLocaleString())}</dd>
                        </dl>
                        ${doc.cover_letter ? `<p class="description">${escapeHTML(doc.cover_letter)}</p>` : ""}
                        <label>Application status
                            <select id="application-status-select">
                                ${["Submitted", "Under Review", "Accepted", "Rejected"].map(status => `
                                    <option ${status === doc.status ? "selected" : ""}>${status}</option>
                                `).join("")}
                            </select>
                        </label>
                        <p id="application-status-note" class="status-text"></p>
                    </div>
                </div>
                <div class="viewer-document">${attachmentHTML(doc)}</div>
            </div>
        `;

        document.getElementById("application-status-select").addEventListener("change", async event => {
            const note = document.getElementById("application-status-note");

            try {
                await sendJSON(`/api/applications/${applicationId}/status`, "PATCH", { status: event.target.value });
                setStatus(note, `Saved: ${event.target.value}.`);

                // Keep the pill in the applicant list in step with the change.
                const pill = document.querySelector(`[data-application-id="${applicationId}"] .pill`);
                if (pill) pill.textContent = event.target.value;
            } catch (error) {
                setStatus(note, error.message, true);
            }
        });
    } catch (error) {
        viewer.innerHTML = `<p class="status-text error">${escapeHTML(error.message)}</p>`;
    }
}
