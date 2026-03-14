/* CoastCapital Assistant — Frontend JS */

// ── API Key (set by template or env) ─────────────────────────────────────────
function getApiKey() {
  return window._API_KEY || window.API_KEY || '';
}

// ── Email Modal ───────────────────────────────────────────────────────────────
function openEmailModal(actionId, to, subject, body) {
  document.getElementById('emailTo').value = to || '';
  document.getElementById('emailSubject').value = subject || '';
  document.getElementById('emailBody').value = (body || '').replace(/\\n/g, '\n');
  document.getElementById('emailActionId').value = actionId || '';
  document.getElementById('emailStatus').classList.add('hidden');
  document.getElementById('emailModal').classList.remove('hidden');
  document.getElementById('emailTo').focus();
}

function closeEmailModal() {
  document.getElementById('emailModal').classList.add('hidden');
}

async function submitEmail() {
  const to = document.getElementById('emailTo').value.trim();
  const subject = document.getElementById('emailSubject').value.trim();
  const body = document.getElementById('emailBody').value.trim();
  const actionId = document.getElementById('emailActionId').value;

  if (!to || !subject || !body) {
    showEmailStatus('Please fill in all fields.', 'error');
    return;
  }

  showEmailStatus('Sending…', 'info');

  try {
    const resp = await fetch('/api/send-email', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': getApiKey(),
      },
      body: JSON.stringify({ to, subject, body, action_id: actionId }),
    });
    const data = await resp.json();
    if (data.success) {
      showEmailStatus('✓ Email sent successfully!', 'success');
      setTimeout(closeEmailModal, 1500);
    } else {
      showEmailStatus('Error: ' + (data.error || 'Unknown error'), 'error');
    }
  } catch (err) {
    showEmailStatus('Network error — check your connection.', 'error');
  }
}

function showEmailStatus(msg, type) {
  const el = document.getElementById('emailStatus');
  el.textContent = msg;
  el.className = 'text-sm mt-2 ' + {
    success: 'text-green-600',
    error: 'text-red-500',
    info: 'text-gray-500',
  }[type];
  el.classList.remove('hidden');
}

// ── Pipeline Runner ───────────────────────────────────────────────────────────
async function runPipeline(name, method = 'POST', body = {}) {
  const statusEl = document.getElementById('pipelineStatus');
  if (statusEl) {
    statusEl.textContent = `Running ${name}…`;
    statusEl.className = 'text-sm text-gray-500 mt-3';
    statusEl.classList.remove('hidden');
  }

  try {
    const opts = {
      method: method,
      headers: { 'Content-Type': 'application/json', 'X-API-Key': getApiKey() },
    };
    if (method === 'POST') opts.body = JSON.stringify(body);

    const resp = await fetch('/api/pipeline/' + name, opts);
    const data = await resp.json();

    if (data.success) {
      if (statusEl) {
        statusEl.textContent = `✓ ${name} completed successfully. Refreshing…`;
        statusEl.className = 'text-sm text-green-600 mt-3';
      }
      setTimeout(() => location.reload(), 1200);
    } else {
      if (statusEl) {
        statusEl.textContent = `Error: ${data.error || 'Pipeline failed'}`;
        statusEl.className = 'text-sm text-red-500 mt-3';
      }
    }
  } catch (err) {
    if (statusEl) {
      statusEl.textContent = 'Network error — is the assistant running?';
      statusEl.className = 'text-sm text-red-500 mt-3';
    }
  }
}

// ── AssistantAgent Chat ───────────────────────────────────────────────────────
let chatHistory = [];

async function sendChat() {
  const input = document.getElementById('chatInput');
  const history = document.getElementById('chatHistory');
  const message = input.value.trim();
  if (!message) return;

  appendChatMsg('You', message, 'user');
  input.value = '';
  chatHistory.push({ role: 'user', content: message });

  const thinkEl = appendChatMsg('AssistantAgent', '…thinking…', 'agent');

  try {
    const resp = await fetch('/api/agent/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': getApiKey() },
      body: JSON.stringify({ message, history: chatHistory }),
    });
    const data = await resp.json();
    thinkEl.remove();

    const reply = data.response || data.error || 'No response.';
    appendChatMsg('AssistantAgent', reply, 'agent');
    chatHistory.push({ role: 'assistant', content: reply });
  } catch (err) {
    thinkEl.remove();
    appendChatMsg('AssistantAgent', 'Error connecting — check the server.', 'agent');
  }

  history.scrollTop = history.scrollHeight;
}

function appendChatMsg(sender, text, type) {
  const history = document.getElementById('chatHistory');
  if (!history) return null;

  // Clear placeholder
  if (history.querySelector('p.text-gray-400')) history.innerHTML = '';

  const div = document.createElement('div');
  div.className = type === 'user'
    ? 'flex justify-end'
    : 'flex justify-start';

  const bubble = document.createElement('div');
  bubble.className = type === 'user'
    ? 'bg-blue-600 text-white text-sm px-4 py-2 rounded-2xl rounded-tr-sm max-w-xs'
    : 'bg-white border border-gray-200 text-gray-800 text-sm px-4 py-2 rounded-2xl rounded-tl-sm max-w-sm shadow-sm';
  bubble.style.whiteSpace = 'pre-wrap';
  bubble.textContent = text;

  div.appendChild(bubble);
  history.appendChild(div);
  history.scrollTop = history.scrollHeight;
  return div;
}
