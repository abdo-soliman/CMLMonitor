let showIndividualWorks = false;
let latestNodesData = [];

document.addEventListener('DOMContentLoaded', () => {
    fetchNodeUtilization();
    // Poll stats API every 5 seconds per requirements
    setInterval(fetchNodeUtilization, 5000);
});

function toggleWorksView() {
    const toggleBtn = document.getElementById('toggleIndividualWorks');
    showIndividualWorks = toggleBtn ? toggleBtn.checked : false;
    renderNodes(latestNodesData);
}

async function fetchNodeUtilization() {
    try {
        const response = await fetch('/api/stats/utilization');
        if (!response.ok) return;

        const data = await response.json();
        latestNodesData = data.nodes || [];
        renderNodes(latestNodesData);
    } catch (err) {
        console.error("Failed to fetch node utilization:", err);
    }
}

function resolveColor(pct) {
    if (pct < 75.0) return "#007bff"; // Blue
    if (pct <= 90.0) return "#ffc107"; // Yellow
    return "#dc3545"; // Red
}

function renderNodes(nodes) {
    const container = document.getElementById('nodes-container');

    if (!nodes || nodes.length === 0) {
        container.innerHTML = `
            <div class="col-12 text-center py-3">
                <p class="text-muted mb-0"><i class="fa-solid fa-circle-exclamation me-2"></i>No worker nodes found.</p>
            </div>
        `;
        return;
    }

    if (!showIndividualWorks) {
        // --- UNIFIED VIEW (Side by Side) ---
        let totalCpuReq = 0, totalCpuCap = 0;
        let totalRamReqGi = 0, totalRamCapGi = 0;

        nodes.forEach(n => {
            totalCpuReq += n.cpu.req;
            totalCpuCap += n.cpu.cap;
            totalRamReqGi += n.ram.req_gi;
            totalRamCapGi += n.ram.cap_gi;
        });

        const cpuPct = totalCpuCap > 0 ? (totalCpuReq / totalCpuCap) * 100 : 0;
        const ramPct = totalRamCapGi > 0 ? (totalRamReqGi / totalRamCapGi) * 100 : 0;

        container.innerHTML = `
            <div class="col-12 d-flex justify-content-center gap-5 flex-wrap">
                <!-- Unified CPU -->
                <div class="text-center">
                    <div class="small fw-semibold text-secondary mb-1">Total CPU Utilization</div>
                    ${createHalfCircleGauge(cpuPct, resolveColor(cpuPct))}
                    <div class="fw-bold fs-5 mt-1" style="color: ${resolveColor(cpuPct)};">${cpuPct.toFixed(2)}%</div>
                    <div class="small text-muted mt-1">
                        <code class="fs-6">${totalCpuReq.toFixed(2)}/${totalCpuCap.toFixed(2)}</code> Cores
                    </div>
                </div>

                <!-- Unified RAM -->
                <div class="text-center">
                    <div class="small fw-semibold text-secondary mb-1">Total RAM Utilization</div>
                    ${createHalfCircleGauge(ramPct, resolveColor(ramPct))}
                    <div class="fw-bold fs-5 mt-1" style="color: ${resolveColor(ramPct)};">${ramPct.toFixed(2)}%</div>
                    <div class="small text-muted mt-1">
                        <code class="fs-6">${totalRamReqGi.toFixed(2)}/${totalRamCapGi.toFixed(2)}</code> GiB
                    </div>
                </div>
            </div>
        `;
    } else {
        // --- INDIVIDUAL VIEW (3 per row, top and bottom, no borders) ---
        let html = '';
        nodes.forEach(node => {
            html += `
                <div class="col-12 col-md-6 col-lg-4">
                    <div class="p-2 text-center h-100">
                        <div class="fw-bold text-dark pb-2 mb-2 text-truncate" title="${node.node_name}">
                            <i class="fa-solid fa-microchip me-1 text-secondary"></i> ${node.node_name}
                        </div>

                        <div class="mb-3">
                            <div class="small text-secondary mb-1">CPU</div>
                            ${createHalfCircleGauge(node.cpu.pct, node.cpu.color)}
                            <div class="fw-bold mt-1" style="color: ${node.cpu.color};">${node.cpu.pct.toFixed(2)}%</div>
                            <div class="small text-muted">
                                <code>${node.cpu.req.toFixed(2)}/${node.cpu.cap.toFixed(2)}</code>
                            </div>
                        </div>

                        <div>
                            <div class="small text-secondary mb-1">RAM</div>
                            ${createHalfCircleGauge(node.ram.pct, node.ram.color)}
                            <div class="fw-bold mt-1" style="color: ${node.ram.color};">${node.ram.pct.toFixed(2)}%</div>
                            <div class="small text-muted">
                                <code>${node.ram.req_gi.toFixed(2)}/${node.ram.cap_gi.toFixed(2)}</code>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });
        container.innerHTML = html;
    }
}

/**
 * Generates an SVG Half-Circle Gauge
 */
function createHalfCircleGauge(percentage, color) {
    const cappedPct = Math.min(Math.max(percentage, 0), 100);
    const circumference = Math.PI * 70; // ~219.91
    const dashOffset = circumference * (1 - cappedPct / 100);

    return `
        <div class="d-flex justify-content-center align-items-center mt-1">
            <svg width="150" height="85" viewBox="0 0 160 95">
                <!-- Background Arc -->
                <path d="M 10 85 A 70 70 0 0 1 150 85" 
                      fill="none" 
                      stroke="#e9ecef" 
                      stroke-width="14" 
                      stroke-linecap="round" />
                
                <!-- Foreground Colored Arc -->
                <path d="M 10 85 A 70 70 0 0 1 150 85" 
                      fill="none" 
                      stroke="${color}" 
                      stroke-width="14" 
                      stroke-linecap="round" 
                      stroke-dasharray="${circumference}" 
                      stroke-dashoffset="${dashOffset}" 
                      style="transition: stroke-dashoffset 0.5s ease-in-out, stroke 0.3s ease;" />
            </svg>
        </div>
    `;
}
