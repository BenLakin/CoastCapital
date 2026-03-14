/* ============================================================
   model_performance.js — Model Performance page logic
   ============================================================ */

let accuracyChart = null;
let aucChart = null;

document.addEventListener('DOMContentLoaded', () => {
    loadPerformance();
    document.getElementById('sport-filter').addEventListener('change', loadPerformance);
});

async function loadPerformance() {
    const sport = document.getElementById('sport-filter').value;
    const qs = sport ? `?sport=${sport}` : '';
    try {
        const resp = await fetch(`/api/model-performance${qs}`);
        const data = await resp.json();
        renderCards(data.models || []);
        renderCharts(data.models || []);
        renderTable(data.models || []);
    } catch (e) {
        console.error('Failed to load model performance', e);
    }
}

// ------------------------------------------------------------------ Cards
function renderCards(models) {
    const container = document.getElementById('perf-cards');
    const spinner = document.getElementById('perf-spinner');
    if (spinner) spinner.remove();
    // Remove old cards (not the spinner)
    container.querySelectorAll('.perf-card-col').forEach(el => el.remove());

    if (models.length === 0) {
        const col = document.createElement('div');
        col.className = 'col-12 perf-card-col';
        col.innerHTML = '<p class="text-muted">No production models found. Train and promote a model first.</p>';
        container.appendChild(col);
        return;
    }

    for (const m of models) {
        const acc = m.cv_avg_accuracy != null ? (m.cv_avg_accuracy * 100).toFixed(1) + '%' : '—';
        const auc = m.cv_avg_auc != null ? m.cv_avg_auc.toFixed(3) : '—';
        const accColor = m.cv_avg_accuracy >= 0.55 ? 'text-success' : (m.cv_avg_accuracy >= 0.50 ? 'text-warning' : 'text-danger');

        const col = document.createElement('div');
        col.className = 'col-md-4 col-lg-3 perf-card-col';
        col.innerHTML = `
            <div class="card h-100">
                <div class="card-header d-flex justify-content-between">
                    <span>${m.sport.toUpperCase()}</span>
                    <span class="badge bg-info">${m.target}</span>
                </div>
                <div class="card-body text-center">
                    <div class="stat-value ${accColor}">${acc}</div>
                    <div class="stat-label">CV Accuracy</div>
                    <hr class="my-2 border-secondary">
                    <div class="stat-value text-info" style="font-size:1.4rem">${auc}</div>
                    <div class="stat-label">CV AUC</div>
                </div>
                <div class="card-footer text-muted small text-center">
                    v${m.model_version || '?'} &middot; ${m.train_rows || '?'} rows
                </div>
            </div>`;
        container.appendChild(col);
    }
}

// ------------------------------------------------------------------ Charts
function renderCharts(models) {
    const labels = models.map(m => `${m.sport} / ${m.target}`);
    const accData = models.map(m => m.cv_avg_accuracy != null ? +(m.cv_avg_accuracy * 100).toFixed(1) : 0);
    const aucData = models.map(m => m.cv_avg_auc != null ? +m.cv_avg_auc.toFixed(3) : 0);

    const colors = models.map((_, i) => [
        'rgba(13,110,253,.7)', 'rgba(13,202,240,.7)', 'rgba(25,135,84,.7)',
        'rgba(253,126,20,.7)', 'rgba(111,66,193,.7)', 'rgba(220,53,69,.7)'
    ][i % 6]);

    // Accuracy chart
    if (accuracyChart) accuracyChart.destroy();
    accuracyChart = new Chart(document.getElementById('accuracy-chart'), {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: 'Accuracy %',
                data: accData,
                backgroundColor: colors,
                borderRadius: 4,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, max: 100, title: { display: true, text: 'Accuracy %' } }
            }
        }
    });

    // AUC chart
    if (aucChart) aucChart.destroy();
    aucChart = new Chart(document.getElementById('auc-chart'), {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: 'AUC',
                data: aucData,
                backgroundColor: colors,
                borderRadius: 4,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, max: 1, title: { display: true, text: 'AUC' } }
            }
        }
    });
}

// ------------------------------------------------------------------ Table
function renderTable(models) {
    const tbody = document.getElementById('model-table-body');
    if (models.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted">No models found</td></tr>';
        return;
    }
    tbody.innerHTML = models.map(m => {
        const statusBadge = m.status === 'production'
            ? '<span class="badge bg-success">production</span>'
            : `<span class="badge bg-secondary">${m.status}</span>`;
        return `<tr>
            <td>${m.sport}</td>
            <td>${m.target}</td>
            <td><code>${m.model_version || '—'}</code></td>
            <td>${statusBadge}</td>
            <td>${m.cv_avg_accuracy != null ? (m.cv_avg_accuracy * 100).toFixed(1) + '%' : '—'}</td>
            <td>${m.cv_avg_auc != null ? m.cv_avg_auc.toFixed(3) : '—'}</td>
            <td>${m.cv_avg_loss != null ? m.cv_avg_loss.toFixed(4) : '—'}</td>
            <td>${m.cv_folds || '—'}</td>
            <td>${m.train_rows || '—'}</td>
            <td>${m.promoted_at || '—'}</td>
        </tr>`;
    }).join('');
}
