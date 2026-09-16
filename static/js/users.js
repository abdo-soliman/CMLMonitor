let userCurrentPage = 1;
let userCurrentSize = 25;
let userSearchQuery = "";
let addUserModalInstance = null;
let editUserModalInstance = null;
let deleteUserModalInstance = null;

document.addEventListener('DOMContentLoaded', () => {
    // Initialize Modals
    const addEl = document.getElementById('addUserModal');
    const editEl = document.getElementById('editUserModal');
    const delEl = document.getElementById('deleteUserModal');
    if (addEl) addUserModalInstance = new bootstrap.Modal(addEl);
    if (editEl) editUserModalInstance = new bootstrap.Modal(editEl);
    if (delEl) deleteUserModalInstance = new bootstrap.Modal(delEl);

    // If Users tab is active on boot, fetch users immediately
    const usersTab = document.getElementById('users-tab');
    if (usersTab && usersTab.classList.contains('active')) {
        fetchUsers();
    }

    // Lazy load when clicking Users tab
    if (usersTab) {
        usersTab.addEventListener('shown.bs.tab', () => {
            fetchUsers();
        });
    }
});

async function fetchUsers(page = null) {
    if (page) userCurrentPage = page;

    const url = `/api/users?page=${userCurrentPage}&size=${userCurrentSize}&search=${encodeURIComponent(userSearchQuery)}`;

    try {
        const response = await fetch(url);
        const data = await response.json();

        renderUsersTable(data.users, data.current_user_id);
        renderUsersPagination(data.pagination);
        updateUserDatalist(data.usernames);
    } catch (err) {
        console.error("Failed to fetch users:", err);
    }
}

function renderUsersTable(users, currentUserId) {
    const tbody = document.getElementById('usersTableBody');
    tbody.innerHTML = '';

    if (!users || users.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-muted">No users found.</td></tr>`;
        return;
    }

    users.forEach(u => {
        const tr = document.createElement('tr');
        
        const typeBadge = u.is_external 
            ? `<span class="badge bg-secondary">External (LDAP)</span>` 
            : `<span class="badge bg-primary">Local</span>`;

        const isSelf = (u.id === currentUserId);

        let actionButtons = [];
        
        // Edit Button (Only for local users who are not the logged-in user)
        if (u.can_edit) {
            actionButtons.push(`<button class="btn btn-sm btn-outline-primary" title="Edit" onclick="openEditUserModal(${u.id}, '${escapeHtml(u.username)}', '${escapeHtml(u.fullname)}', '${escapeHtml(u.mail)}')"><i class="fa-solid fa-pen"></i></button>`);
        }

        // Delete Button (Available for all users EXCEPT the logged-in user)
        if (!isSelf) {
            actionButtons.push(`<button class="btn btn-sm btn-outline-danger" title="Remove" onclick="openDeleteUserModal(${u.id}, '${escapeHtml(u.username)}')"><i class="fa-solid fa-trash"></i></button>`);
        }

        const actionsHtml = actionButtons.length > 0 
            ? `<div class="d-flex justify-content-center gap-2">${actionButtons.join('')}</div>` 
            : `<span class="text-muted small">-</span>`;

        tr.innerHTML = `
            <td><strong>${escapeHtml(u.username)}</strong> ${isSelf ? '<span class="badge bg-info text-dark ms-1">You</span>' : ''}</td>
            <td>${escapeHtml(u.fullname)}</td>
            <td>${escapeHtml(u.mail)}</td>
            <td>${typeBadge}</td>
            <td>
                <div class="form-check form-switch mb-0">
                    <input class="form-check-input" type="checkbox" ${u.is_admin ? 'checked' : ''} ${isSelf ? 'disabled' : ''} onchange="toggleUserRole(${u.id}, 'is_admin', this.checked)">
                </div>
            </td>
            <td>
                <div class="form-check form-switch mb-0">
                    <input class="form-check-input" type="checkbox" ${u.config_admin ? 'checked' : ''} ${isSelf ? 'disabled' : ''} onchange="toggleUserRole(${u.id}, 'config_admin', this.checked)">
                </div>
            </td>
            <td class="text-center">${actionsHtml}</td>
        `;
        tbody.appendChild(tr);
    });
}

async function toggleUserRole(userId, role, value) {
    try {
        const response = await fetch('/api/users/toggle-role', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId, role: role, value: value })
        });
        
        const data = await response.json();
        showUserBanner(data.message, data.success ? 'success' : 'danger');
        if (!data.success) fetchUsers(); // Revert check state on failure
    } catch (err) {
        showUserBanner("Failed to update role.", 'danger');
        fetchUsers();
    }
}

// --- Add User Modal Logic ---
function openAddUserModal() {
    document.getElementById('addUserForm').reset();
    document.getElementById('addUserError').classList.add('d-none');
    document.getElementById('typeLocal').checked = true;
    toggleAddUserForm('local');
    addUserModalInstance.show();
}

function toggleAddUserForm(type) {
    const isExternal = (type === 'external');

    document.getElementById('add_fullname').disabled = isExternal;
    document.getElementById('add_mail').disabled = isExternal;
    document.getElementById('add_password').disabled = isExternal;
    document.getElementById('add_confirm_password').disabled = isExternal;

    document.getElementById('add_fullname').required = !isExternal;
    document.getElementById('add_mail').required = !isExternal;
    document.getElementById('add_password').required = !isExternal;
    document.getElementById('add_confirm_password').required = !isExternal;
}

async function submitAddUser() {
    const errDiv = document.getElementById('addUserError');
    errDiv.classList.add('d-none');

    const userType = document.querySelector('input[name="addUserType"]:checked').value;
    const username = document.getElementById('add_username').value.trim();
    const fullname = document.getElementById('add_fullname').value.trim();
    const mail = document.getElementById('add_mail').value.trim();
    const password = document.getElementById('add_password').value;
    const confirmPassword = document.getElementById('add_confirm_password').value;
    const isAdmin = document.getElementById('add_is_admin').checked;
    const configAdmin = document.getElementById('add_config_admin').checked;

    // Validate before triggering the loading state
    if (userType === 'local' && password !== confirmPassword) {
        errDiv.innerText = "Passwords do not match.";
        errDiv.classList.remove('d-none');
        return;
    }

    // Lock UI and show spinner
    const btn = document.getElementById('btnSaveUser');
    const spinner = btn.querySelector('.spinner-border');
    const btnText = btn.querySelector('.btn-text');
    btn.disabled = true;
    spinner.classList.remove('d-none');
    btnText.innerText = 'Saving...';

    const payload = {
        user_type: userType,
        username: username,
        fullname: fullname,
        mail: mail,
        password: password,
        confirm_password: confirmPassword,
        is_admin: isAdmin,
        config_admin: configAdmin
    };

    try {
        const response = await fetch('/api/users/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();

        if (data.success) {
            addUserModalInstance.hide();
            showUserBanner(data.message, 'success');
            fetchUsers();
        } else {
            errDiv.innerText = data.message;
            errDiv.classList.remove('d-none');
        }
    } catch (err) {
        errDiv.innerText = "Server error processing request.";
        errDiv.classList.remove('d-none');
    } finally {
        // Restore button state
        btn.disabled = false;
        spinner.classList.add('d-none');
        btnText.innerText = 'Save User';
    }
}

// --- Edit User Modal Logic ---
function openEditUserModal(id, username, fullname, mail) {
    document.getElementById('editUserForm').reset();
    document.getElementById('editUserError').classList.add('d-none');

    document.getElementById('edit_user_id').value = id;
    document.getElementById('edit_username').value = username;
    document.getElementById('edit_fullname').value = fullname;
    document.getElementById('edit_mail').value = mail;

    editUserModalInstance.show();
}

async function submitEditUser() {
    const errDiv = document.getElementById('editUserError');
    errDiv.classList.add('d-none');

    const userId = document.getElementById('edit_user_id').value;
    const username = document.getElementById('edit_username').value.trim();
    const fullname = document.getElementById('edit_fullname').value.trim();
    const mail = document.getElementById('edit_mail').value.trim();
    const password = document.getElementById('edit_password').value;
    const confirmPassword = document.getElementById('edit_confirm_password').value;

    // Frontend validation before triggering loading state
    if (password && password !== confirmPassword) {
        errDiv.innerText = "New passwords do not match.";
        errDiv.classList.remove('d-none');
        return;
    }

    // Lock UI and show spinner
    const btn = document.getElementById('btnUpdateUser');
    const spinner = btn.querySelector('.spinner-border');
    const btnText = btn.querySelector('.btn-text');
    btn.disabled = true;
    spinner.classList.remove('d-none');
    btnText.innerText = 'Updating...';

    const payload = {
        user_id: userId,
        username: username,
        fullname: fullname,
        mail: mail,
        password: password,
        confirm_password: confirmPassword
    };

    try {
        const response = await fetch('/api/users/edit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();

        if (data.success) {
            editUserModalInstance.hide();
            showUserBanner(data.message, 'success');
            fetchUsers();
        } else {
            errDiv.innerText = data.message;
            errDiv.classList.remove('d-none');
        }
    } catch (err) {
        errDiv.innerText = "Server error processing request.";
        errDiv.classList.remove('d-none');
    } finally {
        // Restore button state
        btn.disabled = false;
        spinner.classList.add('d-none');
        btnText.innerText = 'Update User';
    }
}

// --- Delete User Modal Logic ---
function openDeleteUserModal(id, username) {
    document.getElementById('deleteUserError').classList.add('d-none');
    document.getElementById('delete_user_id').value = id;
    document.getElementById('delete_username_display').innerText = username;
    deleteUserModalInstance.show();
}

async function submitDeleteUser() {
    const errDiv = document.getElementById('deleteUserError');
    errDiv.classList.add('d-none');

    const userId = document.getElementById('delete_user_id').value;

    // Lock UI and show spinner
    const btn = document.getElementById('btnConfirmDelete');
    const spinner = btn.querySelector('.spinner-border');
    const btnText = btn.querySelector('.btn-text');
    btn.disabled = true;
    spinner.classList.remove('d-none');
    btnText.innerText = 'Removing...';

    try {
        const response = await fetch('/api/users/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId })
        });
        const data = await response.json();

        if (data.success) {
            deleteUserModalInstance.hide();
            showUserBanner(data.message, 'success');
            fetchUsers();
        } else {
            errDiv.innerText = data.message;
            errDiv.classList.remove('d-none');
        }
    } catch (err) {
        errDiv.innerText = "Server error processing request.";
        errDiv.classList.remove('d-none');
    } finally {
        // Restore button state
        btn.disabled = false;
        spinner.classList.add('d-none');
        btnText.innerText = 'Confirm';
    }
}

// --- Search & Pagination Helpers ---
function onUserSearchInput(value) {
    userSearchQuery = value.trim();
    fetchUsers(1);
}

function updateUserDatalist(usernames) {
    const datalist = document.getElementById('user-search-datalist');
    datalist.innerHTML = (usernames || []).map(u => `<option value="${escapeHtml(u)}">`).join('');
}

function renderUsersPagination(p) {
    const btnFirst = document.getElementById('user-btn-first');
    const btnPrev = document.getElementById('user-btn-prev');
    const btnNext = document.getElementById('user-btn-next');
    const btnLast = document.getElementById('user-btn-last');

    btnFirst.classList.toggle('disabled', !p.has_prev);
    btnPrev.classList.toggle('disabled', !p.has_prev);
    btnNext.classList.toggle('disabled', !p.has_next);
    btnLast.classList.toggle('disabled', !p.has_next);

    btnFirst.querySelector('button').onclick = p.has_prev ? () => fetchUsers(1) : null;
    btnPrev.querySelector('button').onclick = p.has_prev ? () => fetchUsers(p.prev_num) : null;
    btnNext.querySelector('button').onclick = p.has_next ? () => fetchUsers(p.next_num) : null;
    btnLast.querySelector('button').onclick = p.has_next ? () => fetchUsers(p.pages) : null;
}

function changeUserPageSize(size) {
    userCurrentSize = parseInt(size);
    fetchUsers(1);
}

function showUserBanner(msg, type) {
    const banner = document.getElementById('users-alert-banner');
    const msgSpan = document.getElementById('users-alert-message');

    banner.className = `alert alert-${type} alert-dismissible fade show mt-3`;
    msgSpan.innerText = msg;
    banner.classList.remove('d-none');
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' })[m]);
}
