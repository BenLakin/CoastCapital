/* ============================================================
   FinanceAgent Market Dashboard — Main Application
   ============================================================ */
(function () {
  'use strict';

  // ── Config ──────────────────────────────────────────────────────────────
  const DEFAULT_WATCHLIST  = ['META','AAPL','Z','NVDA','GOOGL','GLD','BTC-USD'];
  const REFRESH_MS         = 5 * 60 * 1000;   // 5-min full refresh
  const OVERVIEW_REFRESH   = 3 * 60 * 1000;   // 3-min overview
  const STORAGE_KEY        = 'fa_watchlist_v2';
  const CHART_POINTS       = 30;               // sparkline data points

  // ── State ────────────────────────────────────────────────────────────────
  let watchlist       = loadWatchlist();
  let activeHlTicker  = watchlist[0] || DEFAULT_WATCHLIST[0];
  let sparkCharts     = new Map();       // ticker → Chart instance
  let refreshTimer    = null;
  let progressTimer   = null;
  let refreshStart    = Date.now();

  // ── DOM refs ────────────────────────────────────────────────────────────
  const $ = id => document.getElementById(id);
  const el = {
    statusBadge:    $('marketStatusBadge'),
    statusDot:      $('statusDot'),
    statusText:     $('marketStatusText'),
    headerDate:     $('headerDate'),
    lastUpdate:     $('lastUpdate'),
    btnRefresh:     $('btnRefresh'),
    btnSettings:    $('btnSettings'),
    tickerInner:    $('tickerInner'),
    overviewBar:    $('overviewBar'),
    bigNoiseList:   $('bigNoiseList'),
    gainersList:    $('gainersList'),
    losersList:     $('losersList'),
    watchlistGrid:  $('watchlistGrid'),
    watchlistCount: $('watchlistCount'),
    headlinesFeed:  $('headlinesFeed'),
    headlineTabs:   $('headlineTabs'),
    settingsModal:  $('settingsModal'),
    btnCloseSet:    $('btnCloseSettings'),
    newTickerInput: $('newTickerInput'),
    btnConfirmAdd:  $('btnConfirmAdd'),
    currentTickers: $('currentTickers'),
    btnResetWL:     $('btnResetWatchlist'),
    btnAddTicker:   $('btnAddTicker'),
    refreshProgress:$('refreshProgress'),
    hlIndicesCards: $('hlIndicesCards'),
    hlPctCards:     $('hlPctCards'),
    hlMcapCards:    $('hlMcapCards'),
  };

  // ── Formatters ───────────────────────────────────────────────────────────
  function fmtPrice(v, decimals) {
    if (v == null) return '—';
    const d = decimals !== undefined ? decimals : (v >= 1000 ? 0 : v >= 10 ? 2 : v >= 1 ? 3 : 4);
    return '$' + v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
  }

  function fmtPct(v) {
    if (v == null) return '—';
    const sign = v >= 0 ? '+' : '';
    return sign + v.toFixed(2) + '%';
  }

  function fmtChange(v) {
    if (v == null) return '—';
    const sign = v >= 0 ? '+' : '-';
    return sign + '$' + Math.abs(v).toFixed(2);
  }

  function pctClass(v) { return v == null ? '' : v >= 0 ? 'up' : 'down'; }
  function arrow(v)    { return v >= 0 ? '▲' : '▼'; }

  // ── API ──────────────────────────────────────────────────────────────────
  async function api(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }

  // ── Market Status ────────────────────────────────────────────────────────
  async function loadStatus() {
    try {
      const d = await api('/api/v1/market/status');
      el.statusDot.className  = 'status-dot ' + (d.is_open ? 'open' : 'closed');
      el.statusText.textContent = d.is_open ? 'Market Open' : 'Market Closed';
      el.headerDate.textContent = d.day + ' · ' + d.time_utc;
    } catch { /* silent */ }
  }

  // ── Overview Bar ─────────────────────────────────────────────────────────
  async function loadOverview() {
    try {
      const items = await api('/api/v1/market/overview');
      if (!items.length) return;

      el.overviewBar.innerHTML = items.map(it => `
        <div class="ov-item">
          <div class="ov-label">${it.label}</div>
          <div class="ov-price">${fmtOverviewPrice(it.symbol, it.price)}</div>
          <div class="ov-change ${pctClass(it.change_pct)}">
            ${arrow(it.change_pct)} ${fmtPct(it.change_pct)}
          </div>
        </div>`).join('');
    } catch (e) {
      console.warn('Overview error', e);
    }
  }

  function fmtOverviewPrice(sym, v) {
    if (v == null) return '—';
    // Indices (points, not dollars) — no $ prefix
    if (sym === '^GSPC' || sym === '^IXIC' || sym === '^DJI') {
      return v >= 1000 ? v.toLocaleString('en-US', { maximumFractionDigits: 0 }) : v.toFixed(2);
    }
    if (sym === '^VIX' || sym === '^TNX' || sym === '^IRX') return v.toFixed(2);
    if (sym === 'BTC-USD') return '$' + Math.round(v).toLocaleString();
    if (v >= 1000) return '$' + v.toLocaleString('en-US', { maximumFractionDigits: 0 });
    return '$' + v.toFixed(2);
  }

  // ── Ticker Tape ──────────────────────────────────────────────────────────
  async function loadTickerTape() {
    try {
      const tickers = watchlist.join(',');
      const items   = await api(`/api/v1/market/watchlist?tickers=${encodeURIComponent(tickers)}`);
      if (!items.length) return;

      const html = items.map(it => `
        <span class="tape-item">
          <span class="tape-sym">${it.ticker}</span>
          <span class="tape-price">${fmtPrice(it.price)}</span>
          <span class="tape-chg ${pctClass(it.change_pct)}">${fmtPct(it.change_pct)}</span>
        </span>`).join('');

      // Duplicate for seamless loop
      el.tickerInner.innerHTML = html + html;
    } catch (e) {
      console.warn('Tape error', e);
    }
  }

  // ── Fortune 500 Movers ───────────────────────────────────────────────────
  async function loadMovers() {
    try {
      const d = await api('/api/v1/market/movers');

      renderBigNoise(d.big_noise || []);
      renderMoverList(el.gainersList, d.gainers || [], 'up');
      renderMoverList(el.losersList,  d.losers  || [], 'down');
    } catch (e) {
      console.warn('Movers error', e);
      el.bigNoiseList.innerHTML = '<div class="no-data">Data unavailable</div>';
      el.gainersList.innerHTML  = '<div class="no-data">Data unavailable</div>';
      el.losersList.innerHTML   = '<div class="no-data">Data unavailable</div>';
    }
  }

  function renderBigNoise(items) {
    if (!items.length) {
      el.bigNoiseList.innerHTML = '<div class="no-data">No unusual activity detected</div>';
      return;
    }

    el.bigNoiseList.innerHTML = items.slice(0, 8).map(it => {
      const dir      = it.change_pct >= 0 ? 'up' : 'down';
      const isBigVol = it.volume_ratio >= 2.5;
      const isBigMov = Math.abs(it.change_pct) >= 3;

      const tags = [
        isBigMov ? `<span class="noise-tag">Big Move</span>` : '',
        isBigVol ? `<span class="noise-tag vol">${it.volume_ratio?.toFixed(1)}x Vol</span>` : '',
      ].filter(Boolean).join('');

      return `
      <div class="noise-card ${dir}">
        <div class="noise-left">
          <div class="noise-ticker">${it.ticker}</div>
          <div class="noise-name">${it.name}</div>
          <div class="noise-tags">${tags}</div>
        </div>
        <div class="noise-right">
          <div class="noise-price">${fmtPrice(it.price)}</div>
          <div class="noise-pct ${dir}">${fmtPct(it.change_pct)}</div>
        </div>
      </div>`;
    }).join('');
  }

  function renderMoverList(container, items, dir) {
    if (!items.length) {
      container.innerHTML = '<div class="no-data">No data</div>';
      return;
    }

    container.innerHTML = items.slice(0, 8).map((it, i) => {
      const volBadge = it.volume_ratio >= 2
        ? `<span class="vol-badge">${it.volume_ratio?.toFixed(1)}x vol</span>` : '';

      return `
      <div class="mover-row">
        <span class="mover-rank">${i + 1}</span>
        <div class="mover-left">
          <div class="mover-sym">${it.ticker} ${volBadge}</div>
          <div class="mover-name">${it.name}</div>
        </div>
        <div class="mover-right">
          <div class="mover-price">${fmtPrice(it.price)}</div>
          <div class="mover-pct ${dir}">${fmtPct(it.change_pct)}</div>
          <div class="mover-vol">${it.volume}</div>
        </div>
      </div>`;
    }).join('');
  }

  // ── Market Highlights ────────────────────────────────────────────────────
  async function loadHighlights() {
    try {
      const d = await api('/api/v1/market/highlights');
      renderIndexCards(d.indices || []);
      renderPctMovers(d.pct_gainers || [], d.pct_losers || []);
      renderMcapMovers(d.mcap_movers || []);
    } catch (e) {
      console.warn('Highlights error', e);
    }
  }

  function renderIndexCards(indices) {
    if (!indices.length) {
      el.hlIndicesCards.innerHTML = '<span class="no-data" style="font-size:10px">Unavailable</span>';
      return;
    }
    el.hlIndicesCards.innerHTML = indices.map(idx => `
        <div class="hl-card">
          <span class="hl-card-label">${escHtml(idx.label)}</span>
          <span class="hl-card-price">${fmtOverviewPrice(idx.symbol, idx.price)}</span>
          <span class="hl-card-change ${pctClass(idx.change_pct)}">${arrow(idx.change_pct)} ${fmtPct(idx.change_pct)}</span>
        </div>`).join('');
  }

  function renderPctMovers(gainers, losers) {
    // Top 3 gainers then top 3 losers
    const top = [
      ...gainers.slice(0, 3),
      ...losers.slice(0, 3),
    ];

    if (!top.length) {
      el.hlPctCards.innerHTML = '<span class="no-data" style="font-size:10px">Unavailable</span>';
      return;
    }
    el.hlPctCards.innerHTML = top.map(m => {
      const dir = pctClass(m.change_pct);
      return `
      <div class="hl-mover-card ${dir}">
        <div class="hl-mover-left">
          <span class="hl-mover-ticker">${escHtml(m.ticker)}</span>
          <span class="hl-mover-name">${escHtml(m.name || '')}</span>
        </div>
        <div class="hl-mover-right">
          <span class="hl-mover-pct ${dir}">${fmtPct(m.change_pct)}</span>
        </div>
      </div>`;
    }).join('');
  }

  function renderMcapMovers(mcap) {
    if (!mcap.length) {
      el.hlMcapCards.innerHTML = '<span class="no-data" style="font-size:10px">Unavailable</span>';
      return;
    }
    el.hlMcapCards.innerHTML = mcap.slice(0, 5).map(m => {
      const dir = pctClass(m.change_pct);
      return `
        <div class="hl-mover-card ${dir}">
          <div class="hl-mover-left">
            <span class="hl-mover-ticker">${escHtml(m.ticker)}</span>
            <span class="hl-mover-mcap">${m.market_cap_fmt || '—'}</span>
          </div>
          <div class="hl-mover-right">
            <span class="hl-mover-pct ${dir}">${fmtPct(m.change_pct)}</span>
            <span class="hl-mover-mcap">${m.change_pct >= 0 ? '+' : '-'}${m.mcap_change_fmt || '—'}</span>
          </div>
        </div>`;
    }).join('');
  }

  // ── Watchlist Cards ───────────────────────────────────────────────────────
  async function loadWatchlistCards() {
    try {
      const tickers = watchlist.join(',');
      const items   = await api(`/api/v1/market/watchlist?tickers=${encodeURIComponent(tickers)}`);

      el.watchlistCount.textContent = `${items.length} stocks`;
      renderWatchlistCards(items);
    } catch (e) {
      console.warn('Watchlist cards error', e);
      el.watchlistGrid.innerHTML = '<div class="no-data">Data unavailable</div>';
    }
  }

  function renderWatchlistCards(items) {
    // Destroy old chart instances
    sparkCharts.forEach(c => c.destroy());
    sparkCharts.clear();

    const cards = items.map(it => buildCard(it)).join('');
    const addCard = `
      <div class="watch-add-card" id="addCardBtn">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        <span>Add Ticker</span>
      </div>`;

    el.watchlistGrid.innerHTML = cards + addCard;

    // Draw sparklines
    items.forEach(it => drawSparkline(it));

    // Wire card clicks → headlines
    items.forEach(it => {
      const card = document.getElementById('card-' + it.ticker);
      if (card) {
        card.addEventListener('click', (e) => {
          if (e.target.closest('.wc-remove')) return;
          setActiveHeadlineTicker(it.ticker);
        });
      }
    });

    // Wire remove buttons
    items.forEach(it => {
      const btn = document.getElementById('rm-' + it.ticker);
      if (btn) btn.addEventListener('click', (e) => { e.stopPropagation(); removeTicker(it.ticker); });
    });

    // Wire add card
    const addBtn = document.getElementById('addCardBtn');
    if (addBtn) addBtn.addEventListener('click', openSettings);

    // Mark active card
    markActiveCard(activeHlTicker);
  }

  function buildCard(it) {
    const dir     = it.positive ? 'up' : 'down';
    const weekPct = it.week_pct  != null ? it.week_pct  : null;
    const monPct  = it.month_pct != null ? it.month_pct : null;

    const pRange = it.lo_52w && it.hi_52w
      ? `${fmtPrice(it.lo_52w)} – ${fmtPrice(it.hi_52w)}`
      : '—';

    return `
    <div class="watch-card ${dir}" id="card-${it.ticker}" data-ticker="${it.ticker}">
      <div class="wc-header">
        <div>
          <div class="wc-ticker">${it.ticker}</div>
          <div class="wc-name">${it.name}</div>
        </div>
        <button class="wc-remove" id="rm-${it.ticker}" title="Remove">✕</button>
      </div>

      <div class="wc-price">${fmtPrice(it.price)}</div>
      <div class="wc-change">
        <span class="${dir}-arrow">${it.positive ? '▲' : '▼'}</span>
        <span class="wc-dollar ${dir}">${fmtChange(it.change)}</span>
        <span class="wc-pct ${dir}">${fmtPct(it.change_pct)}</span>
      </div>

      <div class="wc-sparkline">
        <canvas id="spark-${it.ticker}" height="52"></canvas>
      </div>

      <div class="wc-periods">
        <div class="wc-period">
          <span class="wc-period-label">1W</span>
          <span class="wc-period-val ${pctClass(weekPct)}">${weekPct != null ? fmtPct(weekPct) : '—'}</span>
        </div>
        <div class="wc-period">
          <span class="wc-period-label">1M</span>
          <span class="wc-period-val ${pctClass(monPct)}">${monPct != null ? fmtPct(monPct) : '—'}</span>
        </div>
      </div>

      <div class="wc-meta">
        <div class="wc-meta-item">
          <span class="wc-meta-label">Volume</span>
          <span class="wc-meta-value">${it.volume}</span>
        </div>
        <div class="wc-meta-item">
          <span class="wc-meta-label">52W Range</span>
          <span class="wc-meta-value" style="font-size:10px">${pRange}</span>
        </div>
      </div>
    </div>`;
  }

  function drawSparkline(it) {
    const canvas = document.getElementById('spark-' + it.ticker);
    if (!canvas || !it.sparkline || it.sparkline.length < 2) return;

    const prices = it.sparkline.map(p => p.close).filter(v => v != null);
    const isPos  = prices[prices.length - 1] >= prices[0];
    const color  = isPos ? '#22c55e' : '#ef4444';

    const ctx = canvas.getContext('2d');
    const grad = ctx.createLinearGradient(0, 0, 0, 52);
    grad.addColorStop(0, isPos ? 'rgba(34,197,94,0.25)' : 'rgba(239,68,68,0.25)');
    grad.addColorStop(1, 'rgba(0,0,0,0)');

    const chart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: prices.map((_, i) => i),
        datasets: [{
          data: prices,
          borderColor: color,
          borderWidth: 1.5,
          fill: true,
          backgroundColor: grad,
          pointRadius: 0,
          tension: 0.3,
        }],
      },
      options: {
        responsive: false,
        animation: false,
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        scales: {
          x: { display: false },
          y: { display: false },
        },
        layout: { padding: 0 },
      },
    });

    sparkCharts.set(it.ticker, chart);
  }

  function markActiveCard(ticker) {
    document.querySelectorAll('.watch-card').forEach(c => c.classList.remove('active-card'));
    const card = document.getElementById('card-' + ticker);
    if (card) card.classList.add('active-card');
  }

  // ── Headlines ─────────────────────────────────────────────────────────────
  async function loadHeadlines(ticker) {
    el.headlinesFeed.innerHTML = `
      <div class="panel-loading">
        <div class="skeleton" style="height:80px;margin-bottom:8px"></div>
        <div class="skeleton" style="height:80px;margin-bottom:8px"></div>
        <div class="skeleton" style="height:80px"></div>
      </div>`;

    try {
      const data = await api(`/api/v1/market/headlines?tickers=${encodeURIComponent(ticker)}`);
      const stock = data[ticker] || {};
      renderHeadlines(ticker, stock.articles || []);
    } catch (e) {
      el.headlinesFeed.innerHTML = '<div class="hl-empty">Headlines unavailable</div>';
    }
  }

  function renderHeadlines(ticker, articles) {
    if (!articles.length) {
      el.headlinesFeed.innerHTML = '<div class="hl-empty">No recent headlines found</div>';
      return;
    }

    el.headlinesFeed.innerHTML = articles.map(a => `
      <a class="headline-item" href="${a.url || '#'}" target="_blank" rel="noopener">
        <div class="hl-meta">
          <span class="hl-ticker-badge">${ticker}</span>
          <span class="hl-source">${a.source || 'News'}</span>
          <span class="hl-time">${a.time_ago || ''}</span>
        </div>
        <div class="hl-headline">${escHtml(a.headline)}</div>
      </a>`).join('');
  }

  function renderHeadlineTabs() {
    el.headlineTabs.innerHTML = watchlist.map(t => `
      <button class="hl-tab ${t === activeHlTicker ? 'active' : ''}"
              data-ticker="${t}">${t}</button>`).join('');

    el.headlineTabs.querySelectorAll('.hl-tab').forEach(btn => {
      btn.addEventListener('click', () => setActiveHeadlineTicker(btn.dataset.ticker));
    });
  }

  function setActiveHeadlineTicker(ticker) {
    activeHlTicker = ticker;
    renderHeadlineTabs();
    markActiveCard(ticker);
    loadHeadlines(ticker);
  }

  // ── Watchlist management ──────────────────────────────────────────────────
  function loadWatchlist() {
    try {
      const stored = JSON.parse(localStorage.getItem(STORAGE_KEY));
      if (Array.isArray(stored) && stored.length) return stored;
    } catch {}
    return [...DEFAULT_WATCHLIST];
  }

  function saveWatchlist() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(watchlist));
  }

  function addTicker(ticker) {
    ticker = ticker.trim().toUpperCase();
    if (!ticker || watchlist.includes(ticker)) return;
    watchlist.push(ticker);
    saveWatchlist();
    refresh();
    renderSettingsTickers();
  }

  function removeTicker(ticker) {
    watchlist = watchlist.filter(t => t !== ticker);
    if (!watchlist.length) watchlist = [...DEFAULT_WATCHLIST];
    if (activeHlTicker === ticker) activeHlTicker = watchlist[0];
    saveWatchlist();
    refresh();
    renderSettingsTickers();
  }

  // ── Settings modal ────────────────────────────────────────────────────────
  function openSettings() {
    renderSettingsTickers();
    el.settingsModal.style.display = 'flex';
    el.newTickerInput.focus();
  }

  function closeSettings() {
    el.settingsModal.style.display = 'none';
    el.newTickerInput.value = '';
  }

  function renderSettingsTickers() {
    el.currentTickers.innerHTML = watchlist.map(t => `
      <span class="ticker-pill">
        ${t}
        <button class="pill-remove" data-ticker="${t}">✕</button>
      </span>`).join('');

    el.currentTickers.querySelectorAll('.pill-remove').forEach(btn => {
      btn.addEventListener('click', () => removeTicker(btn.dataset.ticker));
    });
  }

  // ── Refresh cycle ─────────────────────────────────────────────────────────
  async function refresh() {
    el.btnRefresh.classList.add('spinning');

    try {
      // Phase 1: Load data that other modules depend on
      await Promise.allSettled([
        loadStatus(),
        loadOverview(),
        loadMovers(),
        loadWatchlistCards(),
        loadTickerTape(),
      ]);
      // Phase 2: Highlights depends on movers cache being populated
      await loadHighlights();
      renderHeadlineTabs();
      loadHeadlines(activeHlTicker);
    } finally {
      el.btnRefresh.classList.remove('spinning');
      el.lastUpdate.textContent = 'Updated ' + new Date().toLocaleTimeString();
      startProgressBar();
    }
  }

  function startProgressBar() {
    clearInterval(progressTimer);
    refreshStart = Date.now();
    progressTimer = setInterval(() => {
      const elapsed  = Date.now() - refreshStart;
      const pct      = Math.min(100, (elapsed / REFRESH_MS) * 100);
      el.refreshProgress.style.width = pct + '%';
      if (pct >= 100) clearInterval(progressTimer);
    }, 500);
  }

  function scheduleRefresh() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(async () => {
      await refresh();
      scheduleRefresh();
    }, REFRESH_MS);
  }

  // ── Event wiring ──────────────────────────────────────────────────────────
  function initEvents() {
    el.btnRefresh.addEventListener('click', () => { clearTimeout(refreshTimer); refresh().then(scheduleRefresh); });
    el.btnSettings.addEventListener('click', openSettings);
    el.btnAddTicker.addEventListener('click', openSettings);
    el.btnCloseSet.addEventListener('click', closeSettings);
    el.btnResetWL.addEventListener('click', () => {
      watchlist = [...DEFAULT_WATCHLIST];
      activeHlTicker = watchlist[0];
      saveWatchlist();
      closeSettings();
      refresh();
    });

    el.btnConfirmAdd.addEventListener('click', () => {
      const val = el.newTickerInput.value;
      if (val) { addTicker(val); el.newTickerInput.value = ''; }
    });

    el.newTickerInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') { addTicker(e.target.value); e.target.value = ''; }
    });

    el.settingsModal.addEventListener('click', e => {
      if (e.target === el.settingsModal) closeSettings();
    });

    // Close modal on Escape
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') closeSettings();
    });
  }

  // ── Utility ───────────────────────────────────────────────────────────────
  function escHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g,'&amp;').replace(/</g,'&lt;')
      .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // ── Init ──────────────────────────────────────────────────────────────────
  async function init() {
    initEvents();
    renderHeadlineTabs();
    await refresh();
    scheduleRefresh();
    // Faster status + overview refresh
    setInterval(loadStatus,   60_000);
    setInterval(loadOverview, OVERVIEW_REFRESH);
  }

  init();
})();
