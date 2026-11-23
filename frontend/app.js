// When the backend serves this page (http://127.0.0.1:8000) the API is on
// the same origin. Otherwise (Live Server, file://, GitHub Pages) we try the
// local API and fall back to the bundled sample roles in demo mode.
const API_URL = window.location.port === "8000"
    ? window.location.origin
    : "http://127.0.0.1:8000";

const SKILLS_STORAGE_KEY = "projecthub.skills";

let employeeSkills = loadSavedSkills();
let availableProjects = [];
let selectedProject = null;
let demoMode = false;

// ==========================================
// HELPER FUNCTIONS
// ==========================================

function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, character => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;"
    })[character]);
}

function splitSkills(value) {
    const seen = new Set();

    return String(value || "")
        .split(/[,;|\n]/)
        .map(skill => skill.trim())
        .filter(skill => {
            const key = skill.toLowerCase();
            if (!skill || seen.has(key)) return false;
            seen.add(key);
            return true;
        });
}

function showMessage(elementId, message, isError = false) {
    const element = document.getElementById(elementId);
    if (!element) return;

    element.textContent = message;
    element.classList.toggle("status-error", isError);
    element.classList.toggle("status-success", !isError && Boolean(message));
}

function skillChips(skills, kind) {
    if (!skills || skills.length === 0) return "";

    return skills
        .map(skill => `<span class="skill-chip ${kind}">${escapeHTML(skill)}</span>`)
        .join("");
}

function matchBlock(match) {
    if (!match) return "";

    return `
        <div class="match-meter" aria-label="Match score ${match.score}%">
            <div class="match-meter-fill" style="width: ${Number(match.score)}%"></div>
        </div>
        <p><strong>Match:</strong> ${Number(match.score)}%</p>
        <div class="skill-chips">
            ${skillChips(match.matched_required, "matched")}
            ${skillChips(match.matched_nice_to_have, "bonus")}
            ${skillChips(match.missing_required, "missing")}
        </div>
    `;
}

async function apiRequest(path, options = {}) {
    const response = await fetch(`${API_URL}${path}`, options);
    const result = await response.json().catch(() => ({}));

    if (!response.ok) {
        throw new Error(result.detail || `Request failed (${response.status}).`);
    }

    return result;
}

function loadSavedSkills() {
    try {
        return splitSkills(localStorage.getItem(SKILLS_STORAGE_KEY) || "");
    } catch {
        return [];
    }
}

function saveSkills(skills) {
    employeeSkills = skills;

    try {
        localStorage.setItem(SKILLS_STORAGE_KEY, skills.join(", "));
    } catch {
        // Storage can be blocked (private mode); skills still last for the session.
    }

    document.getElementById("skill-count").textContent = skills.length;
}

// ==========================================
// NAVIGATION
// ==========================================

function showView(selectedView) {
    document.querySelectorAll(".view").forEach(view => {
        view.classList.add("hidden");
    });

    document.querySelectorAll(".nav-button").forEach(nav => {
        nav.classList.toggle("active", nav.dataset.view === selectedView);
    });

    document.getElementById(`${selectedView}-view`)?.classList.remove("hidden");

    if (selectedView === "browse") loadProjects();
    if (selectedView === "recommended") showRecommendations();
    if (selectedView === "manager") loadManagerProjects();
}

function setupNavigation() {
    document.querySelectorAll(".nav-button").forEach(button => {
        button.addEventListener("click", () => showView(button.dataset.view));
    });
}

// ==========================================
// LOAD PROJECTS (API, or bundled samples in demo mode)
// ==========================================

async function getProjects() {
    try {
        const projects = await apiRequest("/projects");
        setDemoMode(false);
        return projects;

    } catch (error) {
        console.warn("API unavailable, showing sample roles.", error);
        setDemoMode(true);
        return loadSampleProjects();
    }
}

async function loadSampleProjects() {
    try {
        const response = await fetch("sample-projects.json");
        const projects = await response.json();
        return projects.filter(
            project => String(project.status).trim().toLowerCase() === "open"
        );
    } catch (error) {
        console.error("Could not load sample roles.", error);
        return [];
    }
}

function setDemoMode(enabled) {
    demoMode = enabled;
    document.getElementById("demo-banner").classList.toggle("hidden", !enabled);
}

async function loadProjects() {
    availableProjects = await getProjects();

    document.getElementById("project-count").textContent = availableProjects.length;
    document.getElementById("skill-count").textContent = employeeSkills.length;

    searchProjects();
    loadLocationOptions(availableProjects);
    updateMatchCount();
}

// ==========================================
// LOCATION FILTER
// ==========================================

function loadLocationOptions(projects) {
    const filter = document.getElementById("location-filter");
    if (!filter) return;

    const currentValue = filter.value;
    const locations = [
        ...new Set(projects.map(project => project.location).filter(Boolean))
    ].sort();

    filter.innerHTML = '<option value="">All Locations</option>';

    locations.forEach(location => {
        const option = document.createElement("option");
        option.value = location;
        option.textContent = location;
        filter.appendChild(option);
    });

    filter.value = locations.includes(currentValue) ? currentValue : "";
}

// ==========================================
// DISPLAY PROJECT CARDS
// ==========================================

function projectActions(project) {
    return `
        <div class="project-actions">
            <button class="secondary-button" data-action="details"
                data-id="${Number(project.id)}">
                View Full Description
            </button>

            <button class="primary-button" data-action="apply"
                data-id="${Number(project.id)}" ${demoMode ? "disabled" : ""}
                title="${demoMode ? "Start the API to apply" : ""}">
                Apply
            </button>
        </div>
    `;
}

function displayProjects(projects) {
    const container = document.getElementById("project-list");
    if (!container) return;

    if (projects.length === 0) {
        container.innerHTML = "<p>No available projects found.</p>";
        return;
    }

    container.innerHTML = projects.map(project => `
        <div class="project-card">
            <h2>${escapeHTML(project.title)}</h2>

            <p><strong>Client:</strong>
                ${escapeHTML(project.client_project || "Not specified")}</p>

            <p><strong>Location:</strong>
                ${escapeHTML(project.location || "Not specified")}</p>

            <p><strong>Seniority:</strong>
                ${escapeHTML(project.seniority || "Not specified")}</p>

            <p><strong>Required Skills:</strong>
                ${escapeHTML(project.required_skills || "Not specified")}</p>

            ${projectActions(project)}
        </div>
    `).join("");
}

// ==========================================
// SEARCH PROJECTS
// ==========================================

function searchProjects() {
    const searchText = document.getElementById("project-search").value
        .toLowerCase()
        .trim();

    const location = document.getElementById("location-filter").value;

    const filtered = availableProjects.filter(project => {
        const searchableText = [
            project.title,
            project.client_project,
            project.required_skills,
            project.nice_to_have_skills,
            project.description,
            project.location
        ].join(" ").toLowerCase();

        return searchableText.includes(searchText)
            && (!location || project.location === location);
    });

    displayProjects(filtered);
}

// ==========================================
// PROJECT DETAILS
// ==========================================

function openProjectDetails(project) {
    selectedProject = project;

    document.getElementById("project-details-content").innerHTML = `
        <h1>${escapeHTML(project.title)}</h1>

        <p><strong>Project ID:</strong>
            ${escapeHTML(project.role_id || "Not specified")}</p>

        <p><strong>Client:</strong>
            ${escapeHTML(project.client_project || "Not specified")}</p>

        <p><strong>Location:</strong>
            ${escapeHTML(project.location || "Not specified")}</p>

        <p><strong>Seniority:</strong>
            ${escapeHTML(project.seniority || "Not specified")}</p>

        <p><strong>Start Date:</strong>
            ${escapeHTML(project.start_date || "Not specified")}</p>

        <h3>Required Skills</h3>
        <p>${escapeHTML(project.required_skills || "Not specified")}</p>

        <h3>Preferred Skills</h3>
        <p>${escapeHTML(project.nice_to_have_skills || "Not specified")}</p>

        <h3>Full Project Description</h3>
        <p class="full-description">
            ${escapeHTML(project.description || "No additional description provided.")}
        </p>
    `;

    const applyButton = document.getElementById("details-apply-button");
    applyButton.disabled = demoMode;
    applyButton.title = demoMode ? "Start the API to apply" : "";

    document.getElementById("project-details-modal").classList.remove("hidden");
}

// ==========================================
// APPLICATION FORM
// ==========================================

function openApplicationForm(project) {
    if (!project || demoMode) return;

    selectedProject = project;

    document.getElementById("application-project-id").value = project.id;
    document.getElementById("application-project-title").textContent =
        `Applying for: ${project.title}`;
    document.getElementById("applicant-skills").value = employeeSkills.join(", ");
    document.getElementById("application-resume").value = "";

    showMessage("application-status", "");

    document.getElementById("application-modal").classList.remove("hidden");
    document.getElementById("project-details-modal").classList.add("hidden");
}

function validateResumeFile(file, statusElementId) {
    if (!file) return true;

    const extension = file.name.toLowerCase().slice(file.name.lastIndexOf("."));

    if (![".pdf", ".docx"].includes(extension)) {
        showMessage(statusElementId, "Please select a PDF or DOCX resume.", true);
        return false;
    }

    if (file.size > 5 * 1024 * 1024) {
        showMessage(statusElementId, "Your resume must be 5 MB or smaller.", true);
        return false;
    }

    return true;
}

async function submitApplication(event) {
    event.preventDefault();

    const resumeFile = document.getElementById("application-resume").files[0];
    const name = document.getElementById("applicant-name").value.trim();
    const email = document.getElementById("applicant-email").value.trim();
    const skills = document.getElementById("applicant-skills").value.trim();
    const coverLetter = document.getElementById("application-cover-letter").value.trim();

    if (!name || !email) {
        showMessage("application-status", "Please enter your name and email.", true);
        return;
    }

    if (!validateResumeFile(resumeFile, "application-status")) return;

    const formData = new FormData();
    formData.append("project_id", document.getElementById("application-project-id").value);
    formData.append("name", name);
    formData.append("email", email);
    formData.append("skills", skills);
    formData.append("cover_letter", coverLetter);

    if (resumeFile) formData.append("resume", resumeFile);

    const submitButton = document.getElementById("submit-application");
    submitButton.disabled = true;
    submitButton.textContent = "Submitting...";

    try {
        const result = await apiRequest("/applications", {
            method: "POST",
            body: formData
        });

        let message =
            `Success! Your application number is ${result.application_id}. ` +
            `Skill match: ${result.match_score}%.`;

        if (result.resume_uploaded) {
            message += ` Resume uploaded (${result.resume_text_characters} characters read).`;
        }

        showMessage("application-status", message);
        saveSkills(splitSkills(skills));
        document.getElementById("application-form").reset();

        setTimeout(() => {
            document.getElementById("application-modal").classList.add("hidden");
        }, 3000);

    } catch (error) {
        showMessage("application-status", error.message, true);

    } finally {
        submitButton.disabled = false;
        submitButton.textContent = "Submit Application";
    }
}

// ==========================================
// EMPLOYEE PROFILE
// ==========================================

function setupProfile() {
    const skillsInput = document.getElementById("employee-skills");
    skillsInput.value = employeeSkills.join(", ");

    document.getElementById("save-profile").addEventListener("click", () => {
        saveSkills(splitSkills(skillsInput.value));
        showMessage("profile-status", "Your skills have been saved.");
        updateMatchCount();
    });

    document.getElementById("resume-file").addEventListener("change", readSkillsFromResume);
}

async function readSkillsFromResume() {
    const input = document.getElementById("resume-file");
    const file = input.files[0];

    if (!file || !validateResumeFile(file, "resume-status")) return;

    if (demoMode) {
        showMessage("resume-status", "Start the API to read skills from a resume.", true);
        return;
    }

    showMessage("resume-status", `Reading ${file.name}...`);

    const formData = new FormData();
    formData.append("file", file);

    try {
        const result = await apiRequest("/resumes/parse", {
            method: "POST",
            body: formData
        });

        const skillsInput = document.getElementById("employee-skills");
        const current = splitSkills(skillsInput.value);
        const known = new Set(current.map(skill => skill.toLowerCase()));
        const added = result.detected_skills.filter(
            skill => !known.has(skill.toLowerCase())
        );

        skillsInput.value = [...current, ...added].join(", ");

        showMessage(
            "resume-status",
            added.length
                ? `Found ${added.length} new skill(s): ${added.join(", ")}. Review them and click Save Profile.`
                : "No new skills found in this resume."
        );

    } catch (error) {
        showMessage("resume-status", error.message, true);
    }
}

// ==========================================
// PROJECT RECOMMENDATIONS
// ==========================================

async function getRecommendations() {
    return apiRequest("/matches/recommend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ skills: employeeSkills })
    });
}

async function updateMatchCount() {
    const counter = document.getElementById("match-count");

    if (demoMode || employeeSkills.length === 0) {
        counter.textContent = 0;
        return;
    }

    try {
        const ranked = await getRecommendations();
        counter.textContent = ranked.filter(project => project.match.score > 0).length;
    } catch {
        counter.textContent = 0;
    }
}

async function showRecommendations() {
    const container = document.getElementById("recommended-list");

    if (demoMode) {
        container.innerHTML = "<p>Start the API to get skill-based recommendations.</p>";
        return;
    }

    if (employeeSkills.length === 0) {
        container.innerHTML =
            "<p>Add your skills in <strong>My Profile</strong> to see recommended projects.</p>";
        return;
    }

    container.innerHTML = "<p>Finding your best matches...</p>";

    try {
        const ranked = await getRecommendations();
        const matching = ranked.filter(project => project.match.score > 0);

        document.getElementById("match-count").textContent = matching.length;

        if (matching.length === 0) {
            container.innerHTML =
                "<p>No open projects match your skills yet. Try adding more skills.</p>";
            return;
        }

        container.innerHTML = matching.map(project => `
            <div class="project-card">
                <h2>${escapeHTML(project.title)}</h2>
                <p>${escapeHTML(project.client_project || "")}</p>
                ${matchBlock(project.match)}
                ${projectActions(project)}
            </div>
        `).join("");

    } catch (error) {
        container.innerHTML = `<p>${escapeHTML(error.message)}</p>`;
    }
}

// ==========================================
// MANAGER DASHBOARD
// ==========================================

let managerProjects = [];

async function loadManagerProjects() {
    const container = document.getElementById("manager-project-list");
    document.getElementById("manager-applicants").classList.add("hidden");

    if (demoMode) {
        container.innerHTML = "<p>Start the API to manage projects.</p>";
        return;
    }

    try {
        managerProjects = await apiRequest("/projects?include_closed=true");

        const open = managerProjects.filter(
            project => String(project.status).trim().toLowerCase() === "open"
        ).length;

        document.getElementById("manager-open").textContent = open;
        document.getElementById("manager-closed").textContent = managerProjects.length - open;
        document.getElementById("manager-total").textContent = managerProjects.length;

        if (managerProjects.length === 0) {
            container.innerHTML = "<p>No projects found.</p>";
            return;
        }

        container.innerHTML = managerProjects.map(project => `
            <div class="project-card">
                <h3>${escapeHTML(project.title)}</h3>
                <p>${escapeHTML(project.role_id || "")} &middot;
                    ${escapeHTML(project.location || "Not specified")}</p>
                <p><strong>Status:</strong> ${escapeHTML(project.status || "")}</p>
                <p><strong>Applicants:</strong> ${Number(project.applicant_count)}</p>
                <button class="secondary-button" data-action="applicants"
                    data-id="${Number(project.id)}"
                    ${Number(project.applicant_count) === 0 ? "disabled" : ""}>
                    View Applicants
                </button>
            </div>
        `).join("");

    } catch (error) {
        container.innerHTML = `<p>${escapeHTML(error.message)}</p>`;
    }
}

const APPLICATION_STATUSES = ["Submitted", "Under Review", "Accepted", "Rejected"];

async function showApplicants(projectId) {
    const project = managerProjects.find(item => Number(item.id) === projectId);
    const panel = document.getElementById("manager-applicants");
    const list = document.getElementById("manager-applicant-list");

    document.getElementById("manager-applicants-title").textContent =
        `Applicants for ${project ? project.title : "project"}, best match first`;

    panel.classList.remove("hidden");
    list.innerHTML = "<p>Loading applicants...</p>";

    try {
        const applicants = await apiRequest(`/projects/${projectId}/applications`);

        if (applicants.length === 0) {
            list.innerHTML = "<p>No applicants yet.</p>";
            return;
        }

        list.innerHTML = applicants.map(applicant => `
            <div class="project-card">
                <h3>${escapeHTML(applicant.name)}</h3>
                <p>${escapeHTML(applicant.email)}</p>
                ${matchBlock(applicant.match)}
                ${applicant.cover_letter
                    ? `<p class="full-description">${escapeHTML(applicant.cover_letter)}</p>`
                    : ""}
                <label>
                    <strong>Status:</strong>
                    <select data-application-id="${Number(applicant.id)}" class="status-select">
                        ${APPLICATION_STATUSES.map(status => `
                            <option ${status === applicant.application_status ? "selected" : ""}>
                                ${status}
                            </option>`).join("")}
                    </select>
                </label>
            </div>
        `).join("");

        panel.scrollIntoView({ behavior: "smooth" });

    } catch (error) {
        list.innerHTML = `<p>${escapeHTML(error.message)}</p>`;
    }
}

async function updateApplicationStatus(select) {
    select.disabled = true;

    try {
        await apiRequest(`/applications/${Number(select.dataset.applicationId)}/status`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status: select.value })
        });
    } catch (error) {
        alert(error.message);
    } finally {
        select.disabled = false;
    }
}

// ==========================================
// EMPLOYEE APPLICATION TRACKING
// ==========================================

async function loadMyApplications() {
    const email = document.getElementById("tracking-email").value.trim().toLowerCase();
    const container = document.getElementById("application-history-list");

    if (!email || !email.includes("@")) {
        showMessage("tracking-status", "Please enter a valid email address.", true);
        return;
    }

    container.innerHTML = "<p>Loading your applications...</p>";
    showMessage("tracking-status", "");

    try {
        const result = await apiRequest(
            `/applications/my-applications?email=${encodeURIComponent(email)}`
        );

        if (result.applications.length === 0) {
            container.innerHTML = "<p>You haven't submitted any applications yet.</p>";
            showMessage("tracking-status", "No applications found.");
            return;
        }

        container.innerHTML = result.applications.map(application => {
            const submittedDate = application.submitted_at
                ? new Date(application.submitted_at.replace(" ", "T") + "Z").toLocaleDateString()
                : "Date unavailable";

            return `
                <div class="project-card application-card">
                    <h2>${escapeHTML(application.project_title)}</h2>

                    <p><strong>Application Number:</strong>
                        ${Number(application.application_id)}</p>

                    <p><strong>Client:</strong>
                        ${escapeHTML(application.client_project || "Not specified")}</p>

                    <p><strong>Location:</strong>
                        ${escapeHTML(application.location || "Not specified")}</p>

                    <p><strong>Date Submitted:</strong> ${escapeHTML(submittedDate)}</p>

                    <p><strong>Status:</strong>
                        <span class="application-status-badge">
                            ${escapeHTML(application.status || "Submitted")}
                        </span>
                    </p>
                </div>
            `;
        }).join("");

        showMessage("tracking-status", `Found ${result.total_applications} application(s).`);

    } catch (error) {
        container.innerHTML = "";
        showMessage("tracking-status", error.message, true);
    }
}

// ==========================================
// MANAGER CSV UPLOAD
// ==========================================

async function uploadCSV() {
    const fileInput = document.getElementById("manager-csv-file");
    const file = fileInput.files[0];

    if (!file) {
        showMessage("csv-upload-status", "Please select a CSV file.", true);
        return;
    }

    const formData = new FormData();
    formData.append("file", file);

    try {
        const result = await apiRequest("/projects/upload-csv", {
            method: "POST",
            body: formData
        });

        showMessage(
            "csv-upload-status",
            `Added: ${result.imported}. Updated: ${result.updated}. Skipped: ${result.skipped}.`
        );

        fileInput.value = "";
        await loadProjects();
        await loadManagerProjects();

    } catch (error) {
        showMessage("csv-upload-status", error.message, true);
    }
}

// ==========================================
// EVENT LISTENERS
// ==========================================

function setupProjectActions() {
    document.addEventListener("click", event => {
        const button = event.target.closest("[data-action]");
        if (!button) return;

        const projectId = Number(button.dataset.id);

        if (button.dataset.action === "applicants") {
            showApplicants(projectId);
            return;
        }

        const project = availableProjects.find(item => Number(item.id) === projectId);
        if (!project) return;

        if (button.dataset.action === "details") openProjectDetails(project);
        if (button.dataset.action === "apply") openApplicationForm(project);
    });

    document.addEventListener("change", event => {
        if (event.target.matches(".status-select")) {
            updateApplicationStatus(event.target);
        }
    });
}

function setupModals() {
    document.getElementById("close-details").addEventListener("click", () => {
        document.getElementById("project-details-modal").classList.add("hidden");
    });

    document.getElementById("close-application").addEventListener("click", () => {
        document.getElementById("application-modal").classList.add("hidden");
    });

    document.getElementById("details-apply-button").addEventListener("click", () => {
        openApplicationForm(selectedProject);
    });
}

// ==========================================
// START PROJECTHUB
// ==========================================

document.addEventListener("DOMContentLoaded", () => {
    setupNavigation();
    setupProfile();
    setupProjectActions();
    setupModals();

    document.getElementById("search-button").addEventListener("click", searchProjects);
    document.getElementById("project-search").addEventListener("input", searchProjects);
    document.getElementById("location-filter").addEventListener("change", searchProjects);
    document.getElementById("application-form").addEventListener("submit", submitApplication);
    document.getElementById("upload-csv-button").addEventListener("click", uploadCSV);
    document.getElementById("load-applications-button")
        .addEventListener("click", loadMyApplications);

    loadProjects();
});
