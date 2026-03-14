/* ============================================================
   bracket.js — NCAA Bracket simulation page logic
   ============================================================ */

document.addEventListener('DOMContentLoaded', () => {
    loadAvailableYears();
});

// ------------------------------------------------------------------ State
let currentSimulations = [];

// ------------------------------------------------------------------ Years
async function loadAvailableYears() {
    const yearSelect = document.getElementById('bracket-year');
    try {
        const resp = await fetch('/api/bracket/simulations?year=all');
        const data = await resp.json();

        const years = data.years || [];
        yearSelect.innerHTML = '';

        if (years.length === 0) {
            // Default to current year if no simulations exist yet
            const currentYear = new Date().getFullYear();
            yearSelect.innerHTML = `<option value="${currentYear}" selected>${currentYear}</option>`;
            return;
        }

        // Sort descending so most recent is first
        years.sort((a, b) => b - a);
        for (const year of years) {
            const opt = document.createElement('option');
            opt.value = year;
            opt.textContent = year;
            yearSelect.appendChild(opt);
        }

        // Auto-load simulations for the most recent year
        loadSimulations(years[0]);

    } catch (e) {
        console.warn('Failed to load available years', e);
        const currentYear = new Date().getFullYear();
        yearSelect.innerHTML = `<option value="${currentYear}" selected>${currentYear}</option>`;
    }
}

// ------------------------------------------------------------------ Load Simulations
async function loadSimulations(year) {
    const tableBody = document.getElementById('simulations-table-body');
    tableBody.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-3"><div class="spinner-border spinner-border-sm text-info me-2" role="status"></div>Loading simulations...</td></tr>';

    // Update the year dropdown to match
    const yearSelect = document.getElementById('bracket-year');
    if (yearSelect.value !== String(year)) {
        yearSelect.value = String(year);
    }

    try {
        const resp = await fetch(`/api/bracket/simulations?year=${year}`);
        const data = await resp.json();

        if (data.status === 'error') {
            tableBody.innerHTML = `<tr><td colspan="8" class="text-center text-muted py-3">${data.message || 'Failed to load simulations'}</td></tr>`;
            return;
        }

        const simulations = data.simulations || [];
        currentSimulations = simulations;

        if (simulations.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-4">No simulations found for this year. Run a simulation to get started.</td></tr>';
            return;
        }

        renderSimulationsTable(simulations, tableBody);

    } catch (e) {
        tableBody.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-3">Failed to load simulations.</td></tr>';
        console.warn('Failed to load simulations', e);
    }
}

// ------------------------------------------------------------------ Render Table
function renderSimulationsTable(simulations, tableBody) {
    tableBody.innerHTML = '';

    for (let i = 0; i < simulations.length; i++) {
        const sim = simulations[i];
        const tr = document.createElement('tr');

        // Highlight the default row
        if (sim.is_default) {
            tr.classList.add('table-active');
        }

        const rank = i + 1;
        const expectedPts = sim.expected_points != null ? sim.expected_points.toFixed(1) : '—';
        const actualScore = sim.actual_score != null ? sim.actual_score.toFixed(1) : '—';
        const runTime = sim.run_time_seconds != null ? `${sim.run_time_seconds.toFixed(1)}s` : '—';
        const champion = sim.champion || '—';

        const defaultBadge = sim.is_default
            ? '<span class="badge bg-info">Default</span>'
            : '';

        const setDefaultBtn = sim.is_default
            ? ''
            : `<button class="btn btn-outline-info btn-sm me-1" onclick="setDefault(${sim.simulation_id})" title="Set as default"><i class="bi bi-check-circle"></i></button>`;

        const viewBtn = `<button class="btn btn-outline-light btn-sm" onclick="viewBracket(${sim.simulation_id})" title="View bracket"><i class="bi bi-diagram-3"></i></button>`;

        tr.innerHTML = `
            <td class="fw-bold">${rank}</td>
            <td class="text-muted">${sim.simulation_id}</td>
            <td class="fw-bold">${champion}</td>
            <td class="text-info">${expectedPts}</td>
            <td>${actualScore !== '—' ? `<span class="text-success">${actualScore}</span>` : '<span class="text-muted">—</span>'}</td>
            <td class="text-muted">${runTime}</td>
            <td>${defaultBadge}</td>
            <td>${setDefaultBtn}${viewBtn}</td>`;

        tableBody.appendChild(tr);
    }
}

// ------------------------------------------------------------------ Run Simulation
async function runSimulation() {
    const year = document.getElementById('bracket-year').value;
    const nRuns = document.getElementById('bracket-n-runs').value;
    const mcSims = document.getElementById('bracket-mc-sims').value;

    if (!year) {
        alert('Please select a year.');
        return;
    }

    // Show progress
    const statusSection = document.getElementById('simulation-status');
    const statusMessage = document.getElementById('status-message');
    const statusDetail = document.getElementById('status-detail');
    const runBtn = document.getElementById('btn-run-simulation');

    statusSection.classList.remove('d-none');
    runBtn.disabled = true;
    runBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status"></span>Running...';
    statusMessage.textContent = 'Running bracket simulation...';
    statusDetail.textContent = `Year: ${year} | Runs: ${nRuns} | MC Sims per run: ${parseInt(mcSims).toLocaleString()}`;

    try {
        const resp = await fetch('/api/bracket/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                year: parseInt(year),
                n_runs: parseInt(nRuns),
                mc_sims: parseInt(mcSims)
            })
        });
        const data = await resp.json();

        if (data.status === 'error') {
            statusMessage.textContent = 'Simulation failed';
            statusMessage.classList.remove('text-info');
            statusMessage.classList.add('text-danger');
            statusDetail.textContent = data.message || 'Unknown error';
            runBtn.disabled = false;
            runBtn.innerHTML = '<i class="bi bi-play-fill me-1"></i>Run Simulation';
            return;
        }

        // Success
        statusMessage.textContent = 'Simulation complete';
        statusMessage.classList.remove('text-danger');
        statusMessage.classList.add('text-info');
        statusDetail.textContent = `Completed ${nRuns} runs successfully.`;

        // Hide progress after a brief delay
        setTimeout(() => {
            statusSection.classList.add('d-none');
        }, 3000);

        // Reload simulations
        loadSimulations(year);

    } catch (e) {
        statusMessage.textContent = 'Simulation failed';
        statusMessage.classList.remove('text-info');
        statusMessage.classList.add('text-danger');
        statusDetail.textContent = 'Network error or server unreachable.';
        console.warn('Failed to run simulation', e);
    } finally {
        runBtn.disabled = false;
        runBtn.innerHTML = '<i class="bi bi-play-fill me-1"></i>Run Simulation';
    }
}

// ------------------------------------------------------------------ Set Default
async function setDefault(simulationId) {
    try {
        const resp = await fetch('/api/bracket/set-default', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ simulation_id: simulationId })
        });
        const data = await resp.json();

        if (data.status === 'error') {
            console.warn('Failed to set default:', data.message);
            return;
        }

        // Reload to update the UI
        const year = document.getElementById('bracket-year').value;
        loadSimulations(year);

    } catch (e) {
        console.warn('Failed to set default simulation', e);
    }
}

// ------------------------------------------------------------------ View Bracket
async function viewBracket(simulationId) {
    const vizSection = document.getElementById('bracket-viz-section');
    const vizContainer = document.getElementById('bracket-viz-container');
    const vizTitle = document.getElementById('bracket-viz-title');

    // Show section with loading state
    vizSection.classList.remove('d-none');
    vizContainer.innerHTML = '<div class="text-center py-5"><div class="spinner-border text-info" role="status"></div><div class="text-muted mt-2">Loading bracket picks...</div></div>';

    // Find the simulation info for the title
    const sim = currentSimulations.find(s => s.simulation_id === simulationId);
    if (sim) {
        vizTitle.textContent = `Bracket — ${sim.champion || 'Simulation'} (Run #${simulationId})`;
    }

    // Scroll to the visualization
    vizSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

    try {
        const resp = await fetch(`/api/bracket/picks?simulation_id=${simulationId}`);
        const data = await resp.json();

        if (data.status === 'error') {
            vizContainer.innerHTML = `<div class="text-center py-5 text-muted">${data.message || 'Failed to load bracket picks.'}</div>`;
            return;
        }

        const picks = data.picks || [];
        if (picks.length === 0) {
            vizContainer.innerHTML = '<div class="text-center py-5 text-muted">No bracket picks found for this simulation.</div>';
            return;
        }

        // Clear container and delegate to bracket_viz.js
        vizContainer.innerHTML = '';
        if (typeof renderBracketViz === 'function') {
            renderBracketViz(picks, vizContainer);
        } else {
            // Fallback: render a simple table if bracket_viz.js is not loaded
            renderBracketFallback(picks, vizContainer);
        }

    } catch (e) {
        vizContainer.innerHTML = '<div class="text-center py-5 text-muted">Failed to load bracket picks.</div>';
        console.warn('Failed to load bracket picks', e);
    }
}

// ------------------------------------------------------------------ Close Bracket Viz
function closeBracketViz() {
    const vizSection = document.getElementById('bracket-viz-section');
    vizSection.classList.add('d-none');
}

// ------------------------------------------------------------------ Fallback Table
function renderBracketFallback(picks, container) {
    const table = document.createElement('div');
    table.className = 'table-responsive';

    let rows = '';
    for (const pick of picks) {
        const winProb = pick.win_probability != null ? `${(pick.win_probability * 100).toFixed(1)}%` : '—';
        rows += `
            <tr>
                <td>${pick.round || '—'}</td>
                <td>${pick.region || '—'}</td>
                <td class="fw-bold">${pick.team_seed || ''} ${pick.team_name || '—'}</td>
                <td>vs</td>
                <td>${pick.opponent_seed || ''} ${pick.opponent_name || '—'}</td>
                <td class="text-info">${winProb}</td>
            </tr>`;
    }

    table.innerHTML = `
        <table class="table table-dark table-sm table-striped mb-0">
            <thead>
                <tr>
                    <th>Round</th>
                    <th>Region</th>
                    <th>Winner</th>
                    <th></th>
                    <th>Opponent</th>
                    <th>Win Prob</th>
                </tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>`;

    container.appendChild(table);
}

// ------------------------------------------------------------------ Year Change Handler
document.addEventListener('DOMContentLoaded', () => {
    const yearSelect = document.getElementById('bracket-year');
    yearSelect.addEventListener('change', () => {
        const year = yearSelect.value;
        if (year) {
            closeBracketViz();
            loadSimulations(year);
        }
    });
});
