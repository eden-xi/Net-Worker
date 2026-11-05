
const API_URL = "http://127.0.0.1:8000";

let employeeSkills = [];
let availableProjects = [];
let selectedProject = null;

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
    return String(value || "")
        .split(/[,;|]/)
        .map(skill => skill.trim())
        .filter(Boolean);
}

function showMessage(elementId, message, isError = false) {
    const element = document.getElementById(elementId);
    if (!element) return;

    element.textContent = message;
    element.style.color = isError ? "#c0392b" : "#218838";
}

// ==========================================
// NAVIGATION
// ==========================================

function setupNavigation() {
    const buttons = document.querySelectorAll(".nav-button");

    buttons.forEach(button => {
        button.addEventListener("click", () => {
            const selectedView = button.dataset.view;

            document.querySelectorAll(".view").forEach(view => {
                view.classList.add("hidden");
            });

            document.querySelectorAll(".nav-button").forEach(nav => {
                nav.classList.remove("active");
            });

            document.getElementById(`${selectedView}-view`)
                ?.classList.remove("hidden");

            button.classList.add("active");

            if (selectedView === "browse") loadProjects();
            if (selectedView === "recommended") showRecommendations();
            if (selectedView === "manager") loadManagerProjects();
            if (selectedView === "my-applications") {
                document.getElementById("application-history-list").innerHTML = "";
                showMessage("tracking-status", "");
            }
        });
    });
}

// ==========================================
// LOAD PROJECTS
// ==========================================

async function getProjects() {
    try {
        const response = await fetch(`${API_URL}/projects`);

        if (!response.ok) {
            throw new Error("Could not load projects.");
        }

        return await response.json();

    } catch (error) {
        console.error(error);
        showMessage("profile-status", "Could not connect to ProjectHub API.", true);
        return [];
    }
}

async function loadProjects() {
    availableProjects = await getProjects();

    document.getElementById("project-count").textContent =
        availableProjects.length;

    document.getElementById("skill-count").textContent =
        employeeSkills.length;

    displayProjects(availableProjects);
    loadLocationOptions(availableProjects);
}

// ==========================================
// LOCATION FILTER
// ==========================================

function loadLocationOptions(projects) {
    const filter = document.getElementById("location-filter");
    if (!filter) return;

    const currentValue = filter.value;

    const locations = [
        ...new Set(
            projects
                .map(project => project.location)
                .filter(Boolean)
        )
    ];

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

            <p>
                <strong>Client:</strong>
                ${escapeHTML(project.client_project || "Not specified")}
            </p>

            <p>
                <strong>Location:</strong>
                ${escapeHTML(project.location || "Not specified")}
            </p>

            <p>
                <strong>Seniority:</strong>
                ${escapeHTML(project.seniority || "Not specified")}
            </p>

            <p>
                <strong>Required Skills:</strong>
                ${escapeHTML(project.required_skills || "Not specified")}
            </p>

            <div class="project-actions">
                <button
                    class="secondary-button"
                    data-action="details"
                    data-id="${Number(project.id)}"
                >
                    View Full Description
                </button>

                <button
                    class="primary-button"
                    data-action="apply"
                    data-id="${Number(project.id)}"
                >
                    Apply
                </button>
            </div>
        </div>
    `).join("");
}

// ==========================================
// SEARCH PROJECTS
// ==========================================

function searchProjects() {
    const searchText = document
        .getElementById("project-search")
        .value.toLowerCase()
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

        const matchesSearch = searchableText.includes(searchText);
        const matchesLocation = !location || project.location === location;

        return matchesSearch && matchesLocation;
    });

    displayProjects(filtered);
}

// ==========================================
// PROJECT DETAILS
// ==========================================

async function openProjectDetails(projectId) {
    try {
        const response = await fetch(`${API_URL}/projects/${projectId}`);

        if (!response.ok) {
            throw new Error("Could not load project details.");
        }

        const project = await response.json();
        selectedProject = project;

        const content = document.getElementById("project-details-content");

        content.innerHTML = `
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

        document.getElementById("project-details-modal")
            .classList.remove("hidden");

    } catch (error) {
        alert(error.message);
    }
}

// ==========================================
// OPEN APPLICATION FORM
// ==========================================

function openApplicationForm(project) {
    if (!project) return;

    selectedProject = project;

    document.getElementById("application-project-id").value = project.id;

    document.getElementById("application-project-title").textContent =
        `Applying for: ${project.title}`;

    document.getElementById("applicant-skills").value =
        employeeSkills.join(", ");

    document.getElementById("application-resume").value = "";

    showMessage("application-status", "");

    document.getElementById("application-modal")
        .classList.remove("hidden");

    document.getElementById("project-details-modal")
        .classList.add("hidden");
}

// ==========================================
// SUBMIT APPLICATION WITH ACTUAL RESUME
// ==========================================

async function submitApplication(event) {
    event.preventDefault();

    const projectId = Number(
        document.getElementById("application-project-id").value
    );

    const resumeFile = document.getElementById("application-resume").files[0];

    const name = document.getElementById("applicant-name").value.trim();
    const email = document.getElementById("applicant-email").value.trim();
    const skills = document.getElementById("applicant-skills").value.trim();
    const coverLetter = document.getElementById(
        "application-cover-letter"
    ).value.trim();

    if (!name || !email) {
        showMessage(
            "application-status",
            "Please enter your name and email.",
            true
        );
        return;
    }

    if (!email.includes("@")) {
        showMessage(
            "application-status",
            "Please enter a valid email address.",
            true
        );
        return;
    }

    // Validate the selected resume.
    if (resumeFile) {
        const extension = resumeFile.name
            .toLowerCase()
            .slice(resumeFile.name.lastIndexOf("."));

        if (![".pdf", ".docx"].includes(extension)) {
            showMessage(
                "application-status",
                "Please select a PDF or DOCX resume.",
                true
            );
            return;
        }

        if (resumeFile.size > 5 * 1024 * 1024) {
            showMessage(
                "application-status",
                "Your resume must be smaller than 5 MB.",
                true
            );
            return;
        }
    }

    // FormData sends the actual resume file to FastAPI.
    const formData = new FormData();

    formData.append("project_id", projectId);
    formData.append("name", name);
    formData.append("email", email);
    formData.append("skills", skills);
    formData.append("cover_letter", coverLetter);

    if (resumeFile) {
        formData.append("resume", resumeFile);
    }

    const submitButton = document.getElementById("submit-application");

    submitButton.disabled = true;
    submitButton.textContent = "Submitting...";

    try {
        const response = await fetch(
            `${API_URL}/applications/submit-with-resume`,
            {
                method: "POST",
                body: formData
            }
        );

        const result = await response.json();

        if (!response.ok) {
            throw new Error(
                result.detail || "Application submission failed."
            );
        }

        let successMessage =
            `Success! Your application number is ${result.application_id}.`;

        if (result.resume_uploaded) {
            successMessage +=
                ` Resume uploaded. ${result.resume_text_characters || 0} characters extracted.`;
        } else {
            successMessage += " No new resume was uploaded.";
        }

        showMessage("application-status", successMessage);

        employeeSkills = splitSkills(skills);

        document.getElementById("application-form").reset();

        document.getElementById("skill-count").textContent =
            employeeSkills.length;

        setTimeout(() => {
            document.getElementById("application-modal")
                .classList.add("hidden");
        }, 3000);

    } catch (error) {
        showMessage(
            "application-status",
            error.message,
            true
        );

    } finally {
        submitButton.disabled = false;
        submitButton.textContent = "Submit Application";
    }
}

// ==========================================
// EMPLOYEE PROFILE
// ==========================================

function setupProfile() {
    const resumeInput = document.getElementById("resume-file");

    resumeInput.addEventListener("change", () => {
        const file = resumeInput.files[0];

        showMessage(
            "resume-status",
            file ? `Selected resume: ${file.name}` : ""
        );
    });

    document.getElementById("save-profile")
        .addEventListener("click", () => {

            const skills = document.getElementById("employee-skills").value;

            employeeSkills = splitSkills(skills);

            document.getElementById("skill-count").textContent =
                employeeSkills.length;

            showMessage(
                "profile-status",
                "Your skills have been saved for this session."
            );
        });
}

// ==========================================
// PROJECT RECOMMENDATIONS
// ==========================================

function calculateMatch(project) {
    const requiredSkills = splitSkills(project.required_skills);

    if (requiredSkills.length === 0 || employeeSkills.length === 0) {
        return 0;
    }

    const normalizedEmployeeSkills = employeeSkills.map(
        skill => skill.toLowerCase()
    );

    const matchedSkills = requiredSkills.filter(skill =>
        normalizedEmployeeSkills.includes(skill.toLowerCase())
    );

    return Math.round(
        (matchedSkills.length / requiredSkills.length) * 100
    );
}

function showRecommendations() {
    const container = document.getElementById("recommended-list");

    const rankedProjects = availableProjects
        .map(project => ({
            ...project,
            matchScore: calculateMatch(project)
        }))
        .sort((a, b) => b.matchScore - a.matchScore);

    document.getElementById("match-count").textContent =
        rankedProjects.filter(project => project.matchScore > 0).length;

    if (rankedProjects.length === 0) {
        container.innerHTML = "<p>No recommendations available.</p>";
        return;
    }

    container.innerHTML = rankedProjects.map(project => `
        <div class="project-card">
            <h2>${escapeHTML(project.title)}</h2>

            <p><strong>Match:</strong> ${project.matchScore}%</p>

            <p><strong>Required Skills:</strong>
                ${escapeHTML(project.required_skills || "Not specified")}
            </p>

            <div class="project-actions">
                <button
                    class="secondary-button"
                    data-action="details"
                    data-id="${Number(project.id)}"
                >
                    View Full Description
                </button>

                <button
                    class="primary-button"
                    data-action="apply"
                    data-id="${Number(project.id)}"
                >
                    Apply
                </button>
            </div>
        </div>
    `).join("");
}

// ==========================================
// MANAGER DASHBOARD
// ==========================================

async function loadManagerProjects() {
    try {
        const response = await fetch(`${API_URL}/projects`);

        if (!response.ok) {
            throw new Error("Could not load manager projects.");
        }

        const projects = await response.json();

        const container = document.getElementById("manager-project-list");

        document.getElementById("manager-open").textContent =
            projects.length;

        document.getElementById("manager-closed").textContent =
            "Not available";

        document.getElementById("manager-total").textContent =
            projects.length;

        if (projects.length === 0) {
            container.innerHTML = "<p>No projects found.</p>";
            return;
        }

        container.innerHTML = projects.map(project => `
            <div class="project-card">
                <h3>${escapeHTML(project.title)}</h3>
                <p>${escapeHTML(project.role_id || "")}</p>
                <p>${escapeHTML(project.location || "Not specified")}</p>
            </div>
        `).join("");

    } catch (error) {
        console.error(error);
    }
}


 // ==========================================
 // EMPLOYEE APPLICATION TRACKING
 // ==========================================

async function loadMyApplications() {
    const emailInput = document.getElementById("tracking-email");
    const container = document.getElementById("application-history-list");
    const email = emailInput.value.trim().toLowerCase();

    if (!email || !email.includes("@")) {
        showMessage("tracking-status", "Please enter a valid email address.", true);
        return;
    }

    container.innerHTML = "<p>Loading your applications...</p>";
    showMessage("tracking-status", "");

    try {
        const response = await fetch(
            `${API_URL}/applications/my-applications?email=${encodeURIComponent(email)}`
        );

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || "Could not load applications.");
        }

        if (result.applications.length === 0) {
            container.innerHTML = `
                <p>You haven't submitted any applications yet.</p>
            `;
            showMessage("tracking-status", "No applications found.");
            return;
        }

        container.innerHTML = result.applications.map(application => {
            const submittedDate = application.submitted_at
                ? new Date(application.submitted_at).toLocaleDateString()
                : "Date unavailable";

            const status = application.status || "Submitted";

            return `
                <div class="project-card application-card">
                    <h2>${escapeHTML(application.project_title)}</h2>

                    <p>
                        <strong>Application Number:</strong>
                        ${Number(application.application_id)}
                    </p>

                    <p>
                        <strong>Client:</strong>
                        ${escapeHTML(application.client_project || "Not specified")}
                    </p>

                    <p>
                        <strong>Location:</strong>
                        ${escapeHTML(application.location || "Not specified")}
                    </p>

                    <p>
                        <strong>Date Submitted:</strong>
                        ${escapeHTML(submittedDate)}
                    </p>

                    <p>
                        <strong>Status:</strong>
                        <span class="application-status-badge">
                            ${escapeHTML(status)}
                        </span>
                    </p>
                </div>
            `;
        }).join("");

        showMessage(
            "tracking-status",
            `Found ${result.total_applications} application(s).`
        );

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
        showMessage(
            "csv-upload-status",
            "Please select a CSV file.",
            true
        );
        return;
    }

    const formData = new FormData();
    formData.append("file", file);

    try {
        const response = await fetch(
            `${API_URL}/projects/upload-csv`,
            {
                method: "POST",
                body: formData
            }
        );

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || "CSV upload failed.");
        }

        showMessage(
            "csv-upload-status",
            `Imported: ${result.imported}. Skipped: ${result.skipped}.`
        );

        fileInput.value = "";

        await loadProjects();
        await loadManagerProjects();

    } catch (error) {
        showMessage(
            "csv-upload-status",
            error.message,
            true
        );
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

        const project = availableProjects.find(
            item => Number(item.id) === projectId
        );

        if (!project) return;

        if (button.dataset.action === "details") {
            openProjectDetails(projectId);
        }

        if (button.dataset.action === "apply") {
            openApplicationForm(project);
        }
    });
}

function setupModals() {
    document.getElementById("close-details")
        .addEventListener("click", () => {
            document.getElementById("project-details-modal")
                .classList.add("hidden");
        });

    document.getElementById("close-application")
        .addEventListener("click", () => {
            document.getElementById("application-modal")
                .classList.add("hidden");
        });

    document.getElementById("details-apply-button")
        .addEventListener("click", () => {
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

    document.getElementById("search-button")
        .addEventListener("click", searchProjects);

    document.getElementById("project-search")
        .addEventListener("input", searchProjects);

    document.getElementById("location-filter")
        .addEventListener("change", searchProjects);

    document.getElementById("application-form")
        .addEventListener("submit", submitApplication);

    document.getElementById("upload-csv-button")
        .addEventListener("click", uploadCSV);

    document.getElementById("load-applications-button")
        .addEventListener("click", loadMyApplications);    
    loadProjects();
});
