/**
 * Platform Dispatcher — Feedback Dashboard
 * Loads predictions, handles voting, and manages the feedback UI.
 */

let currentFilter = 'all';
let currentOffset = 0;
const PAGE_SIZE = 50;
let activeModalId = null;

// ── Init ────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    loadPredictions();
    setupFilterButtons();
    setupVoteModal();
    populateIntentDropdown();
});

// ── Stats ───────────────────────────────────────────────────────────────────

async function loadStats() {
    try {
        const resp = await fetch('/api/predictions/stats');
        const data = await resp.json();
        document.getElementById('stat-total').textContent = (data.total || 0).toLocaleString();
        document.getElementById('stat-accuracy').textContent =
            data.accuracy_pct != null ? `${data.accuracy_pct}%` : '—';
        document.getElementById('stat-upvotes').textContent = (data.upvotes || 0).toLocaleString();
        document.getElementById('stat-downvotes').textContent = (data.downvotes || 0).toLocaleString();
        document.getElementById('stat-pending').textContent = (data.pending || 0).toLocaleString();
        document.getElementById('stat-response').textContent =
            data.avg_response_ms != null ? `${data.avg_response_ms}ms` : '—';
    } catch (e) {
        console.warn('Failed to load stats', e);
    }
}

// ── Predictions Table ───────────────────────────────────────────────────────

async function loadPredictions(append = false) {
    const tbody = document.getElementById('predictions-table');
    const loadMore = document.getElementById('load-more');

    if (!append) {
        currentOffset = 0;
        tbody.innerHTML = `<tr><td colspan="9" class="text-center text-muted py-4">
            <div class="spinner-border spinner-border-sm text-info" role="status"></div>
            Loading…</td></tr>`;
    }

    try {
        const filter = currentFilter === 'all' ? '' : `&vote=${currentFilter}`;
        const resp = await fetch(`/api/predictions?limit=${PAGE_SIZE}&offset=${currentOffset}${filter}`);
        const data = await resp.json();

        if (!append) tbody.innerHTML = '';

        if (data.predictions.length === 0 && !append) {
            tbody.innerHTML = `<tr><td colspan="9" class="text-center text-muted py-4">
                No predictions found</td></tr>`;
            loadMore.style.display = 'none';
            return;
        }

        for (const p of data.predictions) {
            tbody.appendChild(createPredictionRow(p));
        }

        currentOffset += data.predictions.length;
        loadMore.style.display = data.predictions.length === PAGE_SIZE ? '' : 'none';

    } catch (e) {
        if (!append) {
            tbody.innerHTML = `<tr><td colspan="9" class="text-center text-danger py-4">
                Failed to load predictions</td></tr>`;
        }
        console.warn('Failed to load predictions', e);
    }
}

function createPredictionRow(p) {
    const tr = document.createElement('tr');
    const dt = new Date(p.created_at);
    const timeStr = dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) +
                    ' ' + dt.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });

    const confClass = p.confidence >= 0.8 ? 'confidence-high' :
                      p.confidence >= 0.6 ? 'confidence-med' : 'confidence-low';

    let voteHtml;
    if (p.vote === 'up') {
        voteHtml = '<span class="text-success"><i class="bi bi-hand-thumbs-up-fill"></i></span>';
    } else if (p.vote === 'down') {
        voteHtml = `<span class="text-danger"><i class="bi bi-hand-thumbs-down-fill"></i></span>`;
        if (p.correct_intent) {
            voteHtml += ` <span class="intent-badge small">${p.correct_intent}</span>`;
        }
    } else {
        voteHtml = '<span class="text-muted">—</span>';
    }

    tr.innerHTML = `
        <td class="text-nowrap small">${timeStr}</td>
        <td><span class="badge bg-secondary">${p.source}</span></td>
        <td class="user-text-cell" title="${escapeHtml(p.user_text)}">${escapeHtml(p.user_text)}</td>
        <td><span class="intent-badge">${p.predicted_intent}</span></td>
        <td class="${confClass} fw-bold">${(p.confidence * 100).toFixed(0)}%</td>
        <td class="small text-muted">${p.ollama_model || '—'}</td>
        <td class="small">${p.response_time_ms}ms</td>
        <td>${voteHtml}</td>
        <td>
            <button class="vote-btn vote-btn-up${p.vote === 'up' ? ' active' : ''}"
                    onclick="quickVote(${p.id}, 'up')" title="Correct">
                <i class="bi bi-hand-thumbs-up"></i>
            </button>
            <button class="vote-btn vote-btn-down${p.vote === 'down' ? ' active' : ''}"
                    onclick="openVoteModal(${p.id}, '${escapeHtml(p.user_text)}', '${p.predicted_intent}')"
                    title="Incorrect — provide feedback">
                <i class="bi bi-hand-thumbs-down"></i>
            </button>
        </td>
    `;
    return tr;
}

// ── Quick Vote (upvote) ─────────────────────────────────────────────────────

async function quickVote(id, vote) {
    try {
        const resp = await fetch(`/api/predictions/${id}/vote`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ vote }),
        });
        if (resp.ok) {
            loadStats();
            loadPredictions();
        }
    } catch (e) {
        console.warn('Vote failed', e);
    }
}

// ── Vote Modal (downvote with details) ──────────────────────────────────────

function openVoteModal(id, userText, predicted) {
    activeModalId = id;
    document.getElementById('modal-user-text').textContent = userText;
    document.getElementById('modal-predicted').textContent = predicted;
    document.getElementById('vote-down').checked = true;
    document.getElementById('correct-intent-group').style.display = '';
    document.getElementById('correct-intent').value = '';
    document.getElementById('feedback-note').value = '';

    const modal = new bootstrap.Modal(document.getElementById('voteModal'));
    modal.show();
}

function setupVoteModal() {
    // Toggle correct intent field based on vote type
    document.querySelectorAll('input[name="vote"]').forEach(el => {
        el.addEventListener('change', () => {
            const isDown = document.getElementById('vote-down').checked;
            document.getElementById('correct-intent-group').style.display = isDown ? '' : 'none';
        });
    });

    // Submit button
    document.getElementById('submit-vote').addEventListener('click', async () => {
        const vote = document.querySelector('input[name="vote"]:checked')?.value;
        if (!vote || !activeModalId) return;

        const payload = { vote };
        if (vote === 'down') {
            const ci = document.getElementById('correct-intent').value;
            if (ci) payload.correct_intent = ci;
        }
        const note = document.getElementById('feedback-note').value.trim();
        if (note) payload.note = note;

        try {
            const resp = await fetch(`/api/predictions/${activeModalId}/vote`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (resp.ok) {
                bootstrap.Modal.getInstance(document.getElementById('voteModal')).hide();
                loadStats();
                loadPredictions();
            }
        } catch (e) {
            console.warn('Vote submit failed', e);
        }
    });
}

// ── Filters ─────────────────────────────────────────────────────────────────

function setupFilterButtons() {
    document.querySelectorAll('[data-filter]').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('[data-filter]').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentFilter = btn.dataset.filter;
            loadPredictions();
        });
    });

    document.getElementById('load-more').addEventListener('click', () => loadPredictions(true));
}

// ── Intent Dropdown ─────────────────────────────────────────────────────────

function populateIntentDropdown() {
    const select = document.getElementById('correct-intent');
    for (const intent of INTENTS) {
        const opt = document.createElement('option');
        opt.value = intent.id;
        opt.textContent = `${intent.id} — ${intent.desc}`;
        select.appendChild(opt);
    }
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
}
