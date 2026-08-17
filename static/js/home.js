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

            // Construct Reason Text (Now side-by-side)
            const reasonHtml = workload.reason 
                ? `<span class="text-muted small ms-2" title="Reason: ${workload.reason}"><i class="fa-solid fa-circle-info me-1"></i>${workload.reason}</span>`
                : '';

            html += `
                <tr class="main-workload-row">
                    <td class="text-nowrap">
                        ${sub_workload_toggle}
                    </td>
                    <td>
                        <strong>${workload.workload_type}</strong>
                    </td>
                    <td>
                        <strong>${workload.user}</strong>
                        ${workload.show_full_name ? `<br><span style="color:#666666;">${workload.full_name}</span>` : ''}
                    </td>
                    <td>
                        <strong>${workload.project}</strong>${workloadUrlHtml}<br>
                        <span style="color:#666666;">${nameHtml}</span>
                    </td>
                    <td>
                        ${editorVersionHtml}
                    </td>
                    <td>
                        <!-- IMPROVED NAMESPACE LINK -->
                        <a href="${workload.namespace_url}" target="_blank" class="text-primary fw-semibold text-decoration-none" title="View in Kubernetes">${workload.namespace} <i class="fa-solid fa-arrow-up-right-from-square small ms-1"></i></a><br>
                        <span class="badge-id text-muted small">${workload.id}</span>
                    </td>
                    <td>
                        <!-- IMPROVED STATUS & REASON -->
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
                            <td>
                                <div class="ps-4">
                                    <i class="fa-solid fa-level-up fa-rotate-90 text-muted"></i>
                                </div>
                            </td>
                            <td><div class="ps-2">${sub.workload_type}</div></td>
                            <td>
                                <div class="ps-2">
                                    ${sub.user}
                                    ${fullname}
                                </div>
                            </td>
                            <td>
                                <div class="ps-2">
                                    <strong>${sub.project}</strong>${subWorkloadUrlHtml}<br>
                                    <span style="color:#888888;">${subNameHtml}</span>
                                </div>
                            </td>
                            <td>
                                <div class="ps-2">
                                    ${subEditorVersionHtml}
                                </div>
                            </td>
                            <td>
                                <div class="ps-2">
                                    <!-- IMPROVED SUB-NAMESPACE LINK -->
                                    <a href="${sub.namespace_url}" target="_blank" class="text-primary fw-semibold text-decoration-none" title="View in Kubernetes">${sub.namespace} <i class="fa-solid fa-arrow-up-right-from-square small ms-1"></i></a><br>
                                    <span class="badge-id text-muted small">${sub.id}</span>
                                </div>
                            </td>
                            <td>
                                <!-- IMPROVED SUB-STATUS & REASON -->
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


function updateDataList() {
    let data = (SEARCH_FILTER == SearchFilters.ALL) ? SEARCH_DATA[SearchFilters.USERNAME] : SEARCH_DATA[SEARCH_FILTER];
    let html = '';
    
    // Safety check in case the search filter array doesn't exist in SEARCH_DATA
    if(data && Array.isArray(data)) {
        data.forEach(item => {
            html += `<option value="${item}">`;
        });
    }

    document.getElementById("search-data").innerHTML = html;
}


function updateSearch() {
    if (Object.values(SearchFilters).includes(SEARCH_FILTER)) {
        document.getElementById("search-filter").value = (SEARCH_FILTER == SearchFilters.ALL) ? SearchFilters.USERNAME : SEARCH_FILTER;
        document.getElementById("search-value-input").value = SEARCH_VALUE;
    }
    else {
        SEARCH_FILTER = SearchFilters.ALL;
        document.getElementById("search-value-input").value = "";
        document.getElementById("search-filter").value = SearchFilters.USERNAME;
    }

    updateDataList();
}


function searchOnEnter(event) {
    if (event.key === "Enter") {
        if (SEARCH_FILTER_CHANGED) {
            SEARCH_FILTER_CHANGED = false;
            fetchData("first", null, null, event.target.value);
        }
        else {
            fetchData(null, null, null, event.target.value);
        }
    }
}


function searchInputFocus() {
    if (SEARCH_FILTER == SearchFilters.ALL) {
        const searchFilter = document.getElementById("search-filter").value;
        const isValidSearchFilter = Object.values(SearchFilters).includes(searchFilter);
        SEARCH_FILTER_CHANGED = isValidSearchFilter && searchFilter !== SEARCH_FILTER;
        SEARCH_FILTER = (isValidSearchFilter) ? searchFilter : SEARCH_FILTER;
        updateDataList();
    }
}


function setSearchFilter(value) {
    const isValidSearchFilter = Object.values(SearchFilters).includes(value);
    SEARCH_FILTER_CHANGED = isValidSearchFilter && value !== SEARCH_FILTER;
    SEARCH_FILTER = (isValidSearchFilter) ? value : SEARCH_FILTER;
    updateDataList();
}


function fetchData(direction = null, pageSize = null, filter = null, searchValue=null, orderBy=null, desc=null) {
    const baseUrl = `${window.location.href}api/data`;

    const isValidFilter = Object.values(WorkloadFilters).includes(filter);
    const filterChanged = isValidFilter && filter !== FILTER;
    let toBeFilter = (isValidFilter) ? filter : FILTER;

    const isValidSearchFilter = Object.values(SearchFilters).includes(SEARCH_FILTER);
    let toBeSearchFilter = (isValidSearchFilter) ? SEARCH_FILTER : SearchFilters.ALL;

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

    const params = {
        pageSize: toBePageSize,
        pageNumber: toBePageNumber,
        filter: toBeFilter,
        searchFilter: toBeSearchFilter,
        searchValue: (searchValue === null) ? SEARCH_VALUE : searchValue,
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
            // we are assuming server is always right
            PAGE_SIZE = data.page_size;
            FILTER = data.filter;
            SEARCH_FILTER = data.search_filter;
            SEARCH_VALUE = data.search_value;
            SEARCH_DATA = JSON.parse(data.search_data);

            ORDER_BY_FILTER = data.order_by_filter;
            ORDER_BY_DESC = data.desc;

            NUM_SESSIONS = data.num_sessions;
            NUM_APPLICATIONS = data.num_applications;
            NUM_JOBS = data.num_jobs;
            
            // Allow graceful fallback if the backend hasn't been updated to emit this payload key yet
            NUM_ORPHANS = data.num_orphans || 0; 
            
            TOTAL_WORKLOAD = data.total_number_of_workload;

            updatePagination();
            updateFilter();
            updateSearch();
            updateSort();
            renderTable(data.payload);
        })
        .catch(error => console.error('Error fetching data:', error));
}


function refreshData() {
    const loadingModalEl = document.getElementById('loadingModal');
    const errorModalEl = document.getElementById('errorModal');
    const loadingModal = bootstrap.Modal.getOrCreateInstance(loadingModalEl);
    const errorModal = bootstrap.Modal.getOrCreateInstance(errorModalEl);

    loadingModal.show();

    const baseUrl = `${window.location.href}api/refresh`;

    const params = {
        pageSize: PAGE_SIZE,
        pageNumber: CURRENT_PAGE,
        filter: FILTER,
        searchFilter: SEARCH_FILTER,
        searchValue: SEARCH_VALUE,
        orderBy: ORDER_BY_FILTER,
        desc: ORDER_BY_DESC
    };

    const url = new URL(baseUrl);
    url.search = new URLSearchParams(params).toString();

    fetch(url)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            MAX_PAGES = data.max_pages;
            CURRENT_PAGE = data.page_number;
            PAGE_SIZE = data.page_size;
            FILTER = data.filter;
            SEARCH_FILTER = data.search_filter;
            SEARCH_VALUE = data.search_value;
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
            updateSearch();
            updateSort();
            renderTable(data.payload);

            setTimeout(() => { loadingModal.hide(); }, 500);
        })
        .catch(error => {
            console.error('Error fetching data:', error);
            
            setTimeout(() => {
                loadingModalEl.addEventListener('hidden.bs.modal', function triggerErrorModal() {
                    errorModal.show();
                }, { once: true });
                
                loadingModal.hide();
            }, 500);
        });
}


function filterButtonClickHandler(workloadType, btn) {
    if (btn.classList.contains('active'))
        return

    fetchData(null, null, workloadType);
}


function downloadReport() {
    fetch('/api/report')
    .then(response => {
        if (response.ok) return response.blob(); 
        throw new Error('Network response was not ok.');
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
    })
    .catch(error => console.error('Download failed:', error));
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

    fetchData(null, null, null, null, orderBy, isDesc);
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


document.addEventListener('DOMContentLoaded', function () {
    const pageSizeDropdownMenu = document.getElementById('page-size-dropdown');
    pageSizeDropdownMenu.addEventListener('change', (event) => {
        const selectedValue = Number.parseInt(event.target.value, 10);
        fetchData(null, selectedValue);
    });

    // Poll every 1 min
    setInterval(fetchData, 60000);
});


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
    filterOrphansCount.classList.value = "badge bg-secondary";

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
        filterOrphansCount.classList.value = "badge";
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


function stopAllSessions() {
    if(!confirm(`Are you sure you want to delete all running sessions?`)) return;

    fetch('/api/delete_sessions', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert("All running sessions have been stopped");
            fetchData();
        }
    })
    .catch((error) => {
        console.error('Error:', error);
    });
}