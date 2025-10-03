import { runLogState } from './state.js';
import { escapeHtml, autoScroll } from './utils.js';

export function formatLogEntry(entry) {
  const sev = entry.severity || 'INFO';
  const iso = entry.iso || '';
  const src = entry.source || '';
  const agent = entry.agent_id ? `(${entry.agent_id})` : '';
  return `<div class="log-line sev-${sev}">[${iso}] [${sev}] [${src}]${agent} ${escapeHtml(entry.message||'')}</div>`;
}

export function ensureRunLogElements(runId) {
  const panel = document.getElementById('panel-' + runId);
  if (!panel) return;
  let logWrap = panel.querySelector('.run-log-wrapper');
  if (!logWrap) {
    logWrap = document.createElement('div');
    logWrap.className = 'run-log-wrapper';
    logWrap.innerHTML = `<details open><summary>Live Log & Filters</summary>
      <div class="run-log-filters">
        <label>Severity:<select data-log-sev="${runId}">
          <option value="INFO" selected>INFO+</option>
          <option value="DEBUG">DEBUG+</option>
          <option value="WARN">WARN+</option>
          <option value="ERROR">ERROR</option>
        </select></label>
        <label>Source:<select data-log-src="${runId}" multiple size="1">
          <option value="agent">agent</option>
          <option value="decision">decision</option>
          <option value="llm">llm</option>
          <option value="tool">tool</option>
          <option value="system">system</option>
        </select></label>
        <input data-log-q="${runId}" type="text" placeholder="search..." />
        <button type="button" data-log-refresh="${runId}">Reload</button>
        <a href="/runs/${runId}/logs/download" target="_blank">Download</a>
        <span id="log-meta-${runId}" class="log-meta">seq:0</span>
      </div>
      <div class="run-log" id="log-${runId}"></div></details>`;
    panel.appendChild(logWrap);
    attachLogFilterEvents(runId);
  }
}

function attachLogFilterEvents(runId) {
  const sevSel = document.querySelector(`select[data-log-sev='${runId}']`);
  const srcSel = document.querySelector(`select[data-log-src='${runId}']`);
  const qInput = document.querySelector(`input[data-log-q='${runId}']`);
  const reloadBtn = document.querySelector(`button[data-log-refresh='${runId}']`);
  if (sevSel) sevSel.addEventListener('change', () => reloadLogs(runId, true));
  if (srcSel) srcSel.addEventListener('change', () => reloadLogs(runId, true));
  if (qInput) qInput.addEventListener('keydown', e => { if (e.key === 'Enter') reloadLogs(runId, true); });
  if (reloadBtn) reloadBtn.addEventListener('click', () => reloadLogs(runId, true));
}

export function currentLogFilter(runId) {
  const sevSel = document.querySelector(`select[data-log-sev='${runId}']`);
  const srcSel = document.querySelector(`select[data-log-src='${runId}']`);
  const qInput = document.querySelector(`input[data-log-q='${runId}']`);
  let severity = sevSel ? sevSel.value : 'INFO';
  const selectedSources = [];
  if (srcSel) Array.from(srcSel.selectedOptions).forEach(o => selectedSources.push(o.value));
  const q = qInput ? qInput.value.trim() : '';
  return { severity, sources: selectedSources, q };
}

export function reloadLogs(runId, reset=false) {
  const st = runLogState[runId] || (runLogState[runId] = { seq: 0, syncing: false });
  let after_seq = reset ? null : st.seq;
  const { severity, sources, q } = currentLogFilter(runId);
  const params = new URLSearchParams();
  if (severity) params.set('severity', severity);
  if (sources && sources.length) params.set('sources', sources.join(','));
  if (q) params.set('q', q);
  if (after_seq != null) params.set('after_seq', after_seq);
  params.set('limit','250');
  fetch(`/runs/${encodeURIComponent(runId)}/logs?` + params.toString())
    .then(r=>r.json())
    .then(js => {
      const el = document.getElementById('log-' + runId);
      if (!el) return;
      if (reset) el.innerHTML='';
      (js.entries||[]).forEach(e => {
        el.insertAdjacentHTML('beforeend', formatLogEntry(e));
        st.seq = Math.max(st.seq, e.seq);
      });
      updateLogMeta(runId, st.seq);
      autoScroll(el);
    }).catch(()=>{});
}

function updateLogMeta(runId, seq) {
  const meta = document.getElementById('log-meta-' + runId);
  if (meta) meta.textContent = 'seq:' + seq;
}

export function handleRunLogAppend(msg) {
  const st = runLogState[msg.run_id];
  if (!st) return;
  if (msg.seq <= st.seq) return;
  if (msg.seq !== st.seq + 1) {
    st.syncing = true;
    try { window.ws && window.ws.send(JSON.stringify({action:'log_dump', run_id: msg.run_id})); } catch {}
    return;
  }
  const el = document.getElementById('log-' + msg.run_id);
  if (el) {
    (msg.entries||[]).forEach(entry => {
      el.insertAdjacentHTML('beforeend', formatLogEntry(entry));
      st.seq = Math.max(st.seq, entry.seq);
    });
    updateLogMeta(msg.run_id, st.seq);
    autoScroll(el);
  } else {
    st.seq = msg.seq;
  }
}

export function handleRunLogSnapshot(msg) {
  runLogState[msg.run_id] = { seq: msg.seq, syncing: false };
  ensureRunLogElements(msg.run_id);
  const el = document.getElementById('log-' + msg.run_id);
  if (el) {
    el.innerHTML='';
    (msg.entries||[]).forEach(entry => {
      el.insertAdjacentHTML('beforeend', formatLogEntry(entry));
    });
    const meta = document.getElementById('log-meta-' + msg.run_id);
    if (meta) meta.textContent = 'seq:' + msg.seq;
    autoScroll(el);
  }
}

// ==================== Global Log Filter Modal Functions ====================

/**
 * Opens the log filter modal dialog
 */
export function openLogFilterModal() {
  const modal = document.getElementById('log-filter-modal');
  if (modal) {
    modal.showModal();
  }
}

/**
 * Gets the currently active run ID from the active tab
 */
function getActiveRunId() {
  const activeTab = document.querySelector('.instrument-tab.active');
  if (activeTab && activeTab.dataset.runId) {
    return activeTab.dataset.runId;
  }
  // Fallback: check if there's only one run
  const tabs = document.querySelectorAll('.instrument-tab');
  if (tabs.length === 1 && tabs[0].dataset.runId) {
    return tabs[0].dataset.runId;
  }
  return null;
}

/**
 * Applies the selected log filters and displays logs in the right panel
 */
export function applyLogFilters(event) {
  event.preventDefault();
  
  const runId = getActiveRunId();
  if (!runId) {
    alert('No active run selected. Please select a run first.');
    return;
  }

  // Get filter values from modal
  const severitySelect = document.getElementById('global-log-severity');
  const sourcesSelect = document.getElementById('global-log-sources');
  const queryInput = document.getElementById('global-log-query');

  const severity = severitySelect ? severitySelect.value : 'INFO';
  const selectedSources = sourcesSelect ? Array.from(sourcesSelect.selectedOptions).map(o => o.value) : [];
  const query = queryInput ? queryInput.value.trim() : '';

  // Close modal
  const modal = document.getElementById('log-filter-modal');
  if (modal) {
    modal.close();
  }

  // Load and display logs in right panel
  displayLogsInRightPanel(runId, severity, selectedSources, query);
}

/**
 * Fetches logs with filters and displays them in the right panel
 */
function displayLogsInRightPanel(runId, severity, sources, query) {
  const params = new URLSearchParams();
  if (severity) params.set('severity', severity);
  if (sources && sources.length) params.set('sources', sources.join(','));
  if (query) params.set('q', query);
  params.set('limit', '500'); // Higher limit for right panel display

  const panel = document.getElementById('right-panel');
  if (!panel) return;

  // Show loading state
  panel.dataset.currentItemId = 'logs';
  panel.dataset.currentRunId = runId;
  panel.innerHTML = `
    <div class="right-panel-inner">
      <div class="content-header">
        <h3>Filtered Logs - ${runId}</h3>
        <button type="button" class="small-btn" onclick="window.reloadRightPanelLogs()">Refresh</button>
      </div>
      <div class="log-filters-info" style="padding: 8px; background: #f5f5f5; border-radius: 4px; margin-bottom: 10px; font-size: 0.9em;">
        <strong>Active Filters:</strong> 
        Severity: ${severity || 'INFO'}
        ${sources && sources.length ? ` | Sources: ${sources.join(', ')}` : ''}
        ${query ? ` | Search: "${query}"` : ''}
      </div>
      <div class="content-body">
        <div class="right-panel-logs" id="right-panel-logs-display" style="font-family: monospace; font-size: 0.85em; max-height: calc(100vh - 250px); overflow-y: auto;">
          <em>Loading logs...</em>
        </div>
      </div>
    </div>
  `;

  // Store filter params for refresh
  panel.dataset.logSeverity = severity;
  panel.dataset.logSources = sources.join(',');
  panel.dataset.logQuery = query;

  // Fetch and display logs
  fetch(`/runs/${encodeURIComponent(runId)}/logs?` + params.toString())
    .then(r => r.json())
    .then(data => {
      const logDisplay = document.getElementById('right-panel-logs-display');
      if (!logDisplay) return;

      if (!data.entries || data.entries.length === 0) {
        logDisplay.innerHTML = '<p style="color: #666; font-style: italic;">No logs found matching the selected filters.</p>';
        return;
      }

      logDisplay.innerHTML = '';
      data.entries.forEach(entry => {
        logDisplay.insertAdjacentHTML('beforeend', formatLogEntry(entry));
      });

      // Auto-scroll to bottom
      autoScroll(logDisplay);
    })
    .catch(err => {
      const logDisplay = document.getElementById('right-panel-logs-display');
      if (logDisplay) {
        logDisplay.innerHTML = `<p style="color: red;">Error loading logs: ${err.message}</p>`;
      }
    });
}

/**
 * Reloads logs in the right panel using stored filter parameters
 */
export function reloadRightPanelLogs() {
  const panel = document.getElementById('right-panel');
  if (!panel || panel.dataset.currentItemId !== 'logs') return;

  const runId = panel.dataset.currentRunId;
  const severity = panel.dataset.logSeverity || 'INFO';
  const sources = panel.dataset.logSources ? panel.dataset.logSources.split(',').filter(s => s) : [];
  const query = panel.dataset.logQuery || '';

  displayLogsInRightPanel(runId, severity, sources, query);
}
