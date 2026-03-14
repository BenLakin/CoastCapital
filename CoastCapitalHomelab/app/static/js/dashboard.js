/* ═══════════════════════════════════════════════════════════════════════════
   CoastCapital HomeLab — Dashboard JS
   Homepage-style status indicators + widget block updates
   ═══════════════════════════════════════════════════════════════════════════ */

const API       = '/api/pipeline';
const AGENT_API = '/api/agent/chat';
const EVENTS_API = '/api/events';

let chatHistory = [];
let _errorCount = 0;

// ── Core Helpers ──────────────────────────────────────────────────────────

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = (val !== null && val !== undefined) ? val : '—';
}

/** Set a Homepage-style status dot: 'good' | 'warn' | 'danger' | 'loading' | 'offline' */
function setDot(dotId, state) {
  const el = document.getElementById(dotId);
  if (!el) return;
  el.className = 'svc-dot' + (state ? ' dot-' + state : '');
}

/** Set info-strip widget fill bar */
function setIWBar(id, pct) {
  const el = document.getElementById(id);
  if (!el) return;
  const v = Math.min(100, Math.max(0, pct || 0));
  el.style.width = v + '%';
  el.className = 'iw-fill' + (v >= 90 ? ' fill-danger' : v >= 70 ? ' fill-warn' : '');
}

/** Set a service block fill bar */
function setBlockBar(id, pct) {
  const el = document.getElementById(id);
  if (!el) return;
  const v = Math.min(100, Math.max(0, pct || 0));
  el.style.width = v + '%';
  el.className = 'block-fill' + (v >= 90 ? ' fill-danger' : v >= 70 ? ' fill-warn' : '');
}

function pctStr(v) { return v != null ? v.toFixed(1) + '%' : '—'; }

function fmtUptime(sec) {
  if (!sec) return '—';
  const d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600), m = Math.floor((sec % 3600) / 60);
  return d > 0 ? `${d}d ${h}h` : h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function getHeaders() {
  const key = window.__API_KEY__ || '';
  return key ? { 'X-API-Key': key } : {};
}

async function pipelineFetch(path, method = 'GET', body = null) {
  const opts = {
    method,
    headers: { ...getHeaders(), 'Content-Type': 'application/json' },
  };
  if (body) opts.body = JSON.stringify(body);
  const resp = await fetch(API + path, opts);
  if (!resp.ok) throw new Error('HTTP ' + resp.status);
  return resp.json();
}

/** Update the overall header status dot */
function updateOverallStatus() {
  const dot = document.getElementById('hp-status-dot');
  const label = document.getElementById('hp-status-label');
  if (_errorCount === 0) {
    dot.className = 'hp-status-dot status-good';
    if (label) label.textContent = 'All Systems OK';
  } else if (_errorCount <= 2) {
    dot.className = 'hp-status-dot status-warn';
    if (label) label.textContent = `${_errorCount} issue${_errorCount > 1 ? 's' : ''}`;
  } else {
    dot.className = 'hp-status-dot status-danger';
    if (label) label.textContent = `${_errorCount} errors`;
  }
}

// ── System Health (multi-machine) ─────────────────────────────────────────

function buildMachineCard(m, idx) {
  const safe = (id) => `sys-${idx}-${id}`;
  const emoji = m.machine_type === 'mac' ? '🍎' : '🖥️';
  const hasGpu = !!m.gpu_name;

  let gpuHtml = '';
  if (hasGpu) {
    gpuHtml = `
      <div class="gpu-section" id="${safe('gpu')}" style="margin-top:8px">
        <div class="gpu-row">
          <svg viewBox="0 0 24 24" fill="none" class="gpu-icon"><rect x="2" y="7" width="20" height="10" rx="2" stroke="currentColor" stroke-width="1.5"/><path d="M6 7V5M10 7V5M14 7V5M18 7V5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="12" cy="12" r="2" stroke="currentColor" stroke-width="1.5"/></svg>
          <span id="${safe('gpu-name')}">${m.gpu_name || 'GPU'}</span>
        </div>
        <div class="svc-blocks" style="margin-top:8px">
          <div class="svc-block">
            <div class="block-label">Util</div>
            <div class="block-value" id="${safe('gpu-util')}">${m.gpu_util != null ? m.gpu_util + '%' : '—'}</div>
          </div>
          <div class="svc-block">
            <div class="block-label">VRAM</div>
            <div class="block-value" id="${safe('gpu-vram')}">${m.gpu_mem_used_mb != null ? m.gpu_mem_used_mb + '/' + m.gpu_mem_total_mb + ' MB' : '—'}</div>
          </div>
          <div class="svc-block">
            <div class="block-label">Temp</div>
            <div class="block-value" id="${safe('gpu-temp')}">${m.gpu_temp != null ? m.gpu_temp + '°C' : '—'}</div>
          </div>
        </div>
      </div>`;
  }

  const cpu  = m.cpu_pct  ?? 0;
  const mem  = m.mem_pct  ?? 0;
  const disk = m.disk_pct ?? 0;
  const state = m.error ? 'danger' : (cpu >= 90 || mem >= 90 || disk >= 90) ? 'warn' : 'good';

  return `
    <div class="svc-card" id="card-system-${idx}">
      <div class="svc-card-header">
        <span class="svc-dot dot-${state}" id="dot-system-${idx}"></span>
        <span class="svc-emoji">${emoji}</span>
        <div class="svc-meta">
          <div class="svc-name">${m.machine_name || 'Unknown'}</div>
          <div class="svc-desc">${m.machine_desc || m.machine_type || ''}</div>
        </div>
      </div>
      ${m.error ? `<div class="svc-blocks"><div class="svc-block"><div class="block-label">Error</div><div class="block-value block-value-danger">${m.error}</div></div></div>` : `
      <div class="svc-blocks">
        <div class="svc-block">
          <div class="block-label">CPU</div>
          <div class="block-value" id="${safe('cpu')}">${pctStr(m.cpu_pct)}</div>
          <div class="block-bar"><div class="block-fill${cpu >= 90 ? ' fill-danger' : cpu >= 70 ? ' fill-warn' : ''}" id="${safe('cpu-bar')}" style="width:${cpu}%"></div></div>
        </div>
        <div class="svc-block">
          <div class="block-label">RAM</div>
          <div class="block-value" id="${safe('mem')}">${pctStr(m.mem_pct)}</div>
          <div class="block-bar"><div class="block-fill${mem >= 90 ? ' fill-danger' : mem >= 70 ? ' fill-warn' : ''}" id="${safe('mem-bar')}" style="width:${mem}%"></div></div>
        </div>
        <div class="svc-block">
          <div class="block-label">Disk</div>
          <div class="block-value" id="${safe('disk')}">${pctStr(m.disk_pct)}</div>
          <div class="block-bar"><div class="block-fill${disk >= 90 ? ' fill-danger' : disk >= 70 ? ' fill-warn' : ''}" id="${safe('disk-bar')}" style="width:${disk}%"></div></div>
        </div>
        <div class="svc-block">
          <div class="block-label">Load</div>
          <div class="block-value" id="${safe('load')}">${m.load_1 != null ? m.load_1 + ' / ' + m.load_5 + ' / ' + m.load_15 : '—'}</div>
        </div>
      </div>
      ${gpuHtml}`}
    </div>`;
}

async function refreshSystem() {
  const container = document.getElementById('system-machines');
  const loading = document.getElementById('system-machines-loading');
  if (loading) loading.textContent = 'Refreshing…';

  try {
    const data = await pipelineFetch('/system');
    // API returns a list of machines (get_all_machines)
    const machines = Array.isArray(data) ? data : [data];

    // Render all machine cards
    container.innerHTML = machines.map((m, i) => buildMachineCard(m, i)).join('');

    // Update info strip with first machine's data (primary)
    const primary = machines.find(m => !m.error) || machines[0] || {};
    setText('iw-cpu-val',  pctStr(primary.cpu_pct));
    setText('iw-mem-val',  pctStr(primary.mem_pct));
    setText('iw-disk-val', pctStr(primary.disk_pct));
    setIWBar('iw-cpu-bar',  primary.cpu_pct  ?? 0);
    setIWBar('iw-mem-bar',  primary.mem_pct  ?? 0);
    setIWBar('iw-disk-bar', primary.disk_pct ?? 0);

    // GPU info strip — find first machine with GPU
    const gpuMachine = machines.find(m => m.gpu_name);
    if (gpuMachine) {
      setText('iw-gpu-label', gpuMachine.gpu_name.split(' ').slice(-1)[0]);
      setText('iw-gpu-val', gpuMachine.gpu_util != null ? gpuMachine.gpu_util + '%' : '—');
      setText('iw-gpu-sub', gpuMachine.gpu_temp != null ? gpuMachine.gpu_temp + '°C' : '');
    }

    const hasErrors = machines.some(m => m.error);
    const hasWarnings = machines.some(m =>
      (m.cpu_pct && m.cpu_pct >= 90) || (m.mem_pct && m.mem_pct >= 90) || (m.disk_pct && m.disk_pct >= 90));

    if (hasErrors) _errorCount++;
    updateOverallStatus();
  } catch (e) {
    container.innerHTML = '<div class="hp-loading">Failed to load system health.</div>';
    _errorCount++;
    updateOverallStatus();
  }
}

// ── UniFi Network ─────────────────────────────────────────────────────────

async function refreshUnifi() {
  setDot('dot-unifi', 'loading');
  try {
    const d = await pipelineFetch('/unifi/network');
    if (d.error) { setDot('dot-unifi', 'danger'); _errorCount++; return; }

    setText('unifi-isp',    d.isp_name || 'UniFi Network');
    setText('unifi-wan-ip', d.wan_ip  || '—');
    setText('unifi-speed',  d.wan_speed_mbps != null ? d.wan_speed_mbps + ' Mbps' : '—');
    setText('unifi-wifi',   d.clients_wifi   ?? '—');
    setText('unifi-wired',  d.clients_wired  ?? '—');
    setText('unifi-uptime', fmtUptime(d.uptime_sec));

    // Info strip
    setText('iw-wan-ip',    d.wan_ip || '—');
    setText('iw-wan-speed', d.wan_speed_mbps != null ? d.wan_speed_mbps + ' Mbps' : '');

    // Fetch alerts
    try {
      const alerts = await pipelineFetch('/unifi/alerts');
      const list = alerts.alerts || [];
      if (list.length > 0) {
        const section = document.getElementById('unifi-alerts-section');
        section.style.display = '';
        document.getElementById('unifi-alerts-list').innerHTML = list.slice(0, 4)
          .map(a => `<div class="unifi-alert-item">${a.msg || a.key}</div>`).join('');
        setDot('dot-unifi', 'warn');
      } else {
        setDot('dot-unifi', 'good');
      }
    } catch { setDot('dot-unifi', 'good'); }

  } catch (e) {
    setDot('dot-unifi', 'danger'); _errorCount++;
  }
}

// ── UniFi Protect ─────────────────────────────────────────────────────────

async function refreshProtect() {
  setDot('dot-protect', 'loading');
  try {
    const d = await pipelineFetch('/unifi/protect');
    if (d.error) { setDot('dot-protect', 'danger'); return; }

    const cams  = d.cameras || [];
    const total = d.camera_count ?? cams.length;
    const online = cams.filter(c => c.is_connected).length;
    const recording = cams.filter(c => c.is_recording).length;

    setText('protect-count',     total);
    setText('protect-connected', online + ' / ' + total);
    setText('protect-recording', recording > 0 ? recording + ' recording' : 'Idle');

    // Render cam-chips as clickable buttons to open the viewer
    const grid = document.getElementById('protect-cameras');
    grid.innerHTML = cams.map((cam, i) => `
      <div class="cam-chip" onclick="selectCamera(${i})" style="cursor:pointer" title="View ${cam.name || 'Camera'}">
        <span class="cam-chip-dot ${cam.is_recording ? 'cam-rec' : cam.is_connected ? 'cam-on' : 'cam-off'}"></span>
        <span class="cam-name">${cam.name || 'Camera'}</span>
        ${cam.is_recording ? '<span class="cam-badge-rec">REC</span>' : ''}
      </div>
    `).join('');

    // Initialise/refresh the camera viewer with up-to-date camera list
    initCameraViewer(cams);

    setDot('dot-protect', online === total && total > 0 ? 'good' : online < total ? 'warn' : 'good');
  } catch (e) {
    setDot('dot-protect', 'danger'); _errorCount++;
  }
}

// ── Camera Viewer ──────────────────────────────────────────────────────────

let _cameras    = [];   // [{id, name, is_connected, is_recording, ...}]
let _activeCamIdx = 0;
let _camPollTimer = null;

function initCameraViewer(cameras) {
  _cameras = cameras.filter(c => c.id);
  if (!_cameras.length) return;

  const strip = document.getElementById('cam-selector-strip');
  strip.innerHTML = _cameras.map((cam, i) => `
    <button class="cam-selector-btn ${i === _activeCamIdx ? 'cam-sel-active' : ''}"
            id="cam-sel-${i}" onclick="selectCamera(${i})">
      <span class="cam-sel-dot ${cam.is_recording ? 'cam-rec' : cam.is_connected ? 'cam-on' : 'cam-off'}"></span>
      ${cam.name || 'Camera'}
    </button>
  `).join('');

  document.getElementById('cam-viewer-panel').style.display = '';

  // Only select camera 0 on first load; preserve selection on refresh
  if (_activeCamIdx >= _cameras.length) _activeCamIdx = 0;
  selectCamera(_activeCamIdx);
}

function selectCamera(idx) {
  if (!_cameras.length) return;
  _activeCamIdx = ((idx % _cameras.length) + _cameras.length) % _cameras.length;

  // Update active button styling
  _cameras.forEach((_, i) => {
    const btn = document.getElementById('cam-sel-' + i);
    if (btn) btn.classList.toggle('cam-sel-active', i === _activeCamIdx);
  });

  const cam = _cameras[_activeCamIdx];
  setText('cam-viewer-name', cam.name || 'Camera');

  const badges = document.getElementById('cam-viewer-badges');
  if (cam.is_recording) {
    badges.innerHTML = '<span class="cam-badge-rec" style="margin-left:8px">REC</span>';
  } else if (!cam.is_connected) {
    badges.innerHTML = '<span style="margin-left:8px;font-size:11px;color:var(--hp-text-muted)">Offline</span>';
  } else {
    badges.innerHTML = '';
  }

  loadCameraSnapshot();

  // Restart snapshot poll every 8s
  if (_camPollTimer) clearInterval(_camPollTimer);
  _camPollTimer = setInterval(loadCameraSnapshot, 1000);
}

async function loadCameraSnapshot() {
  if (!_cameras.length) return;
  const cam = _cameras[_activeCamIdx];
  if (!cam.id) return;

  const img    = document.getElementById('cam-snapshot-img');
  const noSnap = document.getElementById('cam-no-snapshot');
  const ts     = document.getElementById('cam-overlay-ts');

  noSnap.textContent = 'Loading…';
  noSnap.style.display = '';

  const key = window.__API_KEY__ || '';
  const params = `ts=${Date.now()}${key ? '&api_key=' + encodeURIComponent(key) : ''}`;
  const url = `/api/pipeline/unifi/protect/snapshot/${cam.id}?${params}`;

  const newImg = new Image();
  newImg.onload = () => {
    img.src = newImg.src;
    img.style.display = '';
    noSnap.style.display = 'none';
    if (ts) ts.textContent = new Date().toLocaleTimeString();
  };
  newImg.onerror = () => {
    img.style.display = 'none';
    noSnap.textContent = 'Snapshot unavailable';
  };
  newImg.src = url;
}

function prevCamera() { selectCamera(_activeCamIdx - 1); }
function nextCamera() { selectCamera(_activeCamIdx + 1); }

// ── Plex ──────────────────────────────────────────────────────────────────

async function refreshPlex() {
  setDot('dot-plex', 'loading');
  try {
    const d = await pipelineFetch('/plex');
    if (d.error) { setDot('dot-plex', 'danger'); _errorCount++; return; }

    setText('plex-streams', d.active_streams ?? 0);
    setText('plex-movies',  d.total_movies   ?? '—');
    setText('plex-shows',   d.total_shows    ?? '—');
    setText('plex-music',   d.total_music    ?? '—');

    const nowPlaying = d.now_playing || [];
    const list = document.getElementById('plex-now-playing');
    list.innerHTML = nowPlaying.map(item => {
      const title = item.subtitle ? `${item.title} — ${item.subtitle}` : item.title;
      return `<div class="stream-item">
        <span class="stream-dot"></span>
        <span class="stream-title">${title}</span>
        <span class="stream-user">${item.user}</span>
      </div>`;
    }).join('');

    setDot('dot-plex', d.active_streams > 0 ? 'good' : 'good');
  } catch (e) {
    setDot('dot-plex', 'danger'); _errorCount++;
  }
}

// ── Home Assistant ────────────────────────────────────────────────────────

async function refreshHA() {
  setDot('dot-ha', 'loading');
  try {
    const d = await pipelineFetch('/homeassistant');
    if (d.error) { setDot('dot-ha', 'danger'); _errorCount++; return; }

    setText('ha-entities',   d.entity_count   ?? '—');
    setText('ha-automations', d.automations_on ?? '—');
    setText('ha-alerts',     d.alert_count    ?? 0);

    const alertList = document.getElementById('ha-alert-list');
    const alerts = (d.alerts || []).slice(0, 4);
    alertList.innerHTML = alerts.map(a => `
      <div class="ha-alert-item">
        <span class="ha-alert-name">${a.name || a.entity_id}</span>
        <span class="ha-alert-state">${a.state}</span>
      </div>
    `).join('');

    setDot('dot-ha', d.alert_count > 0 ? 'warn' : 'good');
  } catch (e) {
    setDot('dot-ha', 'danger'); _errorCount++;
  }
}

// ── Ollama ────────────────────────────────────────────────────────────────

async function refreshOllama() {
  setDot('dot-ollama', 'loading');
  try {
    const d = await pipelineFetch('/ollama');
    if (d.error) { setDot('dot-ollama', 'danger'); _errorCount++; return; }

    setText('ollama-count', d.models_count ?? 0);

    // Get running models
    let runningCount = 0;
    try {
      const r = await pipelineFetch('/ollama/running');
      runningCount = (r.running || []).length;
    } catch {}
    setText('ollama-running', runningCount);

    const grid = document.getElementById('ollama-models');
    grid.innerHTML = (d.models || []).map(m => `
      <div class="model-chip">
        <span class="model-chip-name">${m.name}</span>
        <span class="model-chip-size">${m.size_gb} GB</span>
        ${m.quantization ? `<span class="model-chip-quant">${m.quantization}</span>` : ''}
      </div>
    `).join('');

    setDot('dot-ollama', 'good');
  } catch (e) {
    setDot('dot-ollama', 'danger'); _errorCount++;
  }
}

// ── DNS Server (CoreDNS) ──────────────────────────────────────────────────

async function refreshDNS() {
  setDot('dot-dns', 'loading');
  try {
    const d = await pipelineFetch('/dns');
    if (d.error) { setDot('dot-dns', 'danger'); _errorCount++; return; }

    const online = d.status === 'online';
    setText('dns-status',       online ? 'Online' : 'Offline');
    setText('dns-record-count', d.record_count ?? 0);
    setText('dns-upstream',     (d.upstream || '').replace(/,\s*/g, ' · '));

    // Info strip
    setText('iw-dns-status',  online ? 'Online' : 'Offline');
    setText('iw-dns-records', (d.record_count ?? 0) + ' records');

    setDot('dot-dns', online ? 'good' : 'danger');

    // Load DNS records alongside stats (non-blocking)
    refreshDNSRecords();
  } catch (e) {
    setDot('dot-dns', 'danger'); _errorCount++;
  }
}

// ── DNS Records ────────────────────────────────────────────────────────────

async function refreshDNSRecords() {
  const list = document.getElementById('dns-records-list');
  if (!list) return;
  try {
    const d = await pipelineFetch('/dns/records');
    const records = d.records || [];
    if (!records.length) {
      list.innerHTML = '<div class="dns-empty">No local records yet</div>';
      return;
    }
    list.innerHTML = records.map(r => `
      <div class="dns-record-row">
        <span class="dns-record-domain">${r.domain}</span>
        <span class="dns-record-arrow">→</span>
        <span class="dns-record-ip">${r.ip}</span>
        <button class="dns-delete-btn" onclick="dnsDeleteRecord('${r.ip}','${r.domain}')" title="Delete">
          <svg viewBox="0 0 24 24" fill="none"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
        </button>
      </div>
    `).join('');
  } catch (e) {
    list.innerHTML = '<div class="dns-loading">Failed to load records</div>';
  }
}

async function dnsAddRecord() {
  const domainEl = document.getElementById('dns-input-domain');
  const ipEl     = document.getElementById('dns-input-ip');
  const btn      = document.querySelector('.dns-add-btn');
  const domain = domainEl.value.trim();
  const ip     = ipEl.value.trim();
  if (!domain || !ip) { domainEl.focus(); return; }

  btn.disabled = true;
  try {
    const result = await pipelineFetch('/dns/add', 'POST', { domain, ip });
    if (result.success) {
      domainEl.value = '';
      ipEl.value = '';
      await refreshDNSRecords();
      // Refresh summary to update record count
      setText('dns-record-count', (parseInt(document.getElementById('dns-record-count').textContent || '0') + 1));
    } else {
      alert('Failed to add record: ' + (result.error || 'Unknown error'));
    }
  } catch (e) {
    alert('Error: ' + e.message);
  } finally {
    btn.disabled = false;
  }
}

async function dnsDeleteRecord(ip, domain) {
  try {
    const result = await pipelineFetch('/dns/delete', 'POST', { domain, ip });
    if (result.success) {
      await refreshDNSRecords();
    } else {
      alert('Failed to delete record: ' + (result.error || 'Unknown error'));
    }
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

// ── Portainer ─────────────────────────────────────────────────────────────

async function refreshPortainer() {
  setDot('dot-portainer', 'loading');
  try {
    const d = await pipelineFetch('/portainer');
    if (d.error) { setDot('dot-portainer', 'danger'); _errorCount++; return; }

    setText('portainer-running',   d.running_count   ?? 0);
    setText('portainer-stopped',   d.stopped_count   ?? 0);
    setText('portainer-unhealthy', d.unhealthy_count ?? 0);

    // Info strip
    setText('iw-containers-running', d.running_count ?? 0);
    setText('iw-containers-sub',
      d.stopped_count > 0 ? `${d.stopped_count} stopped` : 'running');

    const grid = document.getElementById('portainer-containers');
    const containers = (d.containers || []).slice(0, 20);
    grid.innerHTML = containers.map(c => {
      const stateClass = ['running','stopped','exited','paused'].includes(c.state)
        ? 'ct-' + c.state : 'ct-other';
      return `<div class="ct-chip">
        <span class="ct-dot ${stateClass}"></span>
        <span class="ct-name">${c.name || c.id}</span>
      </div>`;
    }).join('');

    const unhealthy = d.unhealthy_count || 0;
    const stopped   = d.stopped_count   || 0;
    setDot('dot-portainer', unhealthy > 0 ? 'danger' : stopped > 0 ? 'warn' : 'good');
  } catch (e) {
    setDot('dot-portainer', 'danger'); _errorCount++;
  }
}

// ── Homepage ──────────────────────────────────────────────────────────────

async function refreshHomepage() {
  setDot('dot-homepage', 'loading');
  try {
    const d = await pipelineFetch('/homepage');
    const ok = d.reachable !== false && !d.error;
    setText('homepage-status-val', ok ? 'Online' : (d.error || 'Offline'));
    setText('homepage-url', d.url || window.location.hostname);
    setDot('dot-homepage', ok ? 'good' : 'warn');
  } catch (e) {
    setText('homepage-status-val', 'Offline');
    setDot('dot-homepage', 'danger'); _errorCount++;
  }
}

// ── Events ────────────────────────────────────────────────────────────────

async function refreshEvents() {
  const list = document.getElementById('events-list');
  try {
    const d = await fetch(EVENTS_API + '?limit=30', { headers: getHeaders() }).then(r => r.json());
    const events = d.events || [];
    if (!events.length) {
      list.innerHTML = '<div class="hp-loading">No events recorded yet.</div>';
      return;
    }
    list.innerHTML = events.map(ev => `
      <div class="event-row">
        <span class="event-sev sev-${ev.severity}">${ev.severity}</span>
        <div class="event-body">
          <div class="event-title">${ev.title}</div>
          <div class="event-meta">${ev.source} · ${new Date(ev.event_at).toLocaleString()}</div>
          ${ev.details ? `<div class="event-detail">${ev.details}</div>` : ''}
        </div>
      </div>
    `).join('');
  } catch (e) {
    list.innerHTML = '<div class="hp-loading">Failed to load events.</div>';
  }
}

// ── Chat ──────────────────────────────────────────────────────────────────

function addChatMsg(role, text) {
  const container = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = `chat-msg chat-${role}`;

  if (role === 'assistant' || role === 'thinking') {
    div.innerHTML = `
      <div class="chat-avatar">
        <svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.5"/><path d="M9 10h.01M15 10h.01M9.5 14.5a3.5 3.5 0 005 0" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
      </div>
      <div class="chat-bubble">${text.replace(/</g, '&lt;')}</div>`;
  } else {
    div.innerHTML = `<div class="chat-bubble">${text.replace(/</g, '&lt;')}</div>`;
  }

  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return div;
}

async function sendChat() {
  const input  = document.getElementById('chat-input');
  const sendBtn = document.getElementById('chat-send');
  const msg = input.value.trim();
  if (!msg) return;

  input.value = '';
  input.disabled = true;
  sendBtn.disabled = true;

  addChatMsg('user', msg);
  chatHistory.push({ role: 'user', content: msg });
  const thinking = addChatMsg('thinking', '⋯ Thinking…');

  try {
    const resp = await fetch(AGENT_API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getHeaders() },
      body: JSON.stringify({ message: msg, history: chatHistory.slice(-10) }),
    });
    const data = await resp.json();
    thinking.remove();
    const reply = data.reply || data.error || 'No response.';
    addChatMsg('assistant', reply);
    chatHistory.push({ role: 'assistant', content: reply });
  } catch (e) {
    thinking.remove();
    addChatMsg('assistant', 'Error: ' + e.message);
  } finally {
    input.disabled = false;
    sendBtn.disabled = false;
    input.focus();
  }
}

function quickChat(msg) {
  document.getElementById('chat-input').value = msg;
  sendChat();
}

// ── Refresh All ───────────────────────────────────────────────────────────

async function refreshAll() {
  _errorCount = 0;
  const btn = document.getElementById('btn-refresh-all');
  if (btn) btn.classList.add('spinning');

  const ts = document.getElementById('last-updated');
  if (ts) ts.textContent = 'Refreshing…';

  await Promise.allSettled([
    refreshSystem(),
    refreshUnifi(),
    refreshProtect(),
    refreshPlex(),
    refreshHA(),
    refreshOllama(),
    refreshDNS(),
    refreshPortainer(),
    refreshHomepage(),
    refreshEvents(),
  ]);

  if (ts) ts.textContent = new Date().toLocaleTimeString();
  if (btn) btn.classList.remove('spinning');
  updateOverallStatus();
}

// ── Init ──────────────────────────────────────────────────────────────────

document.getElementById('btn-refresh-all').addEventListener('click', refreshAll);

document.getElementById('chat-input').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
});

// DNS add-form: press Enter in either field to submit
['dns-input-domain', 'dns-input-ip'].forEach(id => {
  const el = document.getElementById(id);
  if (el) el.addEventListener('keydown', e => { if (e.key === 'Enter') dnsAddRecord(); });
});

// Initial load
refreshAll();

// Auto-refresh: fast services every 60s
setInterval(() => {
  refreshSystem();
  refreshUnifi();
  refreshDNS();
  refreshPortainer();
}, 60_000);

// Auto-refresh: slower services every 5 min
setInterval(() => {
  refreshPlex();
  refreshHA();
  refreshOllama();
}, 300_000);
