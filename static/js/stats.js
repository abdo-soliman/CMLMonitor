document.addEventListener('DOMContentLoaded', () => {
    fetchNodeUtilization();
    // Poll stats API every 3 seconds
    setInterval(fetchNodeUtilization, 3000);
});

async function fetchNodeUtilization() {
    try {
        const response = await fetch('/api/stats/utilization');
        if (!response.ok) return;

        const data = await response.json();
        renderNodes(data.nodes || []);
        
        const now = new Date();
        document.getElementById('last-updated').innerText = `Updated ${now.toLocaleTimeString()}`;
    } catch (err) {
        console.error("Failed to fetch node utilization:", err);
    }
}

function renderNodes(nodes) {
    const container = document.getElementById('nodes-container');

    if (!nodes || nodes.length === 0) {
        container.innerHTML = `
            <div class="col-12 text-center py-4">
                <i class="fa-solid fa-triangle-exclamation text-warning mb-2" style="font-size: 2rem;"></i>
                <p class="text-muted">No worker nodes found or cluster information unavailable.</p>
            </div>
        `;
        return;
    }

    let html = '';
    nodes.forEach(node => {
        html += `
            <div class="col-12 col-md-6 col-lg-4 col-xl-3">
                <div class="p-3 bg-light rounded border text-center h-100">
                    <!-- Hostname Header -->
                    <div class="fw-bold text-dark border-bottom pb-2 mb-3 text-truncate" title="${node.node_name}">
                        <i class="fa-solid fa-microchip me-2 text-secondary"></i>${node.node_name}
                    </div>

                    <!-- CPU Section (Top) -->
                    <div class="mb-4">
                        <div class="small fw-semibold text-secondary mb-1">CPU Utilization</div>
                        ${createHalfCircleGauge(node.cpu.pct, node.cpu.color)}
                        <div class="fw-bold fs-6 mt-1" style="color: ${node.cpu.color};">${node.cpu.pct.toFixed(2)}%</div>
                        <div class="small text-muted mt-1">
                            <code>${node.cpu.formatted}</code> Cores
                        </div>
                    </div>

                    <!-- RAM Section (Bottom) -->
                    <div>
                        <div class="small fw-semibold text-secondary mb-1">RAM Utilization</div>
                        ${createHalfCircleGauge(node.ram.pct, node.ram.color)}
                        <div class="fw-bold fs-6 mt-1" style="color: ${node.ram.color};">${node.ram.pct.toFixed(2)}%</div>
                        <div class="small text-muted mt-1">
                            <code>${node.ram.formatted}</code> GiB
                        </div>
                    </div>
                </div>
            </div>
        `;
    });

    container.innerHTML = html;
}

/**
 * Generates an SVG Half-Circle Gauge
 * Semi-circle arc radius = 70, stroke-dasharray = 219.91 (pi * 70)
 */
function createHalfCircleGauge(percentage, color) {
    const cappedPct = Math.min(Math.max(percentage, 0), 100);
    const circumference = Math.PI * 70; // ~219.91
    const dashOffset = circumference * (1 - cappedPct / 100);

    return `
        <div class="d-flex justify-content-center align-items-center mt-2">
            <svg width="160" height="95" viewBox="0 0 160 95">
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