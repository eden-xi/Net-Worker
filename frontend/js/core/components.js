// ==========================================
// SHARED COMPONENTS: the same job feed, cards and details for BOTH dashboards.
// A component is just a function that returns HTML or fills a container.
// ==========================================

// ---------- skill chips (matched ones turn green) ----------

function SkillChips(skillsText, matched = [], limit = 4) {
    const skills = splitSkills(skillsText);
    const matchedSet = new Set(matched.map(skill => skill.toLowerCase()));
    const shown = skills.slice(0, limit).map(skill =>
        `<span class="chip ${matchedSet.has(skill.toLowerCase()) ? "matched" : ""}">${escapeHTML(skill)}</span>`);

    if (skills.length > limit) shown.push(`<span class="chip more">+${skills.length - limit}</span>`);
    return `<div class="chips">${shown.join("")}</div>`;
}

// ---------- listing card: the whole card is clickable ----------

function ListingCard(project, match) {
    return `
        <article class="listing-card" tabindex="0" data-open-id="${Number(project.id)}">
            <div class="card-top">
                ${badge(project.status || "Open")}
                ${match ? matchPill(match.score) : ""}
            </div>
            <div>
                <h3>${escapeHTML(project.title)}</h3>
                <p class="muted">${escapeHTML(project.client_project || "Internal project")}</p>
            </div>
            ${SkillChips(project.required_skills, match ? match.matched : [])}
            <div class="card-footer">
                <span>${escapeHTML(project.location || "Location TBD")}</span>
                <span class="dot">${escapeHTML(project.seniority || "Any level")}</span>
                ${project.start_date ? `<span class="dot">Starts ${escapeHTML(project.start_date)}</span>` : ""}
            </div>
        </article>
    `;
}

// ---------- listing details (drawer AND the manager's review screen) ----------

function ProjectMetadata(project) {
    const rows = [
        ["Role ID", project.role_id],
        ["Client / project", project.client_project],
        ["Required skills", project.required_skills],
        ["Nice to have", project.nice_to_have_skills],
        ["Seniority", project.seniority],
        ["Location", project.location],
        ["Start date", project.start_date]
    ];

    return `
        <div class="metadata">
            <div>${badge(project.status || "Open")}</div>
            <h2>${escapeHTML(project.title)}</h2>
            <dl>
                ${rows.filter(([, value]) => value).map(([label, value]) =>
                    `<dt>${escapeHTML(label)}</dt><dd>${escapeHTML(value)}</dd>`).join("")}
            </dl>
            ${project.description ? `<p class="description">${escapeHTML(project.description)}</p>` : ""}
        </div>
    `;
}

// ---------- match breakdown: why this % ----------

function MatchBreakdown(match) {
    if (!match) return "";
    const chips = (list, kind) => list.map(skill => `<span class="chip ${kind}">${escapeHTML(skill)}</span>`).join("");

    return `
        <div class="metadata">
            <div>${matchPill(match.score)}</div>
            <div class="meter" aria-hidden="true"><span style="width:${Number(match.score)}%"></span></div>
            <div class="chips">${chips(match.matched, "matched")}${chips(match.missing, "missing")}</div>
            ${match.bonus.length ? `<p class="subtle">Also has nice-to-have: ${escapeHTML(match.bonus.join(", "))}</p>` : ""}
        </div>
    `;
}

// ---------- job feed: search + location + sort + grid of cards ----------

// options:
//   title, subtitle      heading text
//   loadMatches()        optional: returns [{project_id, score, matched, ...}] to show "% match"
//   banner               optional HTML shown above the grid
//   onOpen(project, match)  what happens when a card is clicked (differs per role)
async function renderJobFeed(container, options) {
    container.innerHTML = `
        <section class="feed">
            <div class="page-header">
                <h1>${escapeHTML(options.title)}</h1>
                <p class="muted">${escapeHTML(options.subtitle || "")}</p>
            </div>
            ${options.banner || ""}
            <div class="toolbar">
                <label class="search-box">${icon("search", 16)}
                    <input type="search" class="feed-search" placeholder="Search title, skill or client" aria-label="Search listings">
                </label>
                <select class="feed-location" aria-label="Location"><option value="">All locations</option></select>
                <select class="feed-sort" aria-label="Sort">
                    ${options.loadMatches ? `<option value="match">Best match</option>` : ""}
                    <option value="newest">Newest</option>
                </select>
                <span class="feed-count subtle count numeric"></span>
            </div>
            <div class="listing-grid">${skeletonCards()}</div>
        </section>
    `;

    const feed = container.querySelector(".feed");
    const grid = feed.querySelector(".listing-grid");
    const [search, location, sort, count] = [".feed-search", ".feed-location", ".feed-sort", ".feed-count"]
        .map(selector => feed.querySelector(selector));

    let projects = [];
    const matches = new Map();

    try {
        const [projectList, matchList] = await Promise.all([
            apiFetch("/api/projects"),
            options.loadMatches ? options.loadMatches() : Promise.resolve([])
        ]);
        projects = projectList;
        matchList.forEach(match => matches.set(match.project_id, match));
    } catch (error) {
        grid.innerHTML = emptyState("Could not load listings", error.message);
        return;
    }

    const places = [...new Set(projects.map(project => project.location).filter(Boolean))].sort();
    location.innerHTML += places.map(place => `<option>${escapeHTML(place)}</option>`).join("");

    function draw() {
        const term = search.value.trim().toLowerCase();
        let visible = projects.filter(project => {
            const text = [project.title, project.client_project, project.required_skills, project.description]
                .join(" ").toLowerCase();
            return text.includes(term) && (!location.value || project.location === location.value);
        });

        if (sort.value === "match") {
            visible = [...visible].sort((a, b) => (matches.get(b.id)?.score || 0) - (matches.get(a.id)?.score || 0));
        }

        count.textContent = `${visible.length} of ${projects.length} open listings`;
        grid.innerHTML = visible.length
            ? visible.map(project => ListingCard(project, matches.get(project.id))).join("")
            : emptyState("No listings match", "Try a different search or location.");
    }

    [search, location, sort].forEach(control => control.addEventListener(control === search ? "input" : "change", draw));

    function open(event) {
        const card = event.target.closest("[data-open-id]");
        if (!card) return;
        const project = projects.find(item => item.id === Number(card.dataset.openId));
        options.onOpen(project, matches.get(project.id));
    }

    grid.addEventListener("click", open);
    grid.addEventListener("keydown", event => { if (event.key === "Enter") open(event); });
    draw();
}

// ---------- application timeline (employee tracker) ----------

function Stepper(application) {
    const reached = new Map(application.timeline.map(step => [step.status, step]));
    const decided = ["Accepted", "Rejected"].includes(application.status);
    const steps = [
        { label: "Submitted", step: reached.get("Submitted") || { created_at: application.submitted_at } },
        { label: "Under review", step: reached.get("Under Review") || (decided ? {} : null) },
        { label: decided ? application.status : "Decision", step: decided ? (reached.get(application.status) || {}) : null }
    ];

    return `
        <div class="stepper">
            ${steps.map(({ label, step }, index) => {
                const kind = !step ? "" : index === 2 ? (application.status === "Accepted" ? "good" : "bad") : "done";
                return `<div class="step ${kind}">
                    <strong>${escapeHTML(label)}</strong>
                    <span class="subtle">${step && step.created_at ? timeAgo(step.created_at) : step ? "" : "Waiting"}</span>
                </div>`;
            }).join("")}
        </div>
    `;
}
