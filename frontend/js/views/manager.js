// ==========================================
// MANAGER / ADMIN DASHBOARD  (Option B: posting projects)
// Same shared feed + cards as the employee view, plus manager-only pages.
// The server re-checks the manager role on every one of these calls.
//   Overview -> views/activity.js      Review applicants -> views/review.js
// ==========================================

const ManagerAdminDashboard = {
    tabs: [
        { id: "overview", label: "Overview", icon: "activity" },
        { id: "browse", label: "All listings", icon: "search" },
        { id: "manage", label: "Manage listings", icon: "list" },
        { id: "create", label: "Post a project", icon: "plus" },
        { id: "review", label: "Review applicants", icon: "review" }
    ],

    // Remembered so "Review applicants" on a listing can jump straight to it.
    selectedProjectId: null,

    show(tabId, root) {
        if (tabId === "browse") return showManagerFeed(root);
        if (tabId === "manage") return showManageListings(root);
        if (tabId === "create") return showCreateListing(root);
        if (tabId === "review") return showReview(root);
        return showOverview(root);
    }
};

function openApplicantsFor(projectId) {
    ManagerAdminDashboard.selectedProjectId = projectId;
    closeModal();
    location.hash = "#/manager/review";
}

function Pipeline(listing) {
    return `<div class="pipeline">
        <span class="badge badge-neutral">${Number(listing.new_count)} new</span>
        <span class="badge badge-warn">${Number(listing.review_count)} in review</span>
        <span class="badge badge-ok">${Number(listing.accepted_count)} accepted</span>
    </div>`;
}

// ---------- All listings: the SAME feed component, a different drawer ----------

function showManagerFeed(root) {
    renderJobFeed(root, {
        title: "All listings",
        subtitle: "Exactly what employees see. Open a listing to review who applied.",
        onOpen: project => {
            openModal(`
                ${ProjectMetadata(project)}
                <button type="button" class="button primary" id="drawer-review">Review applicants</button>
            `);
            document.getElementById("drawer-review").addEventListener("click", () => openApplicantsFor(project.id));
        }
    });
}

// ---------- Manage listings: every status, pipeline per listing ----------

async function showManageListings(root) {
    root.innerHTML = `
        <section>
            <div class="page-header">
                <h1>Manage listings</h1>
                <p class="muted">Every listing in any status. Closed and Filled listings leave the employee feed.</p>
            </div>
            <div id="manage-table" class="table-wrap"><div class="empty skeleton"><div class="skeleton-line wide"></div>
                <div class="skeleton-line"></div><div class="skeleton-line mid"></div></div></div>
        </section>
    `;

    const box = root.querySelector("#manage-table");
    let listings;

    try {
        listings = await apiFetch("/api/projects/manage");
    } catch (error) {
        box.innerHTML = emptyState("Could not load listings", error.message);
        return;
    }

    box.innerHTML = `
        <table>
            <thead><tr><th>Listing</th><th>Posted by</th><th>Pipeline</th><th>Status</th><th></th></tr></thead>
            <tbody>
                ${listings.map(item => `
                    <tr>
                        <td><strong>${escapeHTML(item.title)}</strong><div class="subtle">${escapeHTML(item.role_id)}</div></td>
                        <td>${escapeHTML(item.posted_by_name || "CSV import")}</td>
                        <td>${Pipeline(item)}</td>
                        <td>
                            <select data-status-for="${Number(item.id)}" aria-label="Status of ${escapeHTML(item.title)}">
                                ${["Open", "Closed", "Filled"].map(status =>
                                    `<option ${status === item.status ? "selected" : ""}>${status}</option>`).join("")}
                            </select>
                        </td>
                        <td><button type="button" class="button secondary small" data-review-id="${Number(item.id)}">
                            Review (${Number(item.applicant_count)})</button></td>
                    </tr>
                `).join("")}
            </tbody>
        </table>
    `;

    box.addEventListener("change", async event => {
        const projectId = event.target.dataset.statusFor;
        if (!projectId) return;
        try {
            const updated = await sendJSON(`/api/projects/${projectId}/status`, "PATCH", { status: event.target.value });
            toast(`${updated.title} is now ${updated.status}.`);
        } catch (error) {
            toast(error.message, "bad");
        }
    });

    box.addEventListener("click", event => {
        const projectId = event.target.dataset.reviewId;
        if (projectId) openApplicantsFor(Number(projectId));
    });
}

// ---------- Post a project ----------

function showCreateListing(root) {
    const field = (name, label, placeholder = "") =>
        `<label>${label} <input name="${name}" placeholder="${placeholder}"></label>`;

    root.innerHTML = `
        <section class="narrow">
            <div class="page-header">
                <h1>Post a project</h1>
                <p class="muted">Published listings go straight into the shared feed for every employee.</p>
            </div>
            <form id="create-form" class="stacked-form">
                <label>Title <input name="title" required maxlength="120" placeholder="e.g. Teams bot developer"></label>
                ${field("client_project", "Client / project", "e.g. Finance - Expense bot")}
                ${field("required_skills", "Required skills (used for matching)", "Python; Azure; SQL")}
                ${field("nice_to_have_skills", "Nice-to-have skills", "Power BI")}
                <div class="form-row">
                    ${field("seniority", "Seniority", "Junior / Mid / Senior")}
                    ${field("location", "Location", "Remote / Hybrid / City")}
                    <label>Start date <input name="start_date" type="date"></label>
                </div>
                <label>Description <textarea name="description" rows="5"></textarea></label>
                <div><button type="submit" class="button primary">Publish listing</button></div>
            </form>
        </section>
    `;

    const form = root.querySelector("#create-form");

    form.addEventListener("submit", async event => {
        event.preventDefault();
        try {
            const created = await sendJSON("/api/projects", "POST", Object.fromEntries(new FormData(form)));
            toast(`Published ${created.title} (${created.role_id}). It is now in the shared feed.`);
            form.reset();
        } catch (error) {
            toast(error.message, "bad");
        }
    });
}
