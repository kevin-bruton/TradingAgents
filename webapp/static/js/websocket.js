import { applyContentPatches } from './content.js';
import { ensureRunTab, updateRunTab, loadRunTree, applyRunPatch, handleRunSnapshot } from './runs.js';
import { handleRunLogAppend, handleRunLogSnapshot } from './logs.js';
import { runPatchState, runContentState, runLogState } from './state.js';

export let ws = null;
export let wsConnected = false;
let reconnectAttempts = 0;
const maxReconnectDelay = 15000;

function websocketUrl(runId=null, opts={}) {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const base = proto + '://' + window.location.host + '/ws';
  const params = [];
  if (runId) params.push('run_id=' + encodeURIComponent(runId));
  if (opts.patch) params.push('patch=1');
  return params.length ? base + '?' + params.join('&') : base;
}

export function connectWebSocket(runId=null, onMessageCb=null, options={}) {
  try { ws = new WebSocket(websocketUrl(runId, options)); } catch(e) { console.warn('[ws] construct failed', e); return; }
  window.ws = ws;
  ws.addEventListener('open', () => { wsConnected = true; reconnectAttempts = 0; });
  ws.addEventListener('close', () => { wsConnected = false; scheduleReconnect(); });
  ws.addEventListener('error', (err) => console.warn('[ws] error', err));
  ws.addEventListener('message', (event) => {
    let data; try { data = JSON.parse(event.data); } catch { return; }
    if (window.__WS_DEBUG__) console.debug('[ws] message', data.type, data);
    if (onMessageCb) onMessageCb(data);
    switch(data.type) {
      case 'init_all':
        (data.runs||[]).forEach(r => ensureRunTab(r.run_id, r.ticker, r.status));
        break;
      case 'status_update_aggregate':
        // Aggregate periodic/batched status updates for all runs
        if (data.runs && typeof data.runs === 'object') {
          Object.entries(data.runs).forEach(([rid, info]) => {
            if (!info) return;
            ensureRunTab(rid, info.ticker, info.status);
            updateRunTab(rid, info.status, info.overall_progress);
          });
        }
        break;
      case 'status_update_run':
        updateRunTab(data.run_id, data.status, data.overall_progress);
        break;
      case 'init_run':
        // Always ensure state objects exist even if no patches/log_stream flags yet
        if (!runPatchState[data.run_id]) runPatchState[data.run_id] = { seq: data.seq || 0, syncing: false };
        if (!runLogState[data.run_id] && data.log_stream) runLogState[data.run_id] = { seq: 0, syncing: false };
        loadRunTree(data.run_id, data);
        break;
      case 'status_patch_run':
        applyRunPatch(data); break;
      case 'content_patch_run':
        applyContentPatches(data); break;
      case 'log_append_run':
        handleRunLogAppend(data); break;
      case 'log_snapshot_run':
        handleRunLogSnapshot(data); break;
      case 'run_snapshot':
        handleRunSnapshot(data);
        break;
      default: break;
    }
  });
}

function scheduleReconnect() {
  reconnectAttempts += 1;
  const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), maxReconnectDelay);
  setTimeout(()=> { if (!wsConnected) connectWebSocket(); }, delay);
}
