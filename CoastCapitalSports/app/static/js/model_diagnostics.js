/* ============================================================
   model_diagnostics.js — Model Diagnostics page logic
   ============================================================ */

let rocChart = null;
let btPnlChart = null;
let btRoiChart = null;
let currentSport = '';
let currentTarget = '';

// Cached data for comparison
let cachedDiagnostics = null;
let cachedBacktest = null;
let cachedRefitResult = null;

document.addEventListener('DOMContentLoaded', () => {
    // Auto-load if URL has params
    const params = new URLSearchParams(window.location.search);
    if (params.get('sport')) document.getElementById('diag-sport').value = params.get('sport');
    if (params.get('target')) document.getElementById('diag-target').value = params.get('target');
    if (params.get('sport')) loadDiagnostics();
});

// ================================================================
// Main loader
// ================================================================

async function loadDiagnostics() {
    currentSport = document.getElementById('diag-sport').value;
    currentTarget = document.getElementById('diag-target').value;

    try {
        const [diagResp, regResp] = await Promise.all([
            fetch(`/api/model-diagnostics?sport=${currentSport}&target=${currentTarget}`),
            fetch(`/api/model-registry?sport=${currentSport}&target=${currentTarget}`)
        ]);
        const diag = await diagResp.json();
        const reg = await regResp.json();

        cachedDiagnostics = diag;

        renderRegistry(reg.models || []);
        renderROC(diag);
        renderConfusionMatrix(diag.confusion_matrix);
        renderYearBreakdown(diag.year_segments || []);
        renderRecommendation(diag);

        // Update comparison table if we have backtest data
        if (cachedBacktest) {
            renderComparisonTable();
        }
    } catch (e) {
        console.error('Failed to load diagnostics', e);
    }
}

// ================================================================
// Registry Table
// ================================================================

function renderRegistry(models) {
    const tbody = document.getElementById('registry-body');
    if (models.length === 0) {
        tbody.innerHTML = '<tr><td colspan="11" class="text-center text-muted">No models found</td></tr>';
        return;
    }
    tbody.innerHTML = models.map(m => {
        const badge = m.status === 'production'
            ? '<span class="badge bg-success">production</span>'
            : m.status === 'candidate'
                ? '<span class="badge bg-warning text-dark">candidate</span>'
                : '<span class="badge bg-secondary">retired</span>';

        const promoteBtn = m.status === 'candidate'
            ? `<button class="btn btn-sm btn-outline-success" onclick="promptPromote()" title="Promote to production"><i class="bi bi-rocket"></i></button>`
            : '';

        return `<tr>
            <td><code>${m.model_version || '—'}</code></td>
            <td>${badge}</td>
            <td>${m.cv_avg_accuracy != null ? (m.cv_avg_accuracy * 100).toFixed(1) + '%' : '—'}</td>
            <td>${m.cv_avg_auc != null ? m.cv_avg_auc.toFixed(3) : '—'}</td>
            <td>${m.cv_avg_loss != null ? m.cv_avg_loss.toFixed(4) : '—'}</td>
            <td>${m.hidden_dim || '—'}</td>
            <td>${m.learning_rate || '—'}</td>
            <td>${m.dropout || '—'}</td>
            <td>${m.epochs || '—'}</td>
            <td>${m.trained_at || '—'}</td>
            <td>${promoteBtn}</td>
        </tr>`;
    }).join('');
}

// ================================================================
// ROC Curve
// ================================================================

function renderROC(diag) {
    const canvas = document.getElementById('roc-chart');
    if (rocChart) rocChart.destroy();

    const fpr = diag.roc_fpr || [];
    const tpr = diag.roc_tpr || [];
    const auc = diag.auc != null ? diag.auc.toFixed(3) : '?';

    if (fpr.length === 0) {
        rocChart = new Chart(canvas, {
            type: 'line',
            data: { datasets: [] },
            options: { plugins: { title: { display: true, text: 'No ROC data available' } } }
        });
        return;
    }

    const rocData = fpr.map((x, i) => ({ x, y: tpr[i] }));
    const diagLine = [{ x: 0, y: 0 }, { x: 1, y: 1 }];

    rocChart = new Chart(canvas, {
        type: 'scatter',
        data: {
            datasets: [
                {
                    label: `ROC Curve (AUC = ${auc})`,
                    data: rocData,
                    showLine: true,
                    borderColor: 'rgba(13,202,240,.9)',
                    backgroundColor: 'rgba(13,202,240,.1)',
                    fill: true,
                    pointRadius: 0,
                    borderWidth: 2,
                },
                {
                    label: 'Random (AUC = 0.5)',
                    data: diagLine,
                    showLine: true,
                    borderColor: 'rgba(255,255,255,.2)',
                    borderDash: [6, 4],
                    pointRadius: 0,
                    borderWidth: 1,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { title: { display: true, text: 'False Positive Rate' }, min: 0, max: 1 },
                y: { title: { display: true, text: 'True Positive Rate' }, min: 0, max: 1 }
            },
            plugins: {
                legend: { position: 'bottom' }
            }
        }
    });
}

// ================================================================
// Confusion Matrix
// ================================================================

function renderConfusionMatrix(cm) {
    const container = document.getElementById('cm-container');
    if (!cm) {
        container.innerHTML = '<p class="text-muted">No confusion matrix data available</p>';
        return;
    }

    const total = cm.tp + cm.fp + cm.tn + cm.fn || 1;
    container.innerHTML = `
        <div class="mb-2 text-muted small">Predicted &rarr;</div>
        <div class="d-flex gap-2 mb-1">
            <div class="cm-cell cm-tp">
                ${cm.tp}<small>True Pos</small>
            </div>
            <div class="cm-cell cm-fp">
                ${cm.fp}<small>False Pos</small>
            </div>
        </div>
        <div class="d-flex gap-2">
            <div class="cm-cell cm-fn">
                ${cm.fn}<small>False Neg</small>
            </div>
            <div class="cm-cell cm-tn">
                ${cm.tn}<small>True Neg</small>
            </div>
        </div>
        <div class="mt-2 text-muted small">
            Accuracy: ${((cm.tp + cm.tn) / total * 100).toFixed(1)}%
            &middot; Precision: ${(cm.tp / (cm.tp + cm.fp || 1) * 100).toFixed(1)}%
            &middot; Recall: ${(cm.tp / (cm.tp + cm.fn || 1) * 100).toFixed(1)}%
        </div>`;
}

// ================================================================
// Year Breakdown
// ================================================================

function renderYearBreakdown(segments) {
    const tbody = document.getElementById('year-body');
    if (segments.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">No data</td></tr>';
        return;
    }
    tbody.innerHTML = segments.map(s => `
        <tr>
            <td>${s.year}</td>
            <td>${s.game_count}</td>
            <td>${s.accuracy != null ? (s.accuracy * 100).toFixed(1) + '%' : '—'}</td>
            <td>${s.auc != null ? s.auc.toFixed(3) : '—'}</td>
        </tr>`).join('');
}

// ================================================================
// Recommendation Banner
// ================================================================

function renderRecommendation(diag) {
    const el = document.getElementById('recommendation');
    if (!diag.recommendation) {
        el.style.display = 'none';
        return;
    }
    const rec = diag.recommendation;
    const isPromote = rec.action === 'promote';
    el.style.display = 'block';
    el.className = `recommendation-banner ${isPromote ? 'promote' : 'keep'}`;
    el.innerHTML = `
        <div class="d-flex justify-content-between align-items-center">
            <div>
                <strong>${isPromote ? '&#10004; Recommend Promotion' : '&#9888; Keep Current Production'}</strong>
                <div class="small text-muted mt-1">${rec.reason}</div>
            </div>
            ${isPromote ? '<button class="btn btn-success btn-sm" onclick="promptPromote()"><i class="bi bi-rocket me-1"></i>Push to Production</button>' : ''}
        </div>`;
}

// ================================================================
// Backtest
// ================================================================

async function runBacktest() {
    const sport = document.getElementById('diag-sport').value;
    const target = document.getElementById('diag-target').value;
    const months = document.getElementById('bt-months').value;

    const btn = document.getElementById('btn-run-backtest');
    const placeholder = document.getElementById('bt-placeholder');
    const summaryEl = document.getElementById('bt-summary');

    // Loading state
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Running...';
    placeholder.innerHTML = '<div class="spinner-border spinner-border-sm text-info me-2" role="status"></div>Running historical backtest — this may take a minute...';

    try {
        const resp = await fetch(`/api/backtest?sport=${sport}&target=${target}&months=${months}`);
        const data = await resp.json();

        if (data.status === 'error') {
            placeholder.innerHTML = `<div class="text-danger"><i class="bi bi-exclamation-triangle me-1"></i>${data.message}</div>`;
            summaryEl.style.display = 'none';
            return;
        }

        cachedBacktest = data;

        // Hide placeholder, show summary
        placeholder.style.display = 'none';
        summaryEl.style.display = '';

        const summary = data.summary || {};

        // Update summary cards
        setText('bt-total-bets', summary.total_bets || 0);
        setText('bt-accuracy', summary.accuracy != null ? (summary.accuracy * 100).toFixed(1) + '%' : '—');
        setText('bt-auc', summary.auc != null ? summary.auc.toFixed(3) : '—');

        const roiEl = document.getElementById('bt-roi');
        const roiPct = summary.roi_pct || 0;
        roiEl.textContent = (roiPct >= 0 ? '+' : '') + roiPct.toFixed(1) + '%';
        roiEl.className = 'fw-bold ' + (roiPct >= 0 ? 'text-success' : 'text-danger');

        const pnlEl = document.getElementById('bt-pnl');
        const pnl = summary.total_pnl || 0;
        pnlEl.textContent = (pnl >= 0 ? '+' : '') + '$' + Math.abs(pnl).toFixed(2);
        pnlEl.className = 'fw-bold ' + (pnl >= 0 ? 'text-success' : 'text-danger');

        setText('bt-drawdown', '-$' + (summary.max_drawdown || 0).toFixed(2));

        // Render charts
        renderBacktestPnlChart(data);
        renderBacktestRoiChart(data);

        // Update comparison table
        renderComparisonTable();

    } catch (e) {
        placeholder.innerHTML = '<div class="text-danger"><i class="bi bi-exclamation-triangle me-1"></i>Backtest request failed</div>';
        console.error('Backtest failed', e);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-play-fill me-1"></i>Run Backtest';
    }
}

function renderBacktestPnlChart(data) {
    const canvas = document.getElementById('bt-pnl-chart');
    if (btPnlChart) btPnlChart.destroy();

    const weeks = (data.weekly_results || []).filter(w => w.bets > 0);
    const labels = weeks.map(w => w.week);
    const cumPnl = data.cumulative_pnl || [];

    // Build filtered cumulative P/L (only weeks with bets)
    const pnlData = [];
    let idx = 0;
    for (const wr of data.weekly_results || []) {
        if (wr.bets > 0) {
            pnlData.push(cumPnl[idx] || 0);
        }
        idx++;
    }

    btPnlChart = new Chart(canvas, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: 'Cumulative P/L ($)',
                data: pnlData,
                borderColor: pnlData.length > 0 && pnlData[pnlData.length - 1] >= 0 ? 'rgba(25,135,84,1)' : 'rgba(220,53,69,1)',
                borderWidth: 2,
                pointRadius: 1,
                fill: {
                    target: 'origin',
                    above: 'rgba(25,135,84,0.15)',
                    below: 'rgba(220,53,69,0.15)',
                },
                tension: 0.3,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                title: {
                    display: true,
                    text: 'Cumulative P/L — $100/week bankroll, Quarter-Kelly',
                    color: 'rgba(255,255,255,0.7)',
                    font: { size: 12 },
                },
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
                    ticks: { maxRotation: 45, autoSkipPadding: 15, maxTicksLimit: 20 },
                    grid: { color: 'rgba(255,255,255,0.05)' },
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

function renderBacktestRoiChart(data) {
    const canvas = document.getElementById('bt-roi-chart');
    if (btRoiChart) btRoiChart.destroy();

    const weeks = (data.weekly_results || []).filter(w => w.bets > 0);
    const labels = weeks.map(w => w.week);
    const roiData = weeks.map(w => +(w.roi * 100).toFixed(1));
    const colors = roiData.map(v => v >= 0 ? 'rgba(25,135,84,0.7)' : 'rgba(220,53,69,0.7)');

    btRoiChart = new Chart(canvas, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: 'Weekly ROI %',
                data: roiData,
                backgroundColor: colors,
                borderWidth: 0,
                barPercentage: 0.9,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                title: {
                    display: true,
                    text: 'Weekly ROI %',
                    color: 'rgba(255,255,255,0.7)',
                    font: { size: 12 },
                },
                tooltip: {
                    callbacks: {
                        label: ctx => ctx.parsed.y.toFixed(1) + '%'
                    }
                }
            },
            scales: {
                x: {
                    display: false,
                },
                y: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: {
                        callback: v => v.toFixed(0) + '%'
                    }
                }
            }
        }
    });
}

// ================================================================
// CV vs Backtest Comparison Table
// ================================================================

function renderComparisonTable() {
    const tbody = document.getElementById('cv-bt-comparison-body');

    if (!cachedDiagnostics && !cachedBacktest) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">Run backtest and load diagnostics to compare</td></tr>';
        return;
    }

    const cvAuc = cachedDiagnostics?.auc;
    const cvAcc = cachedDiagnostics?.confusion_matrix
        ? ((cachedDiagnostics.confusion_matrix.tp + cachedDiagnostics.confusion_matrix.tn) /
           (cachedDiagnostics.confusion_matrix.tp + cachedDiagnostics.confusion_matrix.fp +
            cachedDiagnostics.confusion_matrix.fn + cachedDiagnostics.confusion_matrix.tn))
        : null;

    const btSummary = cachedBacktest?.summary || {};
    const btAuc = btSummary.auc;
    const btAcc = btSummary.accuracy;
    const btRoi = btSummary.roi_pct;
    const btPnl = btSummary.total_pnl;

    const rows = [
        {
            metric: 'Accuracy',
            cv: cvAcc != null ? (cvAcc * 100).toFixed(1) + '%' : '—',
            bt: btAcc != null ? (btAcc * 100).toFixed(1) + '%' : '—',
            delta: (cvAcc != null && btAcc != null) ? formatDelta((btAcc - cvAcc) * 100, '%') : '—',
        },
        {
            metric: 'AUC',
            cv: cvAuc != null ? cvAuc.toFixed(3) : '—',
            bt: btAuc != null ? btAuc.toFixed(3) : '—',
            delta: (cvAuc != null && btAuc != null) ? formatDelta(btAuc - cvAuc, '', 3) : '—',
        },
        {
            metric: 'Backtest ROI',
            cv: '<span class="text-muted small">N/A</span>',
            bt: btRoi != null ? (btRoi >= 0 ? '+' : '') + btRoi.toFixed(1) + '%' : '—',
            delta: '—',
        },
        {
            metric: 'Backtest P/L (24mo)',
            cv: '<span class="text-muted small">N/A</span>',
            bt: btPnl != null ? (btPnl >= 0 ? '+' : '') + '$' + Math.abs(btPnl).toFixed(2) : '—',
            delta: '—',
        },
    ];

    tbody.innerHTML = rows.map(r => `
        <tr>
            <td class="fw-bold">${r.metric}</td>
            <td>${r.cv}</td>
            <td>${r.bt}</td>
            <td>${r.delta}</td>
        </tr>`).join('');
}

function formatDelta(value, suffix, decimals) {
    decimals = decimals || 1;
    suffix = suffix || '';
    const sign = value >= 0 ? '+' : '';
    const color = value >= 0 ? 'text-success' : 'text-danger';
    return `<span class="${color}">${sign}${value.toFixed(decimals)}${suffix}</span>`;
}

// ================================================================
// User-Triggered Refit
// ================================================================

async function startRefit() {
    const btn = document.getElementById('btn-refit');
    const progress = document.getElementById('refit-progress');
    const placeholder = document.getElementById('refit-placeholder');
    const result = document.getElementById('refit-result');
    const statusText = document.getElementById('refit-status-text');
    const progressBar = document.getElementById('refit-progress-bar');

    btn.disabled = true;
    placeholder.style.display = 'none';
    result.style.display = 'none';
    progress.style.display = '';

    // Simulate progress
    let pct = 0;
    const progressInterval = setInterval(() => {
        pct = Math.min(pct + 2 + Math.random() * 3, 90);
        progressBar.style.width = pct + '%';
        if (pct < 30) statusText.textContent = 'Training new candidate model...';
        else if (pct < 60) statusText.textContent = 'Cross-validating (5 folds)...';
        else if (pct < 80) statusText.textContent = 'Computing metrics...';
        else statusText.textContent = 'Finalizing...';
    }, 500);

    try {
        const resp = await fetch('/refit-model', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sport: currentSport || document.getElementById('diag-sport').value,
                target: currentTarget || document.getElementById('diag-target').value,
                cv_folds: 5,
            })
        });
        const data = await resp.json();
        clearInterval(progressInterval);
        progressBar.style.width = '100%';

        if (!resp.ok || data.status === 'error') {
            statusText.textContent = 'Refit failed: ' + (data.message || 'Unknown error');
            statusText.classList.remove('text-warning');
            statusText.classList.add('text-danger');
            setTimeout(() => {
                progress.style.display = 'none';
                placeholder.style.display = '';
                placeholder.innerHTML = '<div class="text-danger"><i class="bi bi-exclamation-triangle me-1"></i>Refit failed. Check server logs and try again.</div>';
            }, 3000);
            return;
        }

        cachedRefitResult = data;

        // Show refit result
        progress.style.display = 'none';
        result.style.display = '';

        renderRefitComparison(data);

        // Refresh registry and diagnostics
        loadDiagnostics();

    } catch (e) {
        clearInterval(progressInterval);
        statusText.textContent = 'Refit request failed';
        statusText.classList.remove('text-warning');
        statusText.classList.add('text-danger');
        console.error('Refit failed', e);
    } finally {
        btn.disabled = false;
    }
}

function renderRefitComparison(refitData) {
    const tbody = document.getElementById('refit-comparison-body');

    // Extract metrics from refit result
    const cv = refitData.cv_result || {};
    const train = refitData.train_result || {};

    // Try to get production model info from cached diagnostics
    const prodAcc = cachedDiagnostics?.confusion_matrix
        ? ((cachedDiagnostics.confusion_matrix.tp + cachedDiagnostics.confusion_matrix.tn) /
           (cachedDiagnostics.confusion_matrix.tp + cachedDiagnostics.confusion_matrix.fp +
            cachedDiagnostics.confusion_matrix.fn + cachedDiagnostics.confusion_matrix.tn))
        : null;
    const prodAuc = cachedDiagnostics?.auc;

    const candAcc = cv.avg_accuracy != null ? cv.avg_accuracy : null;
    const candAuc = cv.avg_auc != null ? cv.avg_auc : null;
    const candLoss = cv.avg_loss != null ? cv.avg_loss : null;

    const rows = [
        {
            metric: 'CV Accuracy',
            prod: prodAcc != null ? (prodAcc * 100).toFixed(1) + '%' : '—',
            cand: candAcc != null ? (candAcc * 100).toFixed(1) + '%' : '—',
            delta: (prodAcc != null && candAcc != null) ? formatDelta((candAcc - prodAcc) * 100, '%') : '—',
        },
        {
            metric: 'CV AUC',
            prod: prodAuc != null ? prodAuc.toFixed(3) : '—',
            cand: candAuc != null ? candAuc.toFixed(3) : '—',
            delta: (prodAuc != null && candAuc != null) ? formatDelta(candAuc - prodAuc, '', 3) : '—',
        },
        {
            metric: 'CV Loss',
            prod: '—',
            cand: candLoss != null ? candLoss.toFixed(4) : '—',
            delta: '—',
        },
        {
            metric: 'Model Version',
            prod: refitData.production_version || '—',
            cand: refitData.model_version || train.model_version || '—',
            delta: '',
        },
    ];

    tbody.innerHTML = rows.map(r => `
        <tr>
            <td class="fw-bold">${r.metric}</td>
            <td>${r.prod}</td>
            <td>${r.cand}</td>
            <td>${r.delta}</td>
        </tr>`).join('');
}

function discardCandidate() {
    const result = document.getElementById('refit-result');
    const placeholder = document.getElementById('refit-placeholder');

    result.style.display = 'none';
    placeholder.style.display = '';
    placeholder.innerHTML = '<div class="text-muted"><i class="bi bi-info-circle me-1"></i>Candidate discarded. The current production model remains active.</div>';

    cachedRefitResult = null;
}

// ================================================================
// Promote
// ================================================================

function promptPromote() {
    const modal = new bootstrap.Modal(document.getElementById('promoteModal'));
    const sport = currentSport || document.getElementById('diag-sport').value;
    const target = currentTarget || document.getElementById('diag-target').value;

    document.getElementById('promote-body').querySelector('p').textContent =
        `Promote the candidate ${sport}/${target} model to production? This will retire the current production model.`;

    // Show metrics summary if available
    const summaryEl = document.getElementById('promote-metrics-summary');
    if (cachedRefitResult) {
        const cv = cachedRefitResult.cv_result || {};
        summaryEl.innerHTML = `
            <div class="small">
                <strong>Candidate Metrics:</strong>
                CV Accuracy: ${cv.avg_accuracy != null ? (cv.avg_accuracy * 100).toFixed(1) + '%' : '—'}
                &middot; CV AUC: ${cv.avg_auc != null ? cv.avg_auc.toFixed(3) : '—'}
                &middot; CV Loss: ${cv.avg_loss != null ? cv.avg_loss.toFixed(4) : '—'}
            </div>`;
    } else {
        summaryEl.innerHTML = '';
    }

    modal.show();
}

async function confirmPromote() {
    const btn = document.getElementById('confirm-promote-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Promoting...';

    try {
        const resp = await fetch('/promote-model', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sport: currentSport || document.getElementById('diag-sport').value,
                target: currentTarget || document.getElementById('diag-target').value,
                cv_folds: 5,
            })
        });
        const data = await resp.json();
        if (resp.ok) {
            alert('Model promoted to production successfully!');
            bootstrap.Modal.getInstance(document.getElementById('promoteModal')).hide();

            // Clear refit result
            const refitResult = document.getElementById('refit-result');
            const refitPlaceholder = document.getElementById('refit-placeholder');
            refitResult.style.display = 'none';
            refitPlaceholder.style.display = '';
            refitPlaceholder.innerHTML = '<div class="text-success"><i class="bi bi-check-circle me-1"></i>Candidate promoted to production. The new model is now active.</div>';
            cachedRefitResult = null;

            loadDiagnostics();
        } else {
            alert('Promotion failed: ' + (data.message || JSON.stringify(data)));
        }
    } catch (e) {
        alert('Promotion failed: ' + e.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-rocket me-1"></i>Promote';
    }
}

// ================================================================
// Helpers
// ================================================================

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}
