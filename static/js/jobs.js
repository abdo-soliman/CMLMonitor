let currentPage = 1;
let currentSize = 25;
let syncPollInterval = null;

// Initialize the generic Multi Search function
const ADVANCED_SEARCH_CONFIG = [
    { label: "Name", value: "name" },
    { label: "Username", value: "username" },
    { label: "Project", value: "project" },
    { label: "Script", value: "script" },
    { label: "Job Type", value: "job_type" },
    { label: "Status", value: "status" }
];

let SEARCH_DATA = {};
let advancedSearchObj = null;

document.addEventListener('DOMContentLoaded', () => {
    advancedSearchObj = initAdvancedSearch(
        'advanced-search-search-container', 
        'advanced-search-input', 
        'advanced-search-dropdown', 
        'advanced-search-param-hint', 
        'advanced-search-chips', 
        ADVANCED_SEARCH_CONFIG, 
        () => SEARCH_DATA, 
        (filters) => fetchJobs(1)
    );

    fetchJobs(1);
    // Poll every 60 seconds
    setInterval(() => fetchJobs(currentPage), 60000);
});


function initAdvancedSearch(containerId, inputId, dropdownId, hintId, chipsId, config, getSearchDataCallback, onSearchCallback) {
    const inputEl = document.getElementById(inputId);
    const dropdownEl = document.getElementById(dropdownId);
    const hintEl = document.getElementById(hintId);
    const chipsContainer = document.getElementById(chipsId);
    const containerEl = document.getElementById(containerId);

    let activeFilters = [];
    let isSelectingParam = true;
    let currentSelectedParam = null;
    let activeDropdownIndex = -1;

    // Create a safe identifier for the dynamic window function (replace hyphens with underscores)
    const safeContainerId = containerId.replace(/-/g, '_');

    function renderChips() {
        chipsContainer.innerHTML = '';
        activeFilters.forEach((f, idx) => {
            const chip = document.createElement('div');
            chip.className = 'advanced-search-chip';
            const conf = config.find(c => c.value === f.param);
            const label = conf ? conf.label : f.param;
            chip.innerHTML = `
                <span class="cancel-btn me-2" onclick="window.removeAdvancedSearchFilter_${safeContainerId}(${idx})"><i class="fa-solid fa-circle-xmark"></i></span>
                <span class="param-name">${escapeHtml(label)}:</span> 
                <span class="param-value">${escapeHtml(f.value)}</span> 
            `;
            chipsContainer.appendChild(chip);
        });
    }

    window[`removeAdvancedSearchFilter_${safeContainerId}`] = function(idx) {
        activeFilters.splice(idx, 1);
        renderChips();
        resetInput();
        onSearchCallback(activeFilters);
        inputEl.focus();
    };

    function resetInput() {
        isSelectingParam = true;
        currentSelectedParam = null;
        inputEl.value = '';
        inputEl.placeholder = activeFilters.length === 0 ? 'Search...' : '';
        hintEl.classList.add('d-none');
        hintEl.innerText = '';
        hideDropdown();
    }

    function getAvailableParams() {
        const usedParams = activeFilters.map(f => f.param);
        return config.filter(c => !usedParams.includes(c.value));
    }

    function showDropdown(items, isParamMode) {
        dropdownEl.innerHTML = '';
        activeDropdownIndex = -1;
        if (!items || items.length === 0) {
            hideDropdown();
            return;
        }
        items.forEach((item, idx) => {
            const div = document.createElement('div');
            div.className = 'advanced-search-dropdown-item';
            div.innerText = isParamMode ? item.label : String(item);
            div.onmousedown = (e) => {
                e.preventDefault(); 
                if (isParamMode) selectParam(item);
                else addFilter(item);
            };
            dropdownEl.appendChild(div);
        });
        dropdownEl.style.display = 'block';
    }

    function hideDropdown() {
        // Clear HTML so hidden Ghost items don't intercept Enter key events
        dropdownEl.innerHTML = ''; 
        dropdownEl.style.display = 'none';
        activeDropdownIndex = -1;
    }

    function selectParam(paramObj) {
        isSelectingParam = false;
        currentSelectedParam = paramObj;
        inputEl.value = '';
        inputEl.placeholder = '';
        hintEl.innerText = paramObj.label + ':';
        hintEl.classList.remove('d-none');
        inputEl.focus();
        showValues('');
    }

    function addFilter(value) {
        if (!value || !String(value).trim()) return;
        activeFilters.push({ param: currentSelectedParam.value, value: String(value).trim() });
        renderChips();
        resetInput();
        onSearchCallback(activeFilters);

        // Explicitly force focus and immediately show the params again
        inputEl.focus();
        showParams('');
    }

    function showParams(filterText = '') {
        const available = getAvailableParams();
        const filtered = available.filter(c => c.label.toLowerCase().includes(filterText.toLowerCase()));
        showDropdown(filtered, true);
    }

    function showValues(filterText = '') {
        const searchData = getSearchDataCallback();
        let values = searchData[currentSelectedParam.value] || [];
        if (filterText) {
            values = values.filter(v => String(v).toLowerCase().includes(filterText.toLowerCase()));
        }
        showDropdown(values, false);
    }

    function updateDropdownSelection() {
        const items = dropdownEl.querySelectorAll('.advanced-search-dropdown-item');
        items.forEach((item, idx) => {
            if (idx === activeDropdownIndex) item.classList.add('active');
            else item.classList.remove('active');
        });
        if (activeDropdownIndex >= 0 && items[activeDropdownIndex]) {
            items[activeDropdownIndex].scrollIntoView({ block: 'nearest' });
        }
    }

    // Force focus to input if the user clicks anywhere in the empty space of the search bar
    containerEl.addEventListener('click', (e) => {
        if (e.target !== inputEl && e.target !== dropdownEl && !e.target.closest('.cancel-btn')) {
            inputEl.focus();
        }
    });

    inputEl.addEventListener('focus', () => {
        if (isSelectingParam) showParams(inputEl.value);
        else showValues(inputEl.value);
    });

    inputEl.addEventListener('blur', () => {
        setTimeout(() => {
            // Only hide the dropdown if focus actually left the search container
            if (!containerEl.contains(document.activeElement)) {
                hideDropdown();
                if (!isSelectingParam && inputEl.value.trim() === '') {
                    resetInput();
                }
            }
        }, 150);
    });

    inputEl.addEventListener('input', (e) => {
        const val = e.target.value;
        if (isSelectingParam) showParams(val);
        else showValues(val);
    });

    inputEl.addEventListener('keydown', (e) => {
        const isDropdownVisible = dropdownEl.style.display === 'block';
        const items = isDropdownVisible ? dropdownEl.querySelectorAll('.advanced-search-dropdown-item') : [];
        
        if (e.key === 'Backspace' && inputEl.value === '') {
            if (!isSelectingParam) {
                resetInput();
                showParams('');
            } else if (activeFilters.length > 0) {
                activeFilters.pop();
                renderChips();
                onSearchCallback(activeFilters);
                showParams('');
            }
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (activeDropdownIndex < items.length - 1) {
                activeDropdownIndex++;
                updateDropdownSelection();
            }
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (activeDropdownIndex > 0) {
                activeDropdownIndex--;
                updateDropdownSelection();
            }
        } else if (e.key === 'Enter') {
            e.preventDefault();
            
            if (activeDropdownIndex >= 0 && activeDropdownIndex < items.length) {
                items[activeDropdownIndex].onmousedown(new MouseEvent('mousedown'));
            } else {
                if (isSelectingParam && items.length > 0) {
                    items[0].onmousedown(new MouseEvent('mousedown'));
                } else if (!isSelectingParam) {
                    if (inputEl.value.trim() !== '') {
                        addFilter(inputEl.value);
                    } else if (items.length > 0) {
                        items[0].onmousedown(new MouseEvent('mousedown'));
                    }
                }
            }
        }
    });

    return {
        getActiveFilters: () => activeFilters,
        clearFilters: () => {
            activeFilters = [];
            renderChips();
            resetInput();
        }
    };
}


async function fetchJobs(page = null) {
    if (page) currentPage = page;
    
    const searchFiltersPayload = advancedSearchObj ? JSON.stringify(advancedSearchObj.getActiveFilters()) : '[]';

    const params = new URLSearchParams({
        page: currentPage,
        size: currentSize,
        searchFilters: searchFiltersPayload
    });
    
    const url = `/api/jobs?${params.toString()}`;
    
    try {
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.jobs) {
            SEARCH_DATA = data.search_data;
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
                const month = dateObj.getMonth();
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

    btn.disabled = true;
    spinner.classList.remove('d-none');
    btnText.innerText = 'Refreshing...';

    try {
        const response = await fetch('/api/jobs/sync', { method: 'POST' });
        const data = await response.json();

        if (response.ok && data.success) {
            pollSyncStatus();
        } else {
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
    if (syncPollInterval) clearInterval(syncPollInterval);

    syncPollInterval = setInterval(async () => {
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
                fetchJobs(currentPage); 
                resetSyncButton();
            } else if (data.status === 'failed' || data.status === 'timeout') {
                clearInterval(syncPollInterval);
                showFlashMessage('Failed to refresh jobs on the server.', 'danger');
                resetSyncButton();
            }
        } catch (err) {
            console.error("Polling error:", err);
        }
    }, 3000); 
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
    alertDiv.className = `alert alert-${type} alert-dismissible fade show shadow-sm text-center`;
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
