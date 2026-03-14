/**
 * Model Management — Coast Capital Finance
 *
 * Handles ticker selection, model training, backtesting, comparison,
 * promotion, and feature importance visualization.
 */
(function () {
  "use strict";

  // ── State ──────────────────────────────────────────────────────────────
  let selectedTicker = null;
  let tickerData = [];
  let featureChart = null;

  // ── DOM refs ───────────────────────────────────────────────────────────
  const $pills        = document.getElementById("tickerPills");
  const $champSection = document.getElementById("championSummary");
  const $champSeq     = document.getElementById("championSeq");
  const $champDirAcc  = document.getElementById("champDirAcc");
  const $champSharpe  = document.getElementById("champSharpe");
  const $champAlpha   = document.getElementById("champAlpha");
  const $champMaxDD   = document.getElementById("champMaxDD");
  const $champHPO     = document.getElementById("champHPO");
  const $champTrained = document.getElementById("champTrained");
  const $mainTitle    = document.getElementById("mainTitle");
  const $mainSub      = document.getElementById("mainSubtitle");
  const $versionsBody = document.getElementById("versionsBody");
  const $compSection  = document.getElementById("comparisonSection");
  const $compGrid     = document.getElementById("comparisonGrid");
  const $compVerdict  = document.getElementById("comparisonVerdict");
  const $compActions  = document.getElementById("comparisonActions");
  const $featSection  = document.getElementById("featureSection");
  const $featHorizon  = document.getElementById("featureHorizon");
  const $btnRetrain   = document.getElementById("btnRetrain");

  // ── API helpers ────────────────────────────────────────────────────────

  async function api(url, opts = {}) {
    const res = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...opts,
    });
    return res.json();
  }

  function toast(msg, type = "info") {
    const container = document.getElementById("toastContainer");
    const el = document.createElement("div");
    el.className = `toast toast-${type}`;
    el.textContent = msg;
    container.appendChild(el);
    setTimeout(() => el.remove(), 4000);
  }

  function fmtPct(v) {
    if (v == null) return "—";
    return (v * 100).toFixed(1) + "%";
  }

  function fmtNum(v, dec = 2) {
    if (v == null) return "—";
    return Number(v).toFixed(dec);
  }

  function fmtDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  }

  function badgeHTML(status) {
    const cls = status === "champion" ? "badge-champion"
              : status === "candidate" ? "badge-candidate"
              : "badge-archived";
    return `<span class="status-badge ${cls}">${status}</span>`;
  }

  // ── Init ───────────────────────────────────────────────────────────────

  async function init() {
    await loadTickers();
    $btnRetrain.addEventListener("click", handleRetrain);
  }

  // ── Load tickers ───────────────────────────────────────────────────────

  async function loadTickers() {
    try {
      const data = await api("/api/v1/models/tickers");
      tickerData = data.tickers || [];
      renderTickerPills();
    } catch (e) {
      $pills.innerHTML = '<span style="color:var(--red)">Failed to load tickers</span>';
    }
  }

  function renderTickerPills() {
    $pills.innerHTML = tickerData.map(t => {
      const dotCls = t.has_champion ? "has-champion" : "no-champion";
      const activeCls = t.ticker === selectedTicker ? "active" : "";
      return `<button class="ticker-pill ${activeCls}" data-ticker="${t.ticker}">
        <span class="pill-dot ${dotCls}"></span>${t.ticker}
      </button>`;
    }).join("");

    $pills.querySelectorAll(".ticker-pill").forEach(btn => {
      btn.addEventListener("click", () => selectTicker(btn.dataset.ticker));
    });
  }

  // ── Select ticker ──────────────────────────────────────────────────────

  async function selectTicker(ticker) {
    selectedTicker = ticker;
    renderTickerPills();
    $mainTitle.textContent = ticker;
    $mainSub.textContent = "Loading...";

    await Promise.all([
      loadVersions(ticker),
      loadComparison(ticker),
    ]);
  }

  // ── Load versions ──────────────────────────────────────────────────────

  async function loadVersions(ticker) {
    try {
      const data = await api(`/api/v1/models/${ticker}/versions`);
      const versions = data.versions || [];
      $mainSub.textContent = `${versions.length} version${versions.length !== 1 ? "s" : ""}`;

      // Update champion summary
      const champion = versions.find(v => v.status === "champion");
      if (champion) {
        $champSection.style.display = "";
        $champSeq.textContent = `Seq #${champion.sequence_num}`;
        const bm = champion.backtest_metrics || {};
        $champDirAcc.textContent = fmtPct(bm.directional_accuracy);
        $champSharpe.textContent = fmtNum(bm.sharpe_ratio);
        $champAlpha.textContent = fmtPct(bm.alpha);
        $champMaxDD.textContent = fmtPct(bm.max_drawdown);
        $champHPO.textContent = champion.hpo_method || "none";
        $champTrained.textContent = fmtDate(champion.trained_at);

        // Feature importance
        if (champion.feature_importance) {
          renderFeatureChart(champion.feature_importance);
        } else {
          $featSection.style.display = "none";
        }
      } else {
        $champSection.style.display = "none";
        $featSection.style.display = "none";
      }

      renderVersionsTable(versions);
    } catch (e) {
      $versionsBody.innerHTML = `<tr><td colspan="9" class="empty-state">Error loading versions</td></tr>`;
    }
  }

  function renderVersionsTable(versions) {
    if (!versions.length) {
      $versionsBody.innerHTML = `<tr><td colspan="9" class="empty-state">No models trained yet. Click "Retrain Model" to start.</td></tr>`;
      return;
    }

    $versionsBody.innerHTML = versions.map(v => {
      const bm = v.backtest_metrics || {};
      const tm = v.train_metrics || {};
      const dirAcc = bm.directional_accuracy != null ? fmtPct(bm.directional_accuracy) : (tm["1d"] ? fmtPct(tm["1d"].train_directional_accuracy) + "*" : "—");
      const sharpe = bm.sharpe_ratio != null ? fmtNum(bm.sharpe_ratio) : "—";
      const alpha  = bm.alpha != null ? fmtPct(bm.alpha) : "—";
      const maxDD  = bm.max_drawdown != null ? fmtPct(bm.max_drawdown) : "—";

      // Action buttons
      let actions = "";
      if (v.status === "candidate") {
        if (!v.backtest_metrics) {
          actions += `<button class="btn-sm btn-backtest" data-model="${v.model_id}" data-ticker="${v.ticker}">Backtest</button>`;
        }
        if (v.backtest_metrics) {
          actions += `<button class="btn-sm btn-promote" data-model="${v.model_id}" data-ticker="${v.ticker}">Promote</button>`;
        }
      }

      return `<tr>
        <td class="mono">#${v.sequence_num}</td>
        <td>${badgeHTML(v.status)}</td>
        <td>${v.hpo_method || "none"}</td>
        <td class="mono">${dirAcc}</td>
        <td class="mono">${sharpe}</td>
        <td class="mono">${alpha}</td>
        <td class="mono">${maxDD}</td>
        <td>${fmtDate(v.trained_at)}</td>
        <td>${actions}</td>
      </tr>`;
    }).join("");

    // Bind action buttons
    $versionsBody.querySelectorAll(".btn-backtest").forEach(btn => {
      btn.addEventListener("click", () => handleBacktest(btn.dataset.ticker, btn.dataset.model));
    });
    $versionsBody.querySelectorAll(".btn-promote").forEach(btn => {
      btn.addEventListener("click", () => handlePromote(btn.dataset.ticker, btn.dataset.model));
    });
  }

  // ── Comparison ─────────────────────────────────────────────────────────

  async function loadComparison(ticker) {
    try {
      const data = await api(`/api/v1/models/${ticker}/compare`);

      if (!data.champion && !data.candidate) {
        $compSection.style.display = "none";
        return;
      }

      if (data.recommendation === "no_models") {
        $compSection.style.display = "none";
        return;
      }

      $compSection.style.display = "";

      // Verdict
      const rec = data.recommendation;
      let verdictCls = "verdict-keep";
      let verdictText = "Keep Current Champion";
      if (rec === "promote") {
        verdictCls = "verdict-promote";
        verdictText = "Recommend: Promote Candidate";
      } else if (rec === "needs_backtest") {
        verdictCls = "verdict-needs";
        verdictText = "Candidate Needs Backtest";
      }
      $compVerdict.className = `comparison-verdict ${verdictCls}`;
      $compVerdict.textContent = verdictText;

      // Metric deltas
      const deltas = data.metric_deltas || {};
      const metricNames = {
        directional_accuracy: "Directional Accuracy",
        sharpe_ratio: "Sharpe Ratio",
        alpha: "Alpha",
      };

      let gridHTML = "";
      for (const [key, label] of Object.entries(metricNames)) {
        const d = deltas[key];
        if (!d) continue;

        const isPct = key === "directional_accuracy" || key === "alpha";
        const champVal = isPct ? fmtPct(d.champion) : fmtNum(d.champion);
        const candVal  = isPct ? fmtPct(d.candidate) : fmtNum(d.candidate);
        const deltaVal = d.delta > 0 ? `+${isPct ? fmtPct(d.delta) : fmtNum(d.delta)}`
                       : (isPct ? fmtPct(d.delta) : fmtNum(d.delta));
        const deltaCls = d.delta > 0 ? "delta-positive" : d.delta < 0 ? "delta-negative" : "delta-neutral";

        gridHTML += `<div class="comparison-card">
          <div class="comparison-metric-name">${label}</div>
          <div class="comparison-values">
            <div class="comparison-value">
              <span class="label">Champion</span>
              <span class="number">${champVal}</span>
            </div>
            <span class="comparison-delta ${deltaCls}">${deltaVal}</span>
            <div class="comparison-value">
              <span class="label">Candidate</span>
              <span class="number">${candVal}</span>
            </div>
          </div>
        </div>`;
      }
      $compGrid.innerHTML = gridHTML || '<div class="empty-state">No comparison metrics available</div>';

      // Promote button
      if (rec === "promote" && data.candidate) {
        $compActions.innerHTML = `<button class="btn-promote-lg" id="btnPromoteComp" data-model="${data.candidate.model_id}" data-ticker="${ticker}">
          Promote Candidate #${data.candidate.sequence_num} to Champion
        </button>`;
        document.getElementById("btnPromoteComp").addEventListener("click", function () {
          handlePromote(this.dataset.ticker, this.dataset.model);
        });
      } else {
        $compActions.innerHTML = "";
      }

    } catch (e) {
      $compSection.style.display = "none";
    }
  }

  // ── Feature Importance Chart ───────────────────────────────────────────

  function renderFeatureChart(featureImportance) {
    // Use 1d horizon by default
    const horizon = Object.keys(featureImportance)[0];
    if (!horizon) {
      $featSection.style.display = "none";
      return;
    }

    const features = featureImportance[horizon] || {};
    const entries = Object.entries(features).slice(0, 10);
    if (!entries.length) {
      $featSection.style.display = "none";
      return;
    }

    $featSection.style.display = "";
    $featHorizon.textContent = horizon + " horizon";

    const labels = entries.map(([k]) => k);
    const values = entries.map(([, v]) => v);

    // Color by feature category
    const colors = labels.map(label => {
      if (label.includes("rsi") || label.includes("macd") || label.includes("stoch") || label.includes("roc"))
        return "#f59e0b";  // momentum = gold
      if (label.includes("vol") || label.includes("bb_") || label.includes("atr"))
        return "#ef4444";  // volatility = red
      if (label.includes("return") || label.includes("cum") || label.includes("momentum"))
        return "#3b82f6";  // returns = blue
      if (label.includes("sentiment") || label.includes("vix") || label.includes("yield"))
        return "#a78bfa";  // macro/sentiment = purple
      return "#22c55e";    // other = green
    });

    if (featureChart) featureChart.destroy();

    const ctx = document.getElementById("featureChart").getContext("2d");
    featureChart = new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [{
          data: values,
          backgroundColor: colors.map(c => c + "40"),
          borderColor: colors,
          borderWidth: 1,
          borderRadius: 3,
        }],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => `Importance: ${ctx.raw.toFixed(1)}`,
            },
          },
        },
        scales: {
          x: {
            grid: { color: "rgba(255,255,255,0.04)" },
            ticks: { color: "rgba(255,255,255,0.4)", font: { size: 10 } },
          },
          y: {
            grid: { display: false },
            ticks: { color: "rgba(255,255,255,0.6)", font: { family: "'JetBrains Mono'", size: 10 } },
          },
        },
      },
    });
  }

  // ── Actions ────────────────────────────────────────────────────────────

  async function handleRetrain() {
    if (!selectedTicker) {
      toast("Select a ticker first", "error");
      return;
    }

    const hpo = document.querySelector('input[name="hpo"]:checked').value;
    $btnRetrain.disabled = true;
    $btnRetrain.innerHTML = '<span class="spinner"></span>Training...';
    toast(`Training ${selectedTicker} (HPO: ${hpo})...`, "info");

    try {
      const result = await api(`/api/v1/models/${selectedTicker}/train`, {
        method: "POST",
        body: JSON.stringify({ hpo_method: hpo }),
      });

      if (result.success) {
        toast(`Model trained! Seq #${result.sequence_num} (${result.training_duration_sec}s)`, "success");
        await selectTicker(selectedTicker);
        await loadTickers();
      } else {
        toast(`Training failed: ${result.error}`, "error");
      }
    } catch (e) {
      toast(`Training error: ${e.message}`, "error");
    } finally {
      $btnRetrain.disabled = false;
      $btnRetrain.innerHTML = '<span class="btn-icon-inline">+</span> Retrain Model';
    }
  }

  async function handleBacktest(ticker, modelId) {
    const btn = document.querySelector(`.btn-backtest[data-model="${modelId}"]`);
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span>';
    }
    toast(`Backtesting ${ticker} model #${modelId}...`, "info");

    try {
      const result = await api(`/api/v1/models/${ticker}/backtest/${modelId}`, {
        method: "POST",
      });

      if (result.success) {
        toast(`Backtest complete! DirAcc: ${fmtPct(result.directional_accuracy)}, Sharpe: ${fmtNum(result.sharpe_ratio)}`, "success");
        await selectTicker(ticker);
      } else {
        toast(`Backtest failed: ${result.error}`, "error");
      }
    } catch (e) {
      toast(`Backtest error: ${e.message}`, "error");
    }
  }

  async function handlePromote(ticker, modelId) {
    toast(`Promoting ${ticker} model #${modelId}...`, "info");

    try {
      const result = await api(`/api/v1/models/${ticker}/promote/${modelId}`, {
        method: "POST",
      });

      if (result.success) {
        toast(`Model #${modelId} promoted to champion!`, "success");
        await selectTicker(ticker);
        await loadTickers();
      } else {
        toast(`Promotion failed: ${result.error}`, "error");
      }
    } catch (e) {
      toast(`Promotion error: ${e.message}`, "error");
    }
  }

  // ── Boot ───────────────────────────────────────────────────────────────
  init();
})();
