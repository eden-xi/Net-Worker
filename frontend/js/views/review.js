// ==========================================
// REVIEW APPLICANTS: three panes, all tied to ONE listing
//   left:   listings + the applicants of the chosen listing (ranked by skill match)
//   centre: the applicant's document (PDF inline; Word shows its text)
//   right:  who they are, why they match, and the decision buttons
// Keyboard: J / K = next / previous applicant,  A = accept,  R = reject,  U = under review
// ==========================================

const Review = {
    root: null,                 // this page's box (see route() in app.js)
    listings: [],
    applicants: [],
    current: -1                 // index into applicants
};

// Find an element of the review page. Returns a throwaway element if you already left the page,
// so a late answer from the server never breaks anything.
function reviewPart(id) {
    return (Review.root && Review.root.querySelector(`#${id}`)) || document.createElement("div");
}

async function showReview(root) {
    Review.root = root;
    Review.applicants = [];
    Review.current = -1;
    root.innerHTML = `
        <div class="page-header">
            <h1>Review applicants</h1>
            <p class="muted">Pick a listing, then an applicant. Their document opens next to the listing it was sent to.</p>
        </div>
        <div class="review">
            <section class="pane" aria-label="Listings and applicants">
                <div class="pane-header">
                    <label class="search-box">${icon("search", 16)}
                        <input type="search" id="listing-search" placeholder="Find a listing" aria-label="Find a listing"></label>
                </div>
                <div class="pane-body" id="review-left">${skeletonCards(1)}</div>
            </section>
            <section class="pane" aria-label="Document">
                <div class="document" id="review-document">${emptyState("No applicant selected", "Choose a listing, then an applicant.")}</div>
            </section>
            <section class="pane" aria-label="Decision">
                <div class="decision" id="review-decision"><p class="kbd">Keys: <b>J</b> <b>K</b> move, <b>A</b> accept,
                    <b>R</b> reject, <b>U</b> under review</p></div>
            </section>
        </div>
    `;

    try {
        Review.listings = await apiFetch("/api/projects/manage");
    } catch (error) {
        reviewPart("review-left").innerHTML = emptyState("Could not load listings", error.message);
        return;
    }

    reviewPart("listing-search").addEventListener("input", drawLeftPane);
    reviewPart("review-left").addEventListener("click", onLeftPaneClick);
    document.addEventListener("keydown", onReviewKey);

    if (ManagerAdminDashboard.selectedProjectId) {
        await chooseListing(ManagerAdminDashboard.selectedProjectId);
    } else {
        drawLeftPane();
    }
}

// ---------- left pane ----------

function drawLeftPane() {
    const term = (reviewPart("listing-search").value || "").trim().toLowerCase();
    const selectedId = ManagerAdminDashboard.selectedProjectId;
    const listings = Review.listings.filter(item => item.title.toLowerCase().includes(term));
    const selectedTitle = (Review.listings.find(item => item.id === selectedId) || {}).title || "";

    const listingButtons = listings.map(item => `
        <button type="button" class="list-item ${item.id === selectedId ? "active" : ""}" data-listing-id="${Number(item.id)}">
            <span class="row"><span class="title">${escapeHTML(item.title)}</span>
                <span class="subtle numeric">${Number(item.applicant_count)}</span></span>
            <span class="row"><span class="subtle">${escapeHTML(item.role_id)}</span>${badge(item.status)}</span>
        </button>`).join("");

    const applicantButtons = Review.applicants.map((item, index) => `
        <button type="button" class="list-item ${index === Review.current ? "active" : ""}" data-applicant-index="${index}">
            <span class="row"><span class="title">${escapeHTML(item.name || item.email)}</span>${matchPill(item.match.score)}</span>
            <span class="row"><span class="subtle">${item.has_attachment ? "Resume attached" : "No resume"}</span>
                ${badge(item.status)}</span>
        </button>`).join("");

    reviewPart("review-left").innerHTML = `
        ${selectedId ? `<div class="pane-section">Applicants · ${escapeHTML(selectedTitle)}</div>
            ${applicantButtons || `<p class="subtle pane-note">No applicants yet.</p>`}` : ""}
        <div class="pane-section">Listings</div>
        ${listingButtons || `<p class="subtle pane-note">No listings match.</p>`}
    `;
}

async function onLeftPaneClick(event) {
    const listing = event.target.closest("[data-listing-id]");
    const applicant = event.target.closest("[data-applicant-index]");
    if (listing) await chooseListing(Number(listing.dataset.listingId));
    if (applicant) await chooseApplicant(Number(applicant.dataset.applicantIndex));
}

async function chooseListing(projectId) {
    ManagerAdminDashboard.selectedProjectId = projectId;
    const applicants = await apiFetch(`/api/projects/${projectId}/applications`);
    Review.applicants = applicants.sort((a, b) => b.match.score - a.match.score);      // best fit first
    Review.current = -1;
    drawLeftPane();
    if (Review.applicants.length) await chooseApplicant(0);
    else {
        reviewPart("review-document").innerHTML = emptyState("No applicants yet",
            "When someone applies, they appear on the left.");
        reviewPart("review-decision").innerHTML = "";
    }
}

// ---------- centre + right panes ----------

async function chooseApplicant(index) {
    if (index < 0 || index >= Review.applicants.length) return;
    Review.current = index;
    drawLeftPane();

    const applicationId = Review.applicants[index].application_id;
    const doc = await apiFetch(`/api/applications/${applicationId}/document`);

    reviewPart("review-document").innerHTML =
        doc.attachment_type === "pdf"
            ? `<iframe class="pdf-frame" src="${doc.attachment_url}#toolbar=0" title="Submitted PDF"></iframe>`
            : doc.attachment_type === "docx"
                ? `<pre class="doc-text">${escapeHTML(doc.resume_text || "No readable text found.")}</pre>`
                : emptyState("No document", "This applicant did not attach a resume.");

    reviewPart("review-decision").innerHTML = `
        <div class="metadata">
            <div id="decision-status">${badge(doc.status)}</div>
            <h2>${escapeHTML(doc.applicant_name || doc.applicant_email)}</h2>
            <p class="subtle">${escapeHTML(doc.applicant_email)} · applied ${formatDate(doc.submitted_at)}</p>
        </div>
        <div><h3>Fit for ${escapeHTML(doc.project.title)}</h3>${MatchBreakdown(doc.match)}</div>
        ${doc.cover_letter ? `<div><h3>Why this project</h3><p class="description">${escapeHTML(doc.cover_letter)}</p></div>` : ""}
        <div class="decision-buttons">
            <button type="button" class="button success" data-decide="Accepted">Accept</button>
            <button type="button" class="button danger" data-decide="Rejected">Reject</button>
            <button type="button" class="button secondary wide" data-decide="Under Review">Mark under review</button>
        </div>
        ${doc.attachment_type === "docx" ? `<a href="${doc.attachment_url}">Download the original Word file</a>` : ""}
        <p class="kbd">Keys: <b>J</b> <b>K</b> move, <b>A</b> accept, <b>R</b> reject, <b>U</b> under review</p>
    `;

    reviewPart("review-decision").querySelectorAll("[data-decide]").forEach(button =>
        button.addEventListener("click", () => decide(button.dataset.decide)));
}

async function decide(status) {
    const applicant = Review.applicants[Review.current];
    if (!applicant || applicant.status === status) return;

    const before = applicant.status;
    applicant.status = status;                                   // show it straight away...
    reviewPart("decision-status").innerHTML = badge(status);
    drawLeftPane();

    try {
        await sendJSON(`/api/applications/${applicant.application_id}/status`, "PATCH", { status });
        toast(`${applicant.name || applicant.email}: ${status}`);
    } catch (error) {
        applicant.status = before;                               // ...and undo it if the server refuses
        reviewPart("decision-status").innerHTML = badge(before);
        drawLeftPane();
        toast(error.message, "bad");
    }
}

// ---------- keyboard ----------

function onReviewKey(event) {
    if (!location.hash.startsWith("#/manager/review")) {
        document.removeEventListener("keydown", onReviewKey);    // left the page: stop listening
        return;
    }
    if (["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName) || event.ctrlKey || event.metaKey) return;

    const key = event.key.toLowerCase();
    if (key === "j") chooseApplicant(Review.current + 1);
    if (key === "k") chooseApplicant(Review.current - 1);
    if (key === "a") decide("Accepted");
    if (key === "r") decide("Rejected");
    if (key === "u") decide("Under Review");
}
