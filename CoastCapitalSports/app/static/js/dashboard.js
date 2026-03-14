/* ============================================================
   dashboard.js — Sports Summary page logic
   ============================================================ */

document.addEventListener('DOMContentLoaded', () => {
    loadQuickStats();
    loadBettingRecommendations();
    loadWeeklyPlan();
    loadFocusTeamScores();
    loadNews();
});

// ------------------------------------------------------------------ Quick Stats
async function loadQuickStats() {
    try {
        const resp = await fetch('/api/quick-stats');
        const data = await resp.json();
        if (data.status === 'error') return;
        for (const [sport, info] of Object.entries(data.stats || {})) {
            const el = document.getElementById(`stat-${sport}`);
            if (el) el.textContent = (info.game_count || 0).toLocaleString();
        }
    } catch (e) {
        console.warn('Failed to load quick stats', e);
    }
}

// ------------------------------------------------------------------ Betting Recommendations
async function loadBettingRecommendations() {
    const container = document.getElementById('betting-cards');
    const spinner = document.getElementById('betting-spinner');
    try {
        const resp = await fetch('/api/betting-recommendations?bankroll=50&max_pct=0.5');
        const data = await resp.json();
        spinner.remove();

        // Handle API-level errors
        if (data.status === 'error') {
            container.innerHTML = `<div class="col-12"><p class="text-muted">Could not generate recommendations: ${data.message || 'unknown error'}</p></div>`;
            return;
        }

        // Update summary stats
        document.getElementById('bet-bankroll').textContent = `$${(data.bankroll || 50).toFixed(2)}`;
        document.getElementById('bet-wagered').textContent = `$${(data.total_wagered || 0).toFixed(2)}`;
        document.getElementById('bet-count').textContent = data.bet_count || 0;
        document.getElementById('bet-max').textContent = `$${(data.max_per_game || 25).toFixed(2)}`;

        const bets = data.bets || [];
        if (bets.length === 0) {
            container.innerHTML = '<div class="col-12"><p class="text-muted">No value bets found. Models may need training, or no games with sufficient edge are available.</p></div>';
            return;
        }

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

            // Result indicator if actual result is known
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
                        <div class="small text-muted mb-1">
                            ${bet.away_team} @ ${bet.home_team}
                        </div>
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

        // Add generated timestamp
        if (data.generated_at) {
            const footer = document.createElement('div');
            footer.className = 'col-12';
            footer.innerHTML = `<small class="text-muted">Generated: ${data.generated_at} | Quarter-Kelly allocation | Min edge: 3%</small>`;
            container.appendChild(footer);
        }

    } catch (e) {
        spinner.remove();
        container.innerHTML = '<div class="col-12"><p class="text-muted">Failed to load betting recommendations. Ensure models are trained.</p></div>';
        console.warn('Failed to load betting recommendations', e);
    }
}

// ------------------------------------------------------------------ Weekly Plan
async function loadWeeklyPlan() {
    const container = document.getElementById('weekly-plan-container');
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

        // Build bets table
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
                tableRows += `
                    <tr>
                        <td><span class="badge bg-secondary">${(bet.sport || '').toUpperCase()}</span></td>
                        <td class="fw-bold">${bet.pick || ''}${resultBadge}</td>
                        <td class="small text-muted">${bet.away_team || ''} @ ${bet.home_team || ''}</td>
                        <td>${bet.game_date || ''}</td>
                        <td class="text-success fw-bold">$${(bet.wager || 0).toFixed(2)}</td>
                        <td class="text-info">+${edgePct}%</td>
                        <td>${evPct > 0 ? '+' : ''}${evPct}%</td>
                        <td class="text-success">$${(bet.potential_profit || 0).toFixed(2)}</td>
                    </tr>`;
            }
        } else {
            tableRows = '<tr><td colspan="8" class="text-muted text-center">No bets in this plan</td></tr>';
        }

        container.innerHTML = `
            <div class="col-12">
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <span>
                            <i class="bi bi-calendar-week me-1"></i>
                            Week of ${plan.week_start || '—'}
                        </span>
                        <span class="small text-muted">
                            Saved: ${plan.created_at || '—'}
                        </span>
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

// ------------------------------------------------------------------ Focus Teams
async function loadFocusTeamScores() {
    const container = document.getElementById('focus-teams');
    const spinner = document.getElementById('focus-spinner');
    try {
        const resp = await fetch('/api/focus-team-scores');
        const data = await resp.json();
        spinner.remove();

        if (data.status === 'error') {
            container.innerHTML = '<div class="col-12"><p class="text-muted">Failed to load focus team scores.</p></div>';
            return;
        }

        for (const team of (data.teams || [])) {
            const col = document.createElement('div');
            col.className = 'col-md-4';

            let gamesHtml = '';
            if (team.games && team.games.length > 0) {
                for (const g of team.games) {
                    const homeWin = g.home_score > g.away_score;
                    const isHome = g.home_team.includes(team.team_key);
                    const won = (isHome && homeWin) || (!isHome && !homeWin);
                    const badge = won
                        ? '<span class="badge bg-success me-1">W</span>'
                        : '<span class="badge bg-danger me-1">L</span>';
                    gamesHtml += `
                        <div class="score-row d-flex justify-content-between align-items-center py-1 border-bottom border-secondary">
                            <div>${badge}<small class="text-muted">${g.game_date || ''}</small></div>
                            <div>
                                <span class="${isHome ? (homeWin ? 'winner' : 'loser') : (homeWin ? 'loser' : 'winner')}">${g.home_team} ${g.home_score}</span>
                                <span class="text-muted mx-1">–</span>
                                <span class="${!isHome ? (!homeWin ? 'winner' : 'loser') : (!homeWin ? 'loser' : 'winner')}">${g.away_team} ${g.away_score}</span>
                            </div>
                        </div>`;
                }
            } else {
                gamesHtml = '<p class="text-muted small mb-0">No recent games found</p>';
            }

            col.innerHTML = `
                <div class="card team-card h-100">
                    <div class="card-header d-flex align-items-center">
                        <span class="team-name">${team.team_name}</span>
                        <span class="badge bg-secondary ms-auto">${team.sport}</span>
                    </div>
                    <div class="card-body">${gamesHtml}</div>
                </div>`;
            container.appendChild(col);
        }

        if (!data.teams || data.teams.length === 0) {
            container.innerHTML = '<div class="col-12"><p class="text-muted">No focus team data available. Run an ingest first.</p></div>';
        }
    } catch (e) {
        spinner.remove();
        container.innerHTML = '<div class="col-12"><p class="text-muted">Failed to load focus team scores.</p></div>';
    }
}

// ------------------------------------------------------------------ News
async function loadNews() {
    const container = document.getElementById('news-container');
    const spinner = document.getElementById('news-spinner');
    try {
        const resp = await fetch('/api/news?limit=12');
        const data = await resp.json();
        spinner.remove();

        if (data.status === 'error') {
            container.innerHTML = '<div class="col-12"><p class="text-muted">Failed to load news.</p></div>';
            return;
        }

        for (const article of (data.articles || [])) {
            const col = document.createElement('div');
            col.className = 'col-md-4 col-lg-3';

            const focusBadge = article.focus_team
                ? `<span class="badge bg-info badge-focus me-1">${article.focus_team}</span>`
                : '';
            const sportBadge = `<span class="badge bg-secondary badge-focus">${article.sport || ''}</span>`;
            const summary = article.llm_summary && !article.llm_summary.startsWith('(LLM')
                ? `<p class="summary mt-2 mb-0">${article.llm_summary}</p>`
                : (article.description
                    ? `<p class="summary mt-2 mb-0">${article.description.substring(0, 150)}…</p>`
                    : '');
            const link = article.article_url
                ? `<a href="${article.article_url}" target="_blank" class="text-info small">Read more →</a>`
                : '';

            col.innerHTML = `
                <div class="card news-card h-100">
                    <div class="card-body d-flex flex-column">
                        <div class="mb-1">${focusBadge}${sportBadge}</div>
                        <div class="headline">${article.headline || ''}</div>
                        ${summary}
                        <div class="mt-auto pt-2 d-flex justify-content-between align-items-center">
                            <span class="meta">${article.published_at ? new Date(article.published_at).toLocaleDateString() : ''}</span>
                            ${link}
                        </div>
                    </div>
                </div>`;
            container.appendChild(col);
        }

        if (!data.articles || data.articles.length === 0) {
            container.innerHTML = '<div class="col-12"><p class="text-muted">No news articles available. Run <code>POST /ingest-news</code> first.</p></div>';
        }
    } catch (e) {
        spinner.remove();
        container.innerHTML = '<div class="col-12"><p class="text-muted">Failed to load news.</p></div>';
    }
}
