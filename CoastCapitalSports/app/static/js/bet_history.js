/* ============================================================
   bet_history.js — Bet Tracking & Performance page logic
   ============================================================ */

let accuracyChart = null;
let plChart = null;

document.addEventListener('DOMContentLoaded', () => {
    loadBetSummary();
    loadBetHistory();
    document.getElementById('sport-filter').addEventListener('change', () => {
        const sport = document.getElementById('sport-filter').value;
        loadBetHistory(sport);
    });
});

// ------------------------------------------------------------------ Summary
async function loadBetSummary() {
    try {
        const resp = await fetch('/api/bet-history/summary');
        const data = await resp.json();

        if (data.status === 'error') {
            console.warn('Bet summary returned error:', data.message);
            return;
        }

        const summary = data.summary || {};

        const totalEl = document.getElementById('stat-total-bets');
        if (totalEl) totalEl.textContent = (summary.total_bets || 0).toLocaleString();

        const winEl = document.getElementById('stat-win-rate');
        if (winEl) {
            const rate = summary.win_rate;
            winEl.textContent = rate != null ? (rate * 100).toFixed(1) + '%' : '0.0%';
        }

        const plEl = document.getElementById('stat-total-pl');
        if (plEl) {
            const pl = summary.total_pl || 0;
            plEl.textContent = (pl >= 0 ? '+' : '') + '$' + Math.abs(pl).toFixed(2);
            plEl.className = 'stat-value ' + (pl >= 0 ? 'text-success' : 'text-danger');
        }

        const bestEl = document.getElementById('stat-best-week');
        if (bestEl) {
            const best = summary.best_week_pl || 0;
            bestEl.textContent = (best >= 0 ? '+' : '-') + '$' + Math.abs(best).toFixed(2);
        }

    } catch (e) {
        console.warn('Failed to load bet summary', e);
    }
}

// ------------------------------------------------------------------ History
async function loadBetHistory(sport) {
    const tableBody = document.getElementById('history-table-body');
    const qs = new URLSearchParams({ weeks: '52' });
    if (sport) qs.set('sport', sport);

    try {
        const resp = await fetch(`/api/bet-history?${qs.toString()}`);
        const data = await resp.json();

        if (data.status === 'error') {
            tableBody.innerHTML = '<tr><td colspan="11" class="text-center text-muted">Failed to load bet history.</td></tr>';
            renderEmptyCharts();
            return;
        }

        const bets = data.bets || [];
        if (bets.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="11" class="text-center text-muted">No data yet. Bets will appear here once weekly plans are saved and games are resolved.</td></tr>';
            renderEmptyCharts();
            return;
        }

        renderTable(bets, tableBody);
        renderCharts(bets);

    } catch (e) {
        tableBody.innerHTML = '<tr><td colspan="11" class="text-center text-muted">Failed to load bet history.</td></tr>';
        renderEmptyCharts();
        console.warn('Failed to load bet history', e);
    }
}

// ------------------------------------------------------------------ Table
function renderTable(bets, tableBody) {
    // Sort by date descending
    const sorted = [...bets].sort((a, b) => {
        const da = a.game_date || '';
        const db = b.game_date || '';
        return db.localeCompare(da);
    });

    tableBody.innerHTML = '';
    for (const bet of sorted) {
        const tr = document.createElement('tr');
        const edgePct = bet.edge != null ? (bet.edge * 100).toFixed(1) : '—';

        // Model probability (likelihood score)
        const probPct = bet.model_prob != null ? (bet.model_prob * 100).toFixed(1) + '%' : '—';

        // Outcome badge
        let outcomeBadge;
        if (bet.outcome === 'win') {
            outcomeBadge = '<span class="badge bg-success">Win</span>';
        } else if (bet.outcome === 'loss') {
            outcomeBadge = '<span class="badge bg-danger">Loss</span>';
        } else {
            outcomeBadge = '<span class="badge bg-secondary">Pending</span>';
        }

        // P/L formatting
        let plCell = '<span class="text-muted">—</span>';
        if (bet.pl != null && bet.outcome && bet.outcome !== 'pending') {
            const pl = bet.pl;
            const plColor = pl >= 0 ? 'text-success' : 'text-danger';
            plCell = `<span class="${plColor}">${pl >= 0 ? '+' : ''}$${Math.abs(pl).toFixed(2)}</span>`;
        }

        // Odds formatting
        const oddsStr = bet.moneyline
            ? (bet.moneyline > 0 ? `+${bet.moneyline}` : `${bet.moneyline}`)
            : '—';

        // Matchup
        const matchup = (bet.away_team && bet.home_team)
            ? `${bet.away_team} @ ${bet.home_team}`
            : (bet.matchup || '—');

        tr.innerHTML = `
            <td>${bet.game_date || '—'}</td>
            <td><span class="badge bg-secondary">${(bet.sport || '').toUpperCase()}</span></td>
            <td class="small">${bet.target || '—'}</td>
            <td class="small text-muted">${matchup}</td>
            <td class="fw-bold">${bet.pick || '—'}</td>
            <td><strong>${probPct}</strong></td>
            <td class="text-info">${edgePct !== '—' ? '+' + edgePct + '%' : '—'}</td>
            <td class="text-success fw-bold">$${(bet.wager || 0).toFixed(2)}</td>
            <td>${oddsStr}</td>
            <td>${outcomeBadge}</td>
            <td>${plCell}</td>`;
        tableBody.appendChild(tr);
    }
}

// ------------------------------------------------------------------ Charts
function renderCharts(bets) {
    // Group by week (ISO week + year)
    const weekMap = {};
    for (const bet of bets) {
        if (!bet.game_date) continue;
        const d = new Date(bet.game_date + 'T00:00:00');
        const weekKey = getWeekKey(d);
        if (!weekMap[weekKey]) {
            weekMap[weekKey] = { wins: 0, losses: 0, total: 0, pl: 0 };
        }
        weekMap[weekKey].total++;
        if (bet.outcome === 'win') weekMap[weekKey].wins++;
        if (bet.outcome === 'loss') weekMap[weekKey].losses++;
        if (bet.pl != null) weekMap[weekKey].pl += bet.pl;
    }

    // Sort weeks chronologically
    const weekKeys = Object.keys(weekMap).sort();

    if (weekKeys.length === 0) {
        renderEmptyCharts();
        return;
    }

    const labels = weekKeys.map(k => formatWeekLabel(k));
    const accuracyData = weekKeys.map(k => {
        const w = weekMap[k];
        const resolved = w.wins + w.losses;
        return resolved > 0 ? +((w.wins / resolved) * 100).toFixed(1) : null;
    });

    // Cumulative P/L
    let cumPl = 0;
    const plData = weekKeys.map(k => {
        cumPl += weekMap[k].pl;
        return +cumPl.toFixed(2);
    });

    renderAccuracyChart(labels, accuracyData);
    renderPLChart(labels, plData);
}

function renderAccuracyChart(labels, data) {
    if (accuracyChart) accuracyChart.destroy();

    accuracyChart = new Chart(document.getElementById('accuracy-chart'), {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: 'Accuracy %',
                data,
                borderColor: 'rgba(13,202,240,1)',
                backgroundColor: 'rgba(13,202,240,0.1)',
                borderWidth: 2,
                pointRadius: 4,
                pointBackgroundColor: 'rgba(13,202,240,1)',
                fill: true,
                tension: 0.3,
                spanGaps: true,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: ctx => ctx.parsed.y != null ? ctx.parsed.y.toFixed(1) + '%' : 'N/A'
                    }
                }
            },
            scales: {
                x: {
                    ticks: { maxRotation: 45, autoSkipPadding: 10 },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                },
                y: {
                    beginAtZero: true,
                    max: 100,
                    title: { display: true, text: 'Accuracy %' },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                }
            }
        }
    });
}

function renderPLChart(labels, data) {
    if (plChart) plChart.destroy();

    // Build segment colors: green when at or above 0, red when below
    const segmentColor = (ctx) => {
        const idx = ctx.p1DataIndex;
        return data[idx] >= 0 ? 'rgba(25,135,84,1)' : 'rgba(220,53,69,1)';
    };

    // Build gradient fill — we need per-point fill logic
    // Chart.js doesn't natively do split fills, so we use a plugin approach via
    // two datasets: one for positive region, one for negative
    const posData = data.map(v => v >= 0 ? v : 0);
    const negData = data.map(v => v < 0 ? v : 0);

    plChart = new Chart(document.getElementById('pl-chart'), {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label: 'Cumulative P/L',
                    data,
                    borderColor: data[data.length - 1] >= 0 ? 'rgba(25,135,84,1)' : 'rgba(220,53,69,1)',
                    borderWidth: 2,
                    pointRadius: 4,
                    pointBackgroundColor: data.map(v => v >= 0 ? 'rgba(25,135,84,1)' : 'rgba(220,53,69,1)'),
                    fill: {
                        target: 'origin',
                        above: 'rgba(25,135,84,0.15)',
                        below: 'rgba(220,53,69,0.15)',
                    },
                    tension: 0.3,
                    segment: {
                        borderColor: segmentColor,
                    },
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: ctx => {
                            const v = ctx.parsed.y;
                            return (v >= 0 ? '+' : '') + '$' + Math.abs(v).toFixed(2);
                        }
                    }
                }
            },
            scales: {
                x: {
                    ticks: { maxRotation: 45, autoSkipPadding: 10 },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                },
                y: {
                    title: { display: true, text: 'Cumulative P/L ($)' },
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: {
                        callback: v => (v >= 0 ? '+' : '') + '$' + Math.abs(v).toFixed(0)
                    }
                }
            }
        }
    });
}

function renderEmptyCharts() {
    if (accuracyChart) accuracyChart.destroy();
    accuracyChart = new Chart(document.getElementById('accuracy-chart'), {
        type: 'line',
        data: { labels: [], datasets: [] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                title: { display: true, text: 'No data yet', color: 'rgba(255,255,255,0.4)' }
            }
        }
    });

    if (plChart) plChart.destroy();
    plChart = new Chart(document.getElementById('pl-chart'), {
        type: 'line',
        data: { labels: [], datasets: [] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                title: { display: true, text: 'No data yet', color: 'rgba(255,255,255,0.4)' }
            }
        }
    });
}

// ------------------------------------------------------------------ Helpers
function getWeekKey(date) {
    // Returns "YYYY-WNN" for sorting and grouping
    const year = date.getFullYear();
    const jan1 = new Date(year, 0, 1);
    const dayOfYear = Math.floor((date - jan1) / 86400000) + 1;
    const weekNum = Math.ceil((dayOfYear + jan1.getDay()) / 7);
    return `${year}-W${String(weekNum).padStart(2, '0')}`;
}

function formatWeekLabel(weekKey) {
    // "2026-W10" -> "Week 10, 2026"
    const parts = weekKey.split('-W');
    if (parts.length === 2) {
        return `Week ${parseInt(parts[1], 10)}, ${parts[0]}`;
    }
    return weekKey;
}
