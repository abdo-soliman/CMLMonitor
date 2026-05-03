function renderTable(workloads) {
    const tbody = document.getElementById('table-body');
    let html = '';
        workloads.forEach(workload => {
            sub_workload_toggle = `<span class="d-inline-block me-1" style="width: 20px;"></span>`;
            if (workload.has_sub_workload) {
                icon = (EXPANDED_ROWS.includes(workload.id)) ? `<i class="fa-solid fa-chevron-down fa-fw"></i>` : `<i class="fa-solid fa-chevron-right fa-fw"></i>`;
                sub_workload_toggle = `
                    <button class="btn btn-sm btn-link p-0 text-decoration-none text-dark me-1" onclick="toggleSubWorkload('${workload.id}', this)">
                        ${icon}
                    </button>
                `;
            }

            html += `
                <tr class="main-workload-row">
                    <td class="text-nowrap">
                        ${sub_workload_toggle}
                        <!-- <input class="form-check-input row-checkbox align-middle" type="checkbox" value="{{ workload.id }}"> -->
                    </td>
                    <td>
                        <strong>${workload.workload_type}</strong>
                    </td>
                    <td>
                        <strong>${workload.user}</strong>
                        ${workload.show_full_name ? `<br><span style="color:#666666;">${workload.full_name}</span>` : ''}
                    </td>
                    <td>
                        <strong>${workload.project}</strong><br>
                        <span style="color:#666666;">${workload.name}</span>
                    </td>
                    <td>
                        <span style="color:#666666;">${workload.namespace}</span><br>
                        <span class="badge-id text-muted small">${workload.id}</span>
                    </td>
                    <td><span class="badge badge-schedule badge-schedule-${workload.status.toLowerCase()}">${workload.status}</span></td>
                    <td>${workload.age}</td>
                    <td>${workload["Resource Profile"]}</td>
                </tr>
            `;

            if (workload.has_sub_workload) {
                // display = (EXPANDED_ROWS.includes(workload.id)) ? "table-row" : "none";
                for (const sub of workload.sub_workload) {
                    fullname = sub.show_full_name ? `<br><span style="color:#888888;">${sub.full_name}</span>` : '';
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
                                    ${sub.project}<br>
                                    <span style="color:#888888;">${sub.name}</span>
                                </div>
                            </td>
                            <td>
                                <div class="ps-2">
                                    <span style="color:#888888;">${sub.namespace}</span><br>
                                    <span class="badge-id text-muted small">${sub.id}</span>
                                </div>
                            </td>
                            <td><span class="badge badge-schedule badge-schedule-${sub.status.toLowerCase()}">${sub.status}</span></td>
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
    data = (SEARCH_FILTER == SearchFilters.ALL) ? SEARCH_DATA[SearchFilters.USERNAME] : SEARCH_DATA[SEARCH_FILTER];
    let html = '';
    data.forEach(item => {
        html += `<option value="${item}">`;
    });

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

    // const searchFilter = document.getElementById("search-filter").value;
    const isValidSearchFilter = Object.values(SearchFilters).includes(SEARCH_FILTER);
    let toBeSearchFilter = (isValidSearchFilter) ? SEARCH_FILTER : SearchFilters.ALL;

    let toBePageNumber = CURRENT_PAGE;
    if (filterChanged || direction === "first")
        toBePageNumber = 1
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
            TOTAL_WORKLOAD = data.total_number_of_workload;

            updatePagination();
            updateFilter();
            updateSearch();
            updateSort();
            console.log(">>>>>>>>>>>>>>>>>>>>>>>> HERE");
            renderTable(data.payload);
            console.log(">>>>>>>>>>>>>>>>>>>>>>>> THERE");
        })
        .catch(error => console.error('Error fetching data:', error));
}


function refreshData() {
    // 1. Get the modal elements and create Bootstrap instances
    const loadingModalEl = document.getElementById('loadingModal');
    const errorModalEl = document.getElementById('errorModal');
    const loadingModal = bootstrap.Modal.getOrCreateInstance(loadingModalEl);
    const errorModal = bootstrap.Modal.getOrCreateInstance(errorModalEl);

    // 2. Show the loading modal before starting the fetch
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
            // Check if the HTTP status is not 200-299
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
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
                
                // Now it is safe to hide
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
        if (response.ok) return response.blob(); // Convert to Blob (Binary Large Object)
        throw new Error('Network response was not ok.');
    })
    .then(blob => {
        // 2. Create a temporary URL for the Blob
        const url = window.URL.createObjectURL(blob);
        
        // 3. Create a hidden link and click it programmatically
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;

        const date = new Date(); // Gets the current date and time
        const formattedDate = date.toISOString().split('T')[0];
        a.download = `report_${formattedDate}.xlsx`; // Name the file here

        document.body.appendChild(a);
        
        a.click(); // Trigger the download
        
        // 4. Clean up
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    })
    .catch(error => console.error('Download failed:', error));
}


function toggleSort(orderBy, headerElement) {
    // 1. Check current state of the clicked column
    let currentOrder = headerElement.getAttribute('data-order');
    
    // 2. Determine the new state 
    // If it's currently ascending, make it descending. Otherwise, make it ascending.
    let newOrder = (currentOrder === 'asc') ? 'desc' : 'asc';
    let isDesc = (newOrder === 'desc');

    // 3. Reset all sortable headers to their neutral state
    const allSortHeaders = document.querySelectorAll('th[data-order]');
    allSortHeaders.forEach(th => {
        th.setAttribute('data-order', 'none');
        const icon = th.querySelector('.sort-icon');
        if (icon) {
            // Reset to the default bidirectional sort icon
            icon.className = 'fa-solid fa-sort text-muted sort-icon ms-1';
        }
    });

    // 4. Apply the new state to the clicked header
    headerElement.setAttribute('data-order', newOrder);
    const activeIcon = headerElement.querySelector('.sort-icon');
    
    if (newOrder === 'asc') {
        // Triangle pointing UP
        activeIcon.className = 'fa-solid fa-caret-up sort-icon ms-1'; 
    } else {
        // Triangle pointing DOWN
        activeIcon.className = 'fa-solid fa-caret-down sort-icon ms-1';
    }

    // 5. Call your data fetching function
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
    // Select all sub-workload rows that belong to this workload ID
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
    // 1. SELECT ALL LOGIC
    // const selectAllCheckbox = document.getElementById('selectAll');

    // // Use event delegation for row checkboxes because they are dynamic (re-rendered by JS)
    // document.getElementById('table-body').addEventListener('change', function(e) {
    //     if(e.target.classList.contains('row-checkbox')) {
    //         const allCheckboxes = document.querySelectorAll('.row-checkbox');
    //         const allChecked = Array.from(allCheckboxes).every(c => c.checked);
    //         selectAllCheckbox.checked = allChecked;
    //     }
    // });

    // selectAllCheckbox.addEventListener('change', function () {
    //     const rowCheckboxes = document.querySelectorAll('.row-checkbox');
    //     rowCheckboxes.forEach(checkbox => {
    //         checkbox.checked = selectAllCheckbox.checked;
    //     });
    // });

    // Select the element
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

    if (MAX_PAGES == 1) {
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

    const filterAllCount = document.getElementById("filter-all-count");
    const filterSessionsCount = document.getElementById("filter-sessions-count");
    const filterApplicationsCount = document.getElementById("filter-applications-count");
    const filterJobsCount = document.getElementById("filter-jobs-count");

    filterButtonAll.classList.value = "btn btn-outline-secondary";
    filterButtonSessions.classList.value = "btn btn-outline-secondary";
    filterButtonApplications.classList.value = "btn btn-outline-secondary";
    filterButtonJobs.classList.value = "btn btn-outline-secondary";
    filterAllCount.classList.value = "badge bg-secondary";
    filterSessionsCount.classList.value = "badge bg-secondary";
    filterApplicationsCount.classList.value = "badge bg-secondary";
    filterJobsCount.classList.value = "badge bg-secondary";

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
    else {
        filterButtonAll.classList.value = "btn btn-primary active";
        filterAllCount.classList.value = "badge";
    }

    filterAllCount.textContent = TOTAL_WORKLOAD;
    filterSessionsCount.textContent = NUM_SESSIONS;
    filterApplicationsCount.textContent = NUM_APPLICATIONS;
    filterJobsCount.textContent = NUM_JOBS;
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
