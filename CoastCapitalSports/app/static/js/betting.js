/* ============================================================
   betting.js — Betting Recommendations page logic
   ============================================================ */

document.addEventListener('DOMContentLoaded', () => {
    loadBettingData();
    loadWeeklyPlanSection();
});

// ------------------------------------------------------------------ Main Load
async function loadBettingData() {
    const cardsContainer = document.getElementById('live-bets-container');
    const spinner = document.getElementById('live-spinner');
    const tableBody = document.getElementById('bet-table-body');

    try {
        const resp = await fetch('/api/betting-recommendations?bankroll=50&max_pct=0.5');
        const data = await resp.json();
        spinner.remove();

        if (data.status === 'error') {
            cardsContainer.innerHTML = `<div class="col-12"><p class="text-muted">${data.message || 'Failed to generate recommendations'}</p></div>`;
            tableBody.innerHTML = '<tr><td colspan="13" class="text-center text-muted">No data available</td></tr>';
            return;
        }

        // Update summary
        document.getElementById('bet-bankroll').textContent = `$${(data.bankroll || 50).toFixed(2)}`;
        document.getElementById('bet-wagered').textContent = `$${(data.total_wagered || 0).toFixed(2)}`;
        document.getElementById('bet-count').textContent = data.bet_count || 0;
        document.getElementById('bet-remaining').textContent = `$${(data.remaining_bankroll || 0).toFixed(2)}`;

        const bets = data.bets || [];
        if (bets.length === 0) {
            cardsContainer.innerHTML = '<div class="col-12"><p class="text-muted">No value bets found. Models may need training, or no games with sufficient edge are available.</p></div>';
            tableBody.innerHTML = '<tr><td colspan="13" class="text-center text-muted">No value bets found</td></tr>';
            return;
        }

        // Render cards
        renderBetCards(bets, cardsContainer, data.generated_at);

        // Render table
        renderBetTable(bets, tableBody);

    } catch (e) {
        spinner.remove();
        cardsContainer.innerHTML = '<div class="col-12"><p class="text-muted">Failed to load betting recommendations.</p></div>';
        tableBody.innerHTML = '<tr><td colspan="13" class="text-center text-muted">Failed to load</td></tr>';
        console.warn('Failed to load betting data', e);
    }
}

// ------------------------------------------------------------------ Cards
function renderBetCards(bets, container, generatedAt) {
    for (const bet of bets) {
        const col = document.createElement('div');
        col.className = 'col-md-4 col-lg-3';

        const edgePct = (bet.edge * 100).toFixed(1);
        const evPct = (bet.ev * 100).toFixed(1);
        const probPct = (bet.model_prob * 100).toFixed(1);
        const impliedPct = (bet.market_implied_prob * 100).toFixed(1);
        const edgeColor = bet.edge > 0.08 ? 'text-success' : (bet.edge > 0.05 ? 'text-info' : 'text-warning');

        const sportBadge = `<span class="badge bg-secondary me-1">${(bet.sport || '').toUpperCase()}</span>`;
        const targetBadge = `<span class="badge bg-dark">${bet.target || ''}</span>`;
        const mlStr = bet.moneyline
            ? `<span class="text-muted small">${bet.moneyline > 0 ? '+' : ''}${bet.moneyline}</span>`
            : '';

        let resultBadge = '';
        if (bet.actual_result !== null && bet.actual_result !== undefined) {
            const didWin = (bet.pick_side === 'home' && bet.actual_result === 1)
                        || (bet.pick_side === 'away' && bet.actual_result === 0);
            resultBadge = didWin
                ? '<span class="badge bg-success ms-1">W</span>'
                : '<span class="badge bg-danger ms-1">L</span>';
        }

        col.innerHTML = `
            <div class="card bet-card h-100">
                <div class="card-header d-flex align-items-center justify-content-between">
                    <div>${sportBadge}${targetBadge}</div>
                    <div class="fw-bold text-success">$${bet.wager.toFixed(2)}</div>
                </div>
                <div class="card-body">
                    <div class="mb-2">
                        <span class="fw-bold">${bet.pick}</span>${resultBadge} ${mlStr}
                    </div>
                    <div class="small text-muted mb-1">${bet.away_team} @ ${bet.home_team}</div>
                    <div class="small mb-1">${bet.game_date || ''}</div>
                    <hr class="border-secondary my-2">
                    <div class="d-flex justify-content-between small">
                        <span>Model: <strong>${probPct}%</strong></span>
                        <span>Market: ${impliedPct}%</span>
                    </div>
                    <div class="d-flex justify-content-between small">
                        <span class="${edgeColor}">Edge: +${edgePct}%</span>
                        <span class="text-info">EV: ${evPct > 0 ? '+' : ''}${evPct}%</span>
                    </div>
                    <div class="small text-muted mt-1">
                        Potential profit: <span class="text-success">$${bet.potential_profit.toFixed(2)}</span>
                    </div>
                </div>
            </div>`;
        container.appendChild(col);
    }

    if (generatedAt) {
        const footer = document.createElement('div');
        footer.className = 'col-12';
        footer.innerHTML = `<small class="text-muted">Generated: ${generatedAt} | Quarter-Kelly allocation | Min edge: 3%</small>`;
        container.appendChild(footer);
    }
}

// ------------------------------------------------------------------ Table
function renderBetTable(bets, tableBody) {
    tableBody.innerHTML = '';
    for (const bet of bets) {
        const tr = document.createElement('tr');
        const edgePct = (bet.edge * 100).toFixed(1);
        const evPct = (bet.ev * 100).toFixed(1);
        const probPct = (bet.model_prob * 100).toFixed(1);
        const impliedPct = (bet.market_implied_prob * 100).toFixed(1);
        const edgeColor = bet.edge > 0.08 ? 'text-success' : (bet.edge > 0.05 ? 'text-info' : 'text-warning');

        let resultCell = '<span class="text-muted">—</span>';
        if (bet.actual_result !== null && bet.actual_result !== undefined) {
            const didWin = (bet.pick_side === 'home' && bet.actual_result === 1)
                        || (bet.pick_side === 'away' && bet.actual_result === 0);
            resultCell = didWin
                ? '<span class="badge bg-success">W</span>'
                : '<span class="badge bg-danger">L</span>';
        }

        const mlStr = bet.moneyline ? (bet.moneyline > 0 ? `+${bet.moneyline}` : `${bet.moneyline}`) : '—';

        tr.innerHTML = `
            <td><span class="badge bg-secondary">${(bet.sport || '').toUpperCase()}</span></td>
            <td class="small">${bet.target || ''}</td>
            <td class="fw-bold">${bet.pick || ''}</td>
            <td class="small text-muted">${bet.away_team || ''} @ ${bet.home_team || ''}</td>
            <td>${bet.game_date || ''}</td>
            <td>${mlStr}</td>
            <td><strong>${probPct}%</strong></td>
            <td>${impliedPct}%</td>
            <td class="${edgeColor}">+${edgePct}%</td>
            <td class="text-info">${evPct > 0 ? '+' : ''}${evPct}%</td>
            <td class="text-success fw-bold">$${bet.wager.toFixed(2)}</td>
            <td class="text-success">$${bet.potential_profit.toFixed(2)}</td>
            <td>${resultCell}</td>`;
        tableBody.appendChild(tr);
    }
}

// ------------------------------------------------------------------ Weekly Plan
async function loadWeeklyPlanSection() {
    const container = document.getElementById('weekly-plan-section');
    if (!container) return;

    try {
        const resp = await fetch('/api/weekly-plan');
        const data = await resp.json();

        if (data.status === 'error' || !data.plan) {
            container.innerHTML = `
                <div class="col-12">
                    <div class="card p-3">
                        <p class="text-muted mb-0">
                            <i class="bi bi-info-circle me-1"></i>
                            No saved weekly plan yet. Run <code>POST /weekly-optimization</code> or
                            <code>python scripts/run_weekly.py</code> to generate one.
                        </p>
                    </div>
                </div>`;
            return;
        }

        const plan = data.plan;
        const planData = plan.plan_json || {};
        const bets = planData.bets || [];

        let tableRows = '';
        if (bets.length > 0) {
            for (const bet of bets) {
                const edgePct = ((bet.edge || 0) * 100).toFixed(1);
                const evPct = ((bet.ev || 0) * 100).toFixed(1);
                let resultBadge = '';
                if (bet.actual_result !== null && bet.actual_result !== undefined) {
                    const didWin = (bet.pick_side === 'home' && bet.actual_result === 1)
                                || (bet.pick_side === 'away' && bet.actual_result === 0);
                    resultBadge = didWin
                        ? ' <span class="badge bg-success">W</span>'
                        : ' <span class="badge bg-danger">L</span>';
                }
                const probPct = bet.model_prob != null ? (bet.model_prob * 100).toFixed(1) + '%' : '—';
                tableRows += `
                    <tr>
                        <td><span class="badge bg-secondary">${(bet.sport || '').toUpperCase()}</span></td>
                        <td class="fw-bold">${bet.pick || ''}${resultBadge}</td>
                        <td class="small text-muted">${bet.away_team || ''} @ ${bet.home_team || ''}</td>
                        <td>${bet.game_date || ''}</td>
                        <td><strong>${probPct}</strong></td>
                        <td class="text-success fw-bold">$${(bet.wager || 0).toFixed(2)}</td>
                        <td class="text-info">+${edgePct}%</td>
                        <td>${evPct > 0 ? '+' : ''}${evPct}%</td>
                        <td class="text-success">$${(bet.potential_profit || 0).toFixed(2)}</td>
                    </tr>`;
            }
        } else {
            tableRows = '<tr><td colspan="9" class="text-muted text-center">No bets in this plan</td></tr>';
        }

        container.innerHTML = `
            <div class="col-12">
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <span><i class="bi bi-calendar-week me-1"></i>Week of ${plan.week_start || '—'}</span>
                        <span class="small text-muted">Saved: ${plan.created_at || '—'}</span>
                    </div>
                    <div class="card-body p-0">
                        <div class="table-responsive">
                            <table class="table table-dark table-sm table-striped mb-0">
                                <thead>
                                    <tr>
                                        <th>Sport</th>
                                        <th>Pick</th>
                                        <th>Matchup</th>
                                        <th>Date</th>
                                        <th>Model %</th>
                                        <th>Wager</th>
                                        <th>Edge</th>
                                        <th>EV</th>
                                        <th>Profit</th>
                                    </tr>
                                </thead>
                                <tbody>${tableRows}</tbody>
                            </table>
                        </div>
                    </div>
                    <div class="card-footer d-flex justify-content-between small text-muted">
                        <span>Bankroll: $${(plan.bankroll || 50).toFixed(2)} | Wagered: $${(plan.total_wagered || 0).toFixed(2)} | Remaining: $${((plan.bankroll || 50) - (plan.total_wagered || 0)).toFixed(2)}</span>
                        <span>${plan.bet_count || 0} bets</span>
                    </div>
                </div>
            </div>`;

    } catch (e) {
        container.innerHTML = '';
        console.warn('Failed to load weekly plan', e);
    }
}
