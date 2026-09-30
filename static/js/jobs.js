let currentPage = 1;
let currentSize = 25;
let searchQuery = "";
let syncPollInterval = null;

document.addEventListener('DOMContentLoaded', () => {
    fetchJobs(1);
    // Poll every 60 seconds
    setInterval(() => fetchJobs(currentPage), 60000);
});

async function fetchJobs(page = null) {
    if (page) currentPage = page;
    
    const url = `/api/jobs?page=${currentPage}&size=${currentSize}&search=${encodeURIComponent(searchQuery)}`;
    
    try {
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.jobs) {
            renderTable(data.jobs);
            renderPagination(data.pagination);
        }
    } catch (err) {
        console.error("Failed to fetch jobs:", err);
        document.getElementById('tableBody').innerHTML = `<tr><td colspan="8" class="text-center py-4 text-danger">Failed to load jobs.</td></tr>`;
    }
}

function renderTable(jobs) {
    const tbody = document.getElementById('tableBody');
    tbody.innerHTML = '';

    if (jobs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-muted">No jobs found.</td></tr>`;
        return;
    }

    jobs.forEach(j => {
        const tr = document.createElement('tr');
        
        // Editor parsing
        const editorVersionHtml = (j.editor_name || j.editor_version) 
            ? `<span>${j.editor_name || ''}${(j.editor_name && j.editor_version) ? '/' : ''}${j.editor_version || ''}</span>`
            : `<span class="text-muted">-</span>`;
            
        // Schedule parsing
        let scheduleHtml = `<strong class="text-capitalize">${escapeHtml(j.job_type)}</strong><br>`;
        if (j.job_type === "cron") {
            scheduleHtml += `<span class="text-muted small"><i class="fa-regular fa-clock me-1"></i>${escapeHtml(j.schedule)}</span>`;
        } else if (j.job_type === "dependent") {
            scheduleHtml += `<span class="text-muted small"><i class="fa-solid fa-link me-1"></i>${escapeHtml(j.schedule)}</span>`;
        } else {
            scheduleHtml += `<span class="text-muted small">-</span>`;
        }
        
        if (j.paused) {
            scheduleHtml += `<br><span class="badge bg-warning text-dark mt-1">Paused</span>`;
        }

        // Run Date Parsing
        let lastRunHtml = `<span class="text-muted small"><i class="fa-regular fa-calendar-xmark me-1"></i>Never ran</span>`;
        if (j.last_run_starting_time) {
            try {
                const dateObj = new Date(j.last_run_starting_time);
                
                // Extract properties to detect the dummy CML date (accounting for JS 2001 parsing quirk)
                const year = dateObj.getFullYear();
                const month = dateObj.getMonth(); // 0 is January
                const date = dateObj.getDate();
                
                if ((year <= 1 || year === 2001) && month === 0 && date === 1) {
                    lastRunHtml = `<strong class="text-danger">Job Run Failed to Start</strong><br>
                                   <span class="badge badge-schedule badge-schedule-${j.last_run_status.toLowerCase()}">${escapeHtml(j.last_run_status)}</span>`;
                } else {
                    lastRunHtml = `<strong>${dateObj.toLocaleString()}</strong><br>
                                   <span class="badge badge-schedule badge-schedule-${j.last_run_status.toLowerCase()}">${escapeHtml(j.last_run_status)}</span>`;
                }
            } catch {
                lastRunHtml = `<strong>${escapeHtml(j.last_run_starting_time)}</strong>`;
            }
        }
        
        tr.innerHTML = `
            <td>
                <strong>${escapeHtml(j.name)}</strong><br>
                <span class="text-muted small badge-id">${escapeHtml(j.id)}</span>
            </td>
            <td>
                <strong>${escapeHtml(j.username)}</strong><br>
                <span class="text-muted small">${escapeHtml(j.fullname)}</span>
            </td>
            <td>
                <strong>${escapeHtml(j.project_name)}</strong>
                ${j.project_url ? `<a href="${j.project_url}" target="_blank" class="ms-1 text-primary text-decoration-none" title="Open Project"><i class="fa-solid fa-arrow-up-right-from-square small"></i></a>` : ''}
            </td>
            <td>${editorVersionHtml}</td>
            <td><code>${escapeHtml(j.script)}</code></td>
            <td>${scheduleHtml}</td>
            <td>${j.cpu} vCPU / ${j.ram} GiB</td>
            <td>${lastRunHtml}</td>
        `;
        tbody.appendChild(tr);
    });
}

function renderPagination(p) {
    const btnFirst = document.getElementById('btn-first');
    const btnPrev = document.getElementById('btn-prev');
    const btnNext = document.getElementById('btn-next');
    const btnLast = document.getElementById('btn-last');

    btnFirst.classList.toggle('disabled', !p.has_prev);
    btnPrev.classList.toggle('disabled', !p.has_prev);
    btnNext.classList.toggle('disabled', !p.has_next);
    btnLast.classList.toggle('disabled', !p.has_next);

    btnFirst.querySelector('button').onclick = p.has_prev ? () => fetchJobs(1) : null;
    btnPrev.querySelector('button').onclick = p.has_prev ? () => fetchJobs(p.prev_num) : null;
    btnNext.querySelector('button').onclick = p.has_next ? () => fetchJobs(p.next_num) : null;
    btnLast.querySelector('button').onclick = p.has_next ? () => fetchJobs(p.pages) : null;
}

let searchTimeout;
function onSearchInput(val) {
    searchQuery = val;
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        fetchJobs(1);
    }, 400); // Debounce search
}

function changePageSize(size) {
    currentSize = parseInt(size);
    fetchJobs(1);
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' })[m]);
}

async function syncJobs() {
    const btn = document.getElementById('btnSyncJobs');
    const spinner = btn.querySelector('.spinner-border');
    const btnText = btn.querySelector('.btn-text');

    // Disable button and show spinner
    btn.disabled = true;
    spinner.classList.remove('d-none');
    btnText.innerText = 'Refreshing...';

    try {
        const response = await fetch('/api/jobs/sync', { method: 'POST' });
        const data = await response.json();

        if (response.ok && data.success) {
            // Background thread successfully started. Begin polling the status.
            pollSyncStatus();
        } else {
            // Handle 429 Too Many Requests or lock rejections
            showFlashMessage(data.message || 'Failed to start job refresh.', 'danger');
            resetSyncButton();
        }
    } catch (err) {
        console.error("Failed to trigger sync:", err);
        showFlashMessage('A network error occurred while triggering refresh.', 'danger');
        resetSyncButton();
    }
}

async function pollSyncStatus() {
    const startTime = Date.now();
    
    // Clear any existing intervals just in case
    if (syncPollInterval) clearInterval(syncPollInterval);

    syncPollInterval = setInterval(async () => {
        // Hard timeout: Stop polling after 5 minutes
        if (Date.now() - startTime > 300000) {
            clearInterval(syncPollInterval);
            showFlashMessage('Sync request timed out after 5 minutes.', 'danger');
            resetSyncButton();
            return;
        }

        try {
            const response = await fetch('/api/jobs/sync/status');
            const data = await response.json();

            if (data.status === 'success') {
                clearInterval(syncPollInterval);
                showFlashMessage('Jobs refreshed successfully.', 'success');
                fetchJobs(currentPage); // Reload table with fresh data
                resetSyncButton();
            } else if (data.status === 'failed' || data.status === 'timeout') {
                clearInterval(syncPollInterval);
                showFlashMessage('Failed to refresh jobs on the server.', 'danger');
                resetSyncButton();
            }
            // If status is 'running' or 'idle', do nothing. It will poll again in 3 seconds.
            
        } catch (err) {
            console.error("Polling error:", err);
            // Don't stop polling on a single network blip, just wait for the next tick
        }
    }, 3000); // Check status every 3 seconds
}

function resetSyncButton() {
    const btn = document.getElementById('btnSyncJobs');
    const spinner = btn.querySelector('.spinner-border');
    const btnText = btn.querySelector('.btn-text');
    
    if (syncPollInterval) {
        clearInterval(syncPollInterval);
        syncPollInterval = null;
    }

    btn.disabled = false;
    spinner.classList.add('d-none');
    btnText.innerText = 'Refresh Jobs';
}

function showFlashMessage(message, type = 'success') {
    const container = document.getElementById('flash-container');
    if (!container) return;

    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show shadow-sm`;
    alertDiv.role = 'alert';
    
    const icon = type === 'success' ? 'fa-circle-check' : 'fa-circle-exclamation';
    
    alertDiv.innerHTML = `
        <i class="fa-solid ${icon} me-2"></i>${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    container.appendChild(alertDiv);

    setTimeout(() => {
        alertDiv.classList.remove('show');
        setTimeout(() => alertDiv.remove(), 150); 
    }, 5000);
}
