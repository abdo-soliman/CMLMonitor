let currentPage = 1;
let currentSize = 25;
let hideDisabled = true;
let sortStatus = 'none'; // 'none', 'asc', 'desc'

// Load data immediately when page boots
document.addEventListener('DOMContentLoaded', () => {
    fetchData();
});

// -- Core AJAX Fetch Function --
async function fetchData(page = null) {
    if (page) currentPage = page;

    // Construct the API URL
    const url = `/runtimes?api=true&page=${currentPage}&size=${currentSize}&hide_disabled=${hideDisabled}&sort_status=${sortStatus}`;
    
    try {
        const response = await fetch(url);
        const data = await response.json();
        
        renderTable(data.runtimes);
        renderPagination(data.pagination);
        updateHeadersUI();
    } catch (error) {
        console.error("Error fetching runtimes data:", error);
    }
}

// -- DOM Manipulation Methods --
function renderTable(runtimes) {
    const dataContainer = document.getElementById('data-container');
    const emptyState = document.getElementById('empty-state');
    const tbody = document.getElementById('runtimesTableBody');
    
    tbody.innerHTML = ''; // Clear current rows

    if (runtimes.length === 0) {
        dataContainer.style.display = 'none';
        emptyState.style.display = 'block';
        return;
    }

    dataContainer.style.display = 'block';
    emptyState.style.display = 'none';

    runtimes.forEach(runtime => {
        const tr = document.createElement('tr');
        
        const addedByHtml = runtime.added_by 
            ? runtime.added_by 
            : `<span class="badge bg-secondary text-white"><i class="fa-solid fa-robot me-1"></i> System</span>`;
            
        const statusHtml = runtime.status === 'ENABLED'
            ? `<span class="badge badge-schedule badge-schedule-running">ENABLED</span>`
            : `<span class="badge badge-schedule bg-secondary text-white">DISABLED</span>`;

        tr.innerHTML = `
            <td><strong>${runtime.editor_name}</strong></td>
            <td><span class="badge-id text-muted small">${runtime.editor_version}</span></td>
            <td class="text-muted" style="word-break: break-all;">${runtime.image}</td>
            <td>${addedByHtml}</td>
            <td>${statusHtml}</td>
        `;
        tbody.appendChild(tr);
    });
}

function renderPagination(pagination) {
    const firstBtn = document.getElementById('btn-first');
    const prevBtn = document.getElementById('btn-prev');
    const nextBtn = document.getElementById('btn-next');
    const lastBtn = document.getElementById('btn-last');

    // Handle Prev & First
    if (pagination.has_prev) {
        firstBtn.classList.remove('disabled');
        prevBtn.classList.remove('disabled');
        firstBtn.querySelector('button').onclick = () => fetchData(1);
        prevBtn.querySelector('button').onclick = () => fetchData(pagination.prev_num);
    } else {
        firstBtn.classList.add('disabled');
        prevBtn.classList.add('disabled');
        firstBtn.querySelector('button').onclick = null;
        prevBtn.querySelector('button').onclick = null;
    }

    // Handle Next & Last
    if (pagination.has_next) {
        nextBtn.classList.remove('disabled');
        lastBtn.classList.remove('disabled');
        nextBtn.querySelector('button').onclick = () => fetchData(pagination.next_num);
        lastBtn.querySelector('button').onclick = () => fetchData(pagination.pages);
    } else {
        nextBtn.classList.add('disabled');
        lastBtn.classList.add('disabled');
        nextBtn.querySelector('button').onclick = null;
        lastBtn.querySelector('button').onclick = null;
    }
}

function updateHeadersUI() {
    const header = document.getElementById('statusColumnHeader');
    const icon = document.getElementById('statusSortIcon');

    if (hideDisabled) {
        header.style.cursor = 'default';
        icon.style.display = 'none';
    } else {
        header.style.cursor = 'pointer';
        icon.style.display = 'inline-block';
        
        // Update Icon styles based on current state
        if (sortStatus === 'asc') {
            icon.className = 'fa-solid fa-sort-up text-primary sort-icon ms-1';
        } else if (sortStatus === 'desc') {
            icon.className = 'fa-solid fa-sort-down text-primary sort-icon ms-1';
        } else {
            icon.className = 'fa-solid fa-sort text-muted sort-icon ms-1';
        }
    }
}

// -- Event Handlers --
function toggleDisabledRuntimes() {
    hideDisabled = document.getElementById('hideDisabledToggle').checked;
    if (hideDisabled) {
        sortStatus = 'none'; // Reset sort if we are hiding disabled items
    }
    fetchData(1); // Reset to page 1 on filter change
}

function sortStatusColumn() {
    if (hideDisabled) return; // Prevent sorting if disabled are hidden

    if (sortStatus === 'none' || sortStatus === 'desc') {
        sortStatus = 'asc';
    } else {
        sortStatus = 'desc';
    }
    fetchData(1); // Reset to page 1 on sort change
}

function changePageSize(size) {
    currentSize = parseInt(size);
    fetchData(1); // Reset to page 1 on page size change
}