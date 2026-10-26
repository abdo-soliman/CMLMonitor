let refreshPollInterval = null;

const ADVANCED_SEARCH_CONFIG = [
    { label: "Username", value: "username" },
    { label: "Project", value: "project" },
    { label: "Session Name", value: "session_name" },
    { label: "Namespace", value: "namespace" },
    { label: "Session ID", value: "session_id" },
    { label: "Status", value: "status" },
    { label: "Age", value: "age" },
    { label: "Resources", value: "resources" }
];

let advancedSearchObj = null;

document.addEventListener('DOMContentLoaded', function () {
    advancedSearchObj = initAdvancedSearch(
        'advanced-search-search-container', 
        'advanced-search-input', 
        'advanced-search-dropdown', 
        'advanced-search-param-hint', 
        'advanced-search-chips', 
        ADVANCED_SEARCH_CONFIG, 
        () => SEARCH_DATA, 
        (filters) => fetchData("first")
    );

    const pageSizeDropdownMenu = document.getElementById('page-size-dropdown');
    pageSizeDropdownMenu.addEventListener('change', (event) => {
        const selectedValue = Number.parseInt(event.target.value, 10);
        fetchData(null, selectedValue);
    });

    fetchData();
    setInterval(fetchData, 60000);
});

// --- ADVANCED SEARCH COMPONENT LOGIC ---
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

    // 1. Create a safe identifier for the dynamic window function (replace hyphens with underscores)
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

    // Use the sanitized name for the global window function
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
        // 3. Clear HTML so hidden Ghost items don't intercept Enter key events
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
        
        // 2. Explicitly force focus and immediately show the params again
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
// --- END SEARCH LOGIC ---


function renderTable(workloads) {
    const tbody = document.getElementById('table-body');
    let html = '';
        workloads.forEach(workload => {
            let sub_workload_toggle = `<span class="d-inline-block me-1" style="width: 20px;"></span>`;
            if (workload.has_sub_workload) {
                let icon = (EXPANDED_ROWS.includes(workload.id)) ? `<i class="fa-solid fa-chevron-down fa-fw"></i>` : `<i class="fa-solid fa-chevron-right fa-fw"></i>`;
                sub_workload_toggle = `
                    <button class="btn btn-sm btn-link p-0 text-decoration-none text-dark me-1" onclick="toggleSubWorkload('${workload.id}', this)">
                        ${icon}
                    </button>
                `;
            }

            // Construct Editor / Version Text
            const editorVersionHtml = (workload.editor_name || workload.editor_version) 
                ? `<span>${workload.editor_name || ''}${(workload.editor_name && workload.editor_version) ? '/' : ''}${workload.editor_version || ''}</span>`
                : `<span class="text-muted">-</span>`;

            // Construct Workload URL Button
            const workloadUrlHtml = workload.workload_url
                ? `<a href="${workload.workload_url}" target="_blank" class="ms-1 text-primary text-decoration-none" title="Open Workload"><i class="fa-solid fa-arrow-up-right-from-square small"></i></a>`
                : '';

            // Construct Name (Handle Nulls)
            const nameHtml = workload.name ? workload.name : `<em class="text-muted small">N/A</em>`;

            const reasonHtml = workload.reason 
                ? `<span class="text-muted small ms-2" title="Reason: ${workload.reason}"><i class="fa-solid fa-circle-info me-1"></i>${workload.reason}</span>`
                : '';

            html += `
                <tr class="main-workload-row">
                    <td class="text-nowrap">
                        ${sub_workload_toggle}
                    </td>
                    <td><strong>${workload.workload_type}</strong></td>
                    <td>
                        <strong>${workload.user}</strong>
                        ${workload.show_full_name ? `<br><span style="color:#666666;">${workload.full_name}</span>` : ''}
                    </td>
                    <td>
                        <strong>${workload.project}</strong>${workloadUrlHtml}<br>
                        <span style="color:#666666;">${nameHtml}</span>
                    </td>
                    <td>${editorVersionHtml}</td>
                    <td>
                        <a href="${workload.namespace_url}" target="_blank" class="text-primary fw-semibold text-decoration-none" title="View in Kubernetes">${workload.namespace} <i class="fa-solid fa-arrow-up-right-from-square small ms-1"></i></a><br>
                        <span class="badge-id text-muted small">${workload.id}</span>
                    </td>
                    <td>
                        <div class="d-flex align-items-center flex-wrap">
                            <span class="badge badge-schedule badge-schedule-${workload.status.toLowerCase()}">${workload.status}</span>
                            ${reasonHtml}
                        </div>
                    </td>
                    <td>${workload.age}</td>
                    <td>${workload["Resource Profile"]}</td>
                </tr>
            `;

            if (workload.has_sub_workload) {
                for (const sub of workload.sub_workload) {
                    let fullname = sub.show_full_name ? `<br><span style="color:#888888;">${sub.full_name}</span>` : '';
                    
                    let subEditorVersionHtml = (sub.editor_name || sub.editor_version) 
                        ? `<span>${sub.editor_name || ''}${(sub.editor_name && sub.editor_version) ? '/' : ''}${sub.editor_version || ''}</span>`
                        : `<span class="text-muted">-</span>`;

                    let subWorkloadUrlHtml = sub.workload_url
                        ? `<a href="${sub.workload_url}" target="_blank" class="ms-1 text-primary text-decoration-none" title="Open Workload"><i class="fa-solid fa-arrow-up-right-from-square small"></i></a>`
                        : '';

                    let subNameHtml = sub.name ? sub.name : `<em class="text-muted small">N/A</em>`;
                    
                    let subReasonHtml = sub.reason 
                        ? `<span class="text-muted small ms-2" title="Reason: ${sub.reason}"><i class="fa-solid fa-circle-info me-1"></i>${sub.reason}</span>`
                        : '';

                    html += `
                        <tr class="sub-workload-row sub-workload-${workload.id}" style="display: ${EXPANDED_ROWS.includes(workload.id) ? "table-row" : "none"};">
                            <td><div class="ps-4"><i class="fa-solid fa-level-up fa-rotate-90 text-muted"></i></div></td>
                            <td><div class="ps-2">${sub.workload_type}</div></td>
                            <td><div class="ps-2">${sub.user}${fullname}</div></td>
                            <td>
                                <div class="ps-2">
                                    <strong>${sub.project}</strong>${subWorkloadUrlHtml}<br>
                                    <span style="color:#888888;">${subNameHtml}</span>
                                </div>
                            </td>
                            <td><div class="ps-2">${subEditorVersionHtml}</div></td>
                            <td>
                                <div class="ps-2">
                                    <a href="${sub.namespace_url}" target="_blank" class="text-primary fw-semibold text-decoration-none" title="View in Kubernetes">${sub.namespace} <i class="fa-solid fa-arrow-up-right-from-square small ms-1"></i></a><br>
                                    <span class="badge-id text-muted small">${sub.id}</span>
                                </div>
                            </td>
                            <td>
                                <div class="d-flex align-items-center flex-wrap">
                                    <span class="badge badge-schedule badge-schedule-${sub.status.toLowerCase()}">${sub.status}</span>
                                    ${subReasonHtml}
                                </div>
                            </td>
                            <td>${sub.age}</td>
                            <td>${sub["Resource Profile"]}</td>
                        </tr>
                    `;
                }
            }
        });

        tbody.innerHTML = html;
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' })[m]);
}


function fetchData(direction = null, pageSize = null, filter = null, orderBy=null, desc=null) {
    const baseUrl = `${window.location.href}api/data`;

    const isValidFilter = Object.values(WorkloadFilters).includes(filter);
    const filterChanged = isValidFilter && filter !== FILTER;
    let toBeFilter = (isValidFilter) ? filter : FILTER;

    let toBePageNumber = CURRENT_PAGE;
    if (filterChanged || direction === "first")
        toBePageNumber = 1;
    else if (direction === "previous")
        toBePageNumber = (toBePageNumber > 1) ? toBePageNumber-1 : 1;
    else if (direction === "next")
        toBePageNumber = (toBePageNumber >= MAX_PAGES) ? MAX_PAGES : toBePageNumber+1;
    else if (direction === "last")
        toBePageNumber = MAX_PAGES;

    const isValidPageSize = Object.values(PageSizes).includes(pageSize);
    let toBePageSize = (isValidPageSize) ? pageSize : PAGE_SIZE;

    const isValidOrderByFilter = Object.values(OrderByFilters).includes(orderBy);
    let toBeOrderByFilter = (isValidOrderByFilter) ? orderBy : ORDER_BY_FILTER;

    let toBeDesc = (desc === null) ? ORDER_BY_DESC : desc;

    const searchFiltersPayload = advancedSearchObj ? JSON.stringify(advancedSearchObj.getActiveFilters()) : '[]';

    const params = {
        pageSize: toBePageSize,
        pageNumber: toBePageNumber,
        filter: toBeFilter,
        searchFilters: searchFiltersPayload,
        orderBy: toBeOrderByFilter,
        desc: toBeDesc
    };

    const url = new URL(baseUrl);
    url.search = new URLSearchParams(params).toString();

    fetch(url)
        .then(response => response.json())
        .then(data => {
            MAX_PAGES = data.max_pages;
            CURRENT_PAGE = data.page_number;
            PAGE_SIZE = data.page_size;
            FILTER = data.filter;
            
            SEARCH_DATA = JSON.parse(data.search_data);

            ORDER_BY_FILTER = data.order_by_filter;
            ORDER_BY_DESC = data.desc;

            NUM_SESSIONS = data.num_sessions;
            NUM_APPLICATIONS = data.num_applications;
            NUM_JOBS = data.num_jobs;
            NUM_ORPHANS = data.num_orphans || 0; 
            TOTAL_WORKLOAD = data.total_number_of_workload;

            updatePagination();
            updateFilter();
            updateSort();
            renderTable(data.payload);
        })
        .catch(error => console.error('Error fetching data:', error));
}


async function refreshData() {
    const btn = document.getElementById('btnRefreshData');
    const spinner = btn.querySelector('.spinner-border');
    const btnText = btn.querySelector('.btn-text');

    btn.disabled = true;
    spinner.classList.remove('d-none');
    btnText.innerText = 'Refreshing...';

    try {
        const response = await fetch('/api/refresh', { method: 'POST' });
        const data = await response.json();

        if (response.ok && data.success) {
            pollRefreshStatus();
        } else {
            showFlashMessage(data.message || 'Failed to start workload refresh.', 'danger');
            resetRefreshButton();
        }
    } catch (err) {
        console.error("Failed to trigger refresh:", err);
        showFlashMessage('A network error occurred while triggering refresh.', 'danger');
        resetRefreshButton();
    }
}


function pollRefreshStatus() {
    const startTime = Date.now();
    
    // Clear any existing intervals just in case
    if (refreshPollInterval) clearInterval(refreshPollInterval);

    refreshPollInterval = setInterval(async () => {
        // Hard timeout: Stop polling after 5 minutes
        if (Date.now() - startTime > 300000) {
            clearInterval(refreshPollInterval);
            showFlashMessage('Sync request timed out after 5 minutes.', 'danger');
            resetRefreshButton();
            return;
        }

        try {
            const response = await fetch('/api/refresh/status');
            const data = await response.json();

            if (data.status === 'success') {
                clearInterval(refreshPollInterval);
                showFlashMessage('Workloads refreshed successfully.', 'success');
                fetchData(); 
                resetRefreshButton();
            } else if (data.status === 'failed' || data.status === 'timeout') {
                clearInterval(refreshPollInterval);
                showFlashMessage('Failed to refresh workloads on the server.', 'danger');
                resetRefreshButton();
            }
        } catch (err) {
            console.error("Polling error:", err);
        }
    }, 3000); 
}


function resetRefreshButton() {
    const btn = document.getElementById('btnRefreshData');
    if (!btn) return;
    const spinner = btn.querySelector('.spinner-border');
    const btnText = btn.querySelector('.btn-text');
    
    if (refreshPollInterval) {
        clearInterval(refreshPollInterval);
        refreshPollInterval = null;
    }

    btn.disabled = false;
    spinner.classList.add('d-none');
    btnText.innerText = 'Refresh Data';
}


function showFlashMessage(message, type = 'success') {
    const container = document.getElementById('flash-container');
    if (!container) return;

    container.className = 'position-fixed top-0 start-50 translate-middle-x p-3';
    container.style.minWidth = '350px';

    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show shadow-sm text-center`;
    alertDiv.role = 'alert';
    
    const icon = type === 'success' ? 'fa-circle-check' : 'fa-circle-exclamation';
    
    alertDiv.innerHTML = `
        <i class="fa-solid ${icon} me-2"></i>${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    container.appendChild(alertDiv);

    // Auto dismiss after 5 seconds
    setTimeout(() => {
        alertDiv.classList.remove('show');
        setTimeout(() => alertDiv.remove(), 150); 
    }, 5000);
}


function filterButtonClickHandler(workloadType, btn) {
    if (btn.classList.contains('active'))
        return

    fetchData(null, null, workloadType);
}


function downloadReport() {
    const btn = document.getElementById('btnDownloadReport');
    const spinner = btn.querySelector('.spinner-border');
    const icon = btn.querySelector('.download-icon');
    
    btn.disabled = true;
    spinner.classList.remove('d-none');
    icon.classList.add('d-none');

    fetch('/api/report')
    .then(async response => {
        if (response.ok) return response.blob(); 
        
        let errMsg = 'Network response was not ok.';
        try {
            const errData = await response.json();
            if (errData.error) errMsg = errData.error;
        } catch (e) {}
        
        throw new Error(errMsg);
    })
    .then(blob => {
        const url = window.URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;

        const date = new Date(); 
        const formattedDate = date.toISOString().split('T')[0];
        a.download = `report_${formattedDate}.xlsx`; 

        document.body.appendChild(a);
        a.click(); 
        
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
        showFlashMessage('Report downloaded successfully.', 'success');
    })
    .catch(error => {
        console.error('Download failed:', error);
        showFlashMessage(`Download failed: ${error.message}`, 'danger');
    })
    .finally(() => {
        btn.disabled = false;
        spinner.classList.add('d-none');
        icon.classList.remove('d-none');
    });
}


function toggleSort(orderBy, headerElement) {
    let currentOrder = headerElement.getAttribute('data-order');
    
    let newOrder = (currentOrder === 'asc') ? 'desc' : 'asc';
    let isDesc = (newOrder === 'desc');

    const allSortHeaders = document.querySelectorAll('th[data-order]');
    allSortHeaders.forEach(th => {
        th.setAttribute('data-order', 'none');
        const icon = th.querySelector('.sort-icon');
        if (icon) {
            icon.className = 'fa-solid fa-sort text-muted sort-icon ms-1';
        }
    });

    headerElement.setAttribute('data-order', newOrder);
    const activeIcon = headerElement.querySelector('.sort-icon');
    
    if (newOrder === 'asc') {
        activeIcon.className = 'fa-solid fa-caret-up sort-icon ms-1'; 
    } else {
        activeIcon.className = 'fa-solid fa-caret-down sort-icon ms-1';
    }

    fetchData(null, null, null, orderBy, isDesc);
}


function updateSort() {
    const allSortHeaders = document.querySelectorAll('th[data-order]');
    allSortHeaders.forEach(th => {
        th.setAttribute('data-order', 'none');
        const icon = th.querySelector('.sort-icon');
        if (icon) {
            icon.className = 'fa-solid fa-sort text-muted sort-icon ms-1';
        }
    });

    let selectedHeader = null;
    if (ORDER_BY_FILTER === OrderByFilters.AGE) {
        selectedHeader = document.getElementById('ageColumnHeader');
    }
    else if (ORDER_BY_FILTER === OrderByFilters.RESOURCES) {
        selectedHeader = document.getElementById('resourcesColumnHeader');
    }
    else {
        return
    }

    const activeIcon = selectedHeader.querySelector('.sort-icon');
    if (ORDER_BY_DESC) {
        selectedHeader.setAttribute('data-order', 'desc');
        activeIcon.className = 'fa-solid fa-caret-down sort-icon ms-1';
    }
    else {
        activeIcon.className = 'fa-solid fa-caret-up sort-icon ms-1'; 
        selectedHeader.setAttribute('data-order', 'asc');
    }
}


function toggleSubWorkload(workloadId, btnElement) {
    const subRows = document.querySelectorAll('.sub-workload-' + workloadId);
    const icon = btnElement.querySelector('i');

    if (EXPANDED_ROWS.includes(workloadId)) {
        subRows.forEach(row => row.style.display = 'none');
        EXPANDED_ROWS = EXPANDED_ROWS.filter(function (id) { return id !== workloadId; });
        icon.classList.remove('fa-chevron-down');
        icon.classList.add('fa-chevron-right');
    }
    else {
        subRows.forEach(row => row.style.display = 'table-row');
        EXPANDED_ROWS.push(workloadId);
        icon.classList.remove('fa-chevron-right');
        icon.classList.add('fa-chevron-down');
    }
}


function updatePagination() {
    const firstPageButton = document.getElementById('first-page-button');
    const previousPageButton = document.getElementById('previous-page-button');
    const lastPageButton = document.getElementById('last-page-button');
    const nextPageButton = document.getElementById('next-page-button');
    const pageSizeDropdownMenu = document.getElementById('page-size-dropdown');

    pageSizeDropdownMenu.value = PAGE_SIZE;

    firstPageButton.classList.remove("disabled");
    previousPageButton.classList.remove("disabled");
    lastPageButton.classList.remove("disabled");
    nextPageButton.classList.remove("disabled");

    if (CURRENT_PAGE == 1) {
        firstPageButton.classList.add("disabled");
        previousPageButton.classList.add("disabled");
        lastPageButton.classList.remove("disabled");
        nextPageButton.classList.remove("disabled");
    }
    else if (CURRENT_PAGE == MAX_PAGES) {
        firstPageButton.classList.remove("disabled");
        previousPageButton.classList.remove("disabled");
        lastPageButton.classList.add("disabled");
        nextPageButton.classList.add("disabled");
    }

    if (MAX_PAGES <= 1) {
        firstPageButton.classList.add("disabled");
        previousPageButton.classList.add("disabled");
        lastPageButton.classList.add("disabled");
        nextPageButton.classList.add("disabled");
    }
}


function updateFilter() {
    const filterButtonAll = document.getElementById('filter-btn-all');
    const filterButtonSessions = document.getElementById('filter-btn-sessions');
    const filterButtonApplications = document.getElementById('filter-btn-applications');
    const filterButtonJobs = document.getElementById('filter-btn-jobs');
    const filterButtonOrphans = document.getElementById('filter-btn-orphans');

    const filterAllCount = document.getElementById("filter-all-count");
    const filterSessionsCount = document.getElementById("filter-sessions-count");
    const filterApplicationsCount = document.getElementById("filter-applications-count");
    const filterJobsCount = document.getElementById("filter-jobs-count");
    const filterOrphansCount = document.getElementById("filter-orphans-count");

    // Reset styles
    filterButtonAll.classList.value = "btn btn-outline-secondary";
    filterButtonSessions.classList.value = "btn btn-outline-secondary";
    filterButtonApplications.classList.value = "btn btn-outline-secondary";
    filterButtonJobs.classList.value = "btn btn-outline-secondary";
    filterButtonOrphans.classList.value = "btn btn-outline-secondary";
    
    filterAllCount.classList.value = "badge bg-secondary";
    filterSessionsCount.classList.value = "badge bg-secondary";
    filterApplicationsCount.classList.value = "badge bg-secondary";
    filterJobsCount.classList.value = "badge bg-secondary";
    if(filterOrphansCount) filterOrphansCount.classList.value = "badge bg-secondary";

    // Apply active styles
    if (FILTER === WorkloadFilters.SESSION) {
        filterButtonSessions.classList.value = "btn btn-primary active";
        filterSessionsCount.classList.value = "badge";
    }
    else if (FILTER === WorkloadFilters.APPLICATION) {
        filterButtonApplications.classList.value = "btn btn-primary active";
        filterApplicationsCount.classList.value = "badge";
    }
    else if (FILTER === WorkloadFilters.JOB) {
        filterButtonJobs.classList.value = "btn btn-primary active";
        filterJobsCount.classList.value = "badge";
    }
    else if (FILTER === WorkloadFilters.ORPHAN) {
        filterButtonOrphans.classList.value = "btn btn-primary active";
        if(filterOrphansCount) filterOrphansCount.classList.value = "badge";
    }
    else {
        filterButtonAll.classList.value = "btn btn-primary active";
        filterAllCount.classList.value = "badge";
    }

    // Update counts
    filterAllCount.textContent = TOTAL_WORKLOAD;
    filterSessionsCount.textContent = NUM_SESSIONS;
    filterApplicationsCount.textContent = NUM_APPLICATIONS;
    filterJobsCount.textContent = NUM_JOBS;
    if (filterOrphansCount) filterOrphansCount.textContent = NUM_ORPHANS;
}
