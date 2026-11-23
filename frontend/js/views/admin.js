// Admin screen: grant or remove project manager access.

import { get, sendJSON } from "../api.js";
import { avatarHTML } from "../avatars.js";
import { $, escapeHTML, toast } from "../ui.js";

const ROLES = [["employee", "Employee"], ["pm", "Project manager"], ["admin", "Admin"]];

let state = null;
let users = [];

export function initAdminView(appState) {
    state = appState;

    $("#admin-search").addEventListener("input", renderRows);

    $("#admin-users").addEventListener("change", async event => {
        const select = event.target.closest("[data-user-role]");
        if (!select) return;

        const user = users.find(item => item.id === Number(select.dataset.userRole));
        select.disabled = true;

        try {
            await sendJSON("PATCH", `/admin/users/${select.dataset.userRole}/role`, { role: select.value });
            user.role = select.value;
            toast(`${user.display_name} is now ${state.roleLabel(select.value).toLowerCase()}.`);
        } catch (error) {
            toast(error.message, "error");
            select.value = user.role;
        } finally {
            select.disabled = false;
        }
    });
}

export async function renderAdmin() {
    $("#admin-users").innerHTML = `<tr><td colspan="3" class="muted">Loading...</td></tr>`;

    try {
        users = await get("/admin/users");
        renderRows();
    } catch (error) {
        $("#admin-users").innerHTML = `<tr><td colspan="3">${escapeHTML(error.message)}</td></tr>`;
    }
}

function renderRows() {
    const text = $("#admin-search").value.trim().toLowerCase();
    const visible = users.filter(user =>
        `${user.display_name} ${user.email}`.toLowerCase().includes(text));

    $("#admin-users").innerHTML = visible.length
        ? visible.map(user => `
            <tr>
                <td>
                    <div class="person">
                        ${avatarHTML(user, "sm")}
                        <div class="person-text">
                            <strong>${escapeHTML(user.display_name)}</strong>
                            <span>${escapeHTML(user.email)}</span>
                        </div>
                    </div>
                </td>
                <td>${Number(user.managed_projects)}</td>
                <td>
                    <label class="sr-only" for="role-${Number(user.id)}">Role for ${escapeHTML(user.display_name)}</label>
                    <select id="role-${Number(user.id)}" data-user-role="${Number(user.id)}"
                        ${user.id === state.me.id ? "disabled title='You cannot change your own role'" : ""}>
                        ${ROLES.map(([value, label]) =>
                            `<option value="${value}" ${value === user.role ? "selected" : ""}>${label}</option>`
                        ).join("")}
                    </select>
                </td>
            </tr>`).join("")
        : `<tr><td colspan="3" class="muted">No one matches that search.</td></tr>`;
}
