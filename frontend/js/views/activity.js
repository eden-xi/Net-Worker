// ==========================================
// MANAGER OVERVIEW: headline numbers + the live activity feed.
//
// "Live" = the page asks GET /api/insights/activity?after_id=<newest id seen> every 5 s.
// Usually the answer is an empty list. New lines slide in highlighted.
// ==========================================

const ACTIVITY_ICON = {
    listing_posted: "plus",
    listing_status: "list",
    application_submitted: "inbox",
    application_status: "review"
};

function ActivityItem(event, fresh = false) {
    return `
        <li class="activity-item ${fresh ? "fresh" : ""}">
            <span class="role-icon">${icon(ACTIVITY_ICON[event.kind] || "activity", 16)}</span>
            <span>${escapeHTML(event.message)}</span>
            <span class="when subtle" data-time="${escapeHTML(event.created_at)}">${timeAgo(event.created_at)}</span>
        </li>
    `;
}

function Tile(value, label) {
    return `<div class="tile"><div class="value">${Number(value)}</div><div class="label">${escapeHTML(label)}</div></div>`;
}

async function showOverview(root) {
    root.innerHTML = `
        <section>
            <div class="page-header">
                <h1>Overview</h1>
                <p class="muted">What is happening across your listings right now.</p>
            </div>
            <div id="tiles" class="tiles">${Tile(0, "Loading...")}</div>
            <div class="panel">
                <div class="panel-header"><h3>Activity</h3><span class="live-dot">Live</span></div>
                <ul id="activity-list" class="activity-list"></ul>
            </div>
        </section>
    `;

    const list = root.querySelector("#activity-list");
    let newestId = 0;

    async function drawTiles() {
        const listings = await apiFetch("/api/projects/manage");
        const sum = key => listings.reduce((total, item) => total + Number(item[key] || 0), 0);
        root.querySelector("#tiles").innerHTML =
            Tile(listings.filter(item => item.status === "Open").length, "Open listings") +
            Tile(sum("applicant_count"), "Applications") +
            Tile(sum("new_count") + sum("review_count"), "Waiting for a decision") +
            Tile(sum("accepted_count"), "Accepted");
    }

    async function poll(first = false) {
        const events = await apiFetch(`/api/insights/activity?after_id=${newestId}`);
        if (events.length) {
            list.querySelector(".placeholder")?.remove();
            newestId = events[0].id;
            list.insertAdjacentHTML("afterbegin", events.map(event => ActivityItem(event, !first)).join(""));
            if (!first) drawTiles();                     // something changed: refresh the numbers too
            setTimeout(() => list.querySelectorAll(".fresh").forEach(item => item.classList.remove("fresh")), 2500);
        }
        list.querySelectorAll("[data-time]").forEach(cell => { cell.textContent = timeAgo(cell.dataset.time); });
        if (!list.children.length) {
            list.innerHTML = `<li class="activity-item subtle placeholder">No activity yet. Post a listing to get started.</li>`;
        }
    }

    try {
        await Promise.all([drawTiles(), poll(true)]);
    } catch (error) {
        list.innerHTML = `<li class="activity-item">${escapeHTML(error.message)}</li>`;
        return;
    }

    startPolling(() => poll().catch(() => {}), 5000, root);
}
