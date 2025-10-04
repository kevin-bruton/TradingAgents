import { statusIconFor, capitalizeFirstLetter, scheduleMathRender, contentHasRenderableMath } from './utils.js';
import { runPatchState } from './state.js';
import { applyContentPatches, applyContentOverride } from './content.js';
import { ensureRunLogElements, handleRunLogAppend, handleRunLogSnapshot } from './logs.js';

export function ensureRunTab(runId, ticker, status) {
  let tab = document.getElementById('instrument-tab-' + runId);
  if (!tab) {
    const tabs = document.getElementById('instrument-tabs');
    if (!tabs) return;
    tab = document.createElement('button');
    tab.id = 'instrument-tab-' + runId;
    tab.className = 'instrument-tab';
    tab.setAttribute('role','tab');
    tab.dataset.runId = runId;
    tab.textContent = `${ticker} (${status})`;
    tab.addEventListener('click', () => activateRun(runId));
    tabs.appendChild(tab);
    const treesHost = document.getElementById('instrument-trees');
    const treeWrap = document.createElement('div');
    treeWrap.id = 'instrument-tree-' + runId;
    treeWrap.className = 'instrument-tree-wrapper';
    treeWrap.innerHTML = `<div class="run-progress"><div class="run-progress-inner" style="width:0%"></div></div><ul class="execution-tree" data-run-tree="${runId}"><li><em>Initializing...</em></li></ul>`;
    treesHost.appendChild(treeWrap);
    // Remove static placeholder if present
    const placeholder = treesHost.querySelector('.placeholder');
    if (placeholder) placeholder.remove();
  }
  // Ensure patch state structure exists early so patch messages are not ignored
  if (!runPatchState[runId]) runPatchState[runId] = { seq: 0, syncing: false };
  updateRunTab(runId, status);
}

export function updateRunTab(runId, status, progress=null) {
  const tab = document.getElementById('instrument-tab-' + runId);
  if (tab) {
    tab.textContent = tab.textContent.replace(/\([^)]*\)$/, `(${status})`);
    tab.dataset.status = status;
  }
  if (progress != null) {
    const prog = document.querySelector(`#instrument-tree-${CSS.escape(runId)} .run-progress-inner`);
    if (prog) prog.style.width = progress + '%';
  }
}

export function activateRun(runId) {
  document.querySelectorAll('.instrument-tab').forEach(t=> t.classList.toggle('active', t.dataset.runId === runId));
  document.querySelectorAll('.instrument-tree-wrapper').forEach(w=> w.style.display = (w.id === 'instrument-tree-' + runId) ? 'block' : 'none');
  const treeWrap = document.getElementById('instrument-tree-' + runId);
  if (treeWrap && !treeWrap.dataset.focused) {
    // Open a focused websocket (with patch=1) for this run to receive patch deltas
    window.connectWebSocket(runId, (msg) => {
      if (msg.type === 'init_run') loadRunTree(runId, msg);
      else if (msg.type === 'status_update_run') updateRunTab(runId, msg.status, msg.overall_progress);
      else if (msg.type === 'status_patch_run') applyRunPatch(msg);
      else if (msg.type === 'content_patch_run') applyContentPatches(msg);
      else if (msg.type === 'log_append_run') handleRunLogAppend(msg);
      else if (msg.type === 'log_snapshot_run') handleRunLogSnapshot(msg);
    }, {patch: true});
    treeWrap.dataset.focused = '1';
  }
}

// Simple per-run patch/message queues so early arriving patches (before initial tree load)
// or patches received while a resync snapshot is inflight are not lost.
const pendingStatusPatches = {}; // runId -> [patchMsg]

export function loadRunTree(runId, snapshot) {
  const wrapper = document.querySelector(`#instrument-tree-${CSS.escape(runId)} ul.execution-tree`);
  if (!wrapper) return;
  if (snapshot.execution_tree) {
    wrapper.innerHTML = '';
    snapshot.execution_tree.forEach(phase => {
      const li = document.createElement('li');
      li.id = `run-${runId}-node-${phase.id}`;
      li.className = 'process-item phase-node status-' + phase.status;
      li.innerHTML = `<div class="item-header"><button class="toggle-btn" data-action="toggle-node"><span class="toggle-icon">▶</span></button><span class="item-name clickable" data-item-id="${phase.id}" data-run-id="${runId}"><span class="status-icon">${statusIconFor(phase.status)}</span>${phase.name}</span></div><ul class="item-children collapsed"></ul>`;
      const childrenUl = li.querySelector('.item-children');
      (phase.children||[]).forEach(agent => {
        const agentLi = document.createElement('li');
        agentLi.id = `run-${runId}-node-${agent.id}`;
        agentLi.className = 'process-item agent-node status-' + agent.status;
        agentLi.innerHTML = `<div class="item-header"><button class="toggle-btn" data-action="toggle-node"><span class="toggle-icon">▶</span></button><span class="item-name clickable" data-item-id="${agent.id}" data-run-id="${runId}"><span class="status-icon">${statusIconFor(agent.status)}</span>${agent.name}</span></div><ul class="item-children collapsed"></ul>`;
        const childUl = agentLi.querySelector('.item-children');
        (agent.children||[]).forEach(child => {
          const childLi = document.createElement('li');
          childLi.id = `run-${runId}-node-${child.id}`;
          childLi.className = 'process-item leaf-node status-' + child.status;
          childLi.innerHTML = `<div class="item-header"><span class="toggle-spacer"></span><span class="item-name clickable" data-item-id="${child.id}" data-run-id="${runId}"><span class="status-icon">${statusIconFor(child.status)}</span>${child.name}</span></div>`;
          childUl.appendChild(childLi);
        });
        childrenUl.appendChild(agentLi);
      });
      wrapper.appendChild(li);
    });
  }
  if (snapshot.log_stream) ensureRunLogElements(runId);
  // After building tree, drain any queued patches (in order) to catch up statuses
  if (pendingStatusPatches[runId] && pendingStatusPatches[runId].length) {
  if (window.__RUN_DEBUG__) console.debug('[runs] draining queued patches after load', runId, pendingStatusPatches[runId].map(p=>p.seq));
  pendingStatusPatches[runId].sort((a,b)=>a.seq-b.seq).forEach(p=>applyRunPatch(p));
    pendingStatusPatches[runId] = [];
  }
}

export function applyRunPatch(patchMsg) {
  const { run_id, seq, changed } = patchMsg;
  const state = runPatchState[run_id];
  if (!state) {
    // Tree not yet initialized; queue patch
    if (!pendingStatusPatches[run_id]) pendingStatusPatches[run_id] = [];
    if (window.__RUN_DEBUG__) console.debug('[runs] queue patch (no state yet)', run_id, seq);
    pendingStatusPatches[run_id].push(patchMsg);
    return;
  }
  if (state.syncing) {
    // During resync we temporarily queue patches to avoid dropping them
    if (!pendingStatusPatches[run_id]) pendingStatusPatches[run_id] = [];
    if (window.__RUN_DEBUG__) console.debug('[runs] queue patch (syncing)', run_id, seq);
    pendingStatusPatches[run_id].push(patchMsg);
    return;
  }
  if (seq <= state.seq) return;
  if (seq !== state.seq + 1) {
    state.syncing = true;
    if (window.__RUN_DEBUG__) console.debug('[runs] sequence gap detected requesting resync', run_id, 'have', state.seq, 'got', seq);
    try { window.ws && window.ws.send(JSON.stringify({action:'resync', run_id})); } catch {}
    return;
  }
  changed.forEach(node => {
    const el = document.getElementById(`run-${run_id}-node-${node.id}`);
    if (el) {
      el.classList.remove('status-pending','status-in_progress','status-completed','status-error');
      el.classList.add('status-' + node.status);
      const iconSpan = el.querySelector('.status-icon');
      if (iconSpan) iconSpan.textContent = (node.status_icon && node.status_icon.trim()) ? node.status_icon : statusIconFor(node.status);
    }
    ['messages','report'].forEach(kind => {
      const leafEl = document.getElementById(`run-${run_id}-node-${node.id}_${kind}`);
      if (leafEl) {
        leafEl.classList.remove('status-pending','status-in_progress','status-completed','status-error');
        leafEl.classList.add('status-' + node.status);
        const leafIcon = leafEl.querySelector('.status-icon');
        if (leafIcon) leafIcon.textContent = (node.status_icon && node.status_icon.trim()) ? node.status_icon : statusIconFor(node.status);
      }
    });
  });
  state.seq = seq;
  if (typeof patchMsg.overall_progress === 'number') {
    const p = document.querySelector(`#instrument-tree-${CSS.escape(run_id)} .run-progress-inner`);
    if (p) p.style.width = patchMsg.overall_progress + '%';
  }
}

// Helper invoked for run_snapshot (full resync). Sets state.seq and drains any queued patches beyond snapshot seq.
export function handleRunSnapshot(snapshotMsg) {
  const { run_id, seq } = snapshotMsg;
  const state = runPatchState[run_id];
  if (state) {
    state.seq = seq;
    state.syncing = false;
    if (window.__RUN_DEBUG__) console.debug('[runs] run snapshot applied', run_id, 'seq', seq);
  }
  loadRunTree(run_id, snapshotMsg);
  // Any queued patches with seq > current seq can now be applied in order
  if (pendingStatusPatches[run_id] && pendingStatusPatches[run_id].length) {
    const queue = pendingStatusPatches[run_id].filter(p=>p.seq > seq).sort((a,b)=>a.seq-b.seq);
    if (window.__RUN_DEBUG__) console.debug('[runs] applying queued patches after snapshot', run_id, queue.map(p=>p.seq));
    queue.forEach(p=>applyRunPatch(p));
    pendingStatusPatches[run_id] = [];
  }
}

export function selectNode(ev) {
  ev.stopPropagation();
  const target = ev.currentTarget;
  const itemId = target.dataset.itemId;
  const runId = target.dataset.runId || (target.closest('ul.execution-tree')?.dataset.runTree);
  document.querySelectorAll('.item-name.clickable.active').forEach(el=> el.classList.remove('active'));
  target.classList.add('active');
  const panel = document.getElementById('right-panel');
  panel.dataset.currentItemId = itemId;
  if (runId) panel.dataset.currentRunId = runId;
  const isLeafStream = /(_messages|_report)$/.test(itemId) && runId;
  if (isLeafStream) {
    let cached = (window.runContentState && window.runContentState[runId] && window.runContentState[runId].nodes[itemId]) || '';
    if (cached && !/(<p|<h1|<h2|<h3|<ul|<ol|<table|<code)\b/i.test(cached)) {
      cached = renderContentForItem(itemId, cached);
      if (window.runContentState && window.runContentState[runId]) window.runContentState[runId].nodes[itemId] = cached;
    }
    panel.innerHTML = `<div class="right-panel-inner"><div class="content-header"><h3>${itemId.replace(/_(messages|report)$/,'').split('_').map(capitalizeFirstLetter).join(' ')} ${itemId.endsWith('_messages')?'Messages':'Report'}</h3></div><div class="content-body">${cached ? cached : '<em>Streaming...</em>'}</div></div>`;
    if (!cached) setTimeout(()=>{ applyContentOverride(runId, itemId); }, 50);
  } else {
    const url = runId ? `/runs/${encodeURIComponent(runId)}/content/${encodeURIComponent(itemId)}` : `/content/${encodeURIComponent(itemId)}`;
    fetch(url).then(r=>r.text()).then(html => {
      panel.innerHTML = html;
      try { applyContentOverride(runId, itemId); } catch {}
      const bodyEl = panel.querySelector('.content-body') || panel;
      if (bodyEl && contentHasRenderableMath(bodyEl.textContent)) scheduleMathRender(bodyEl);
    }).catch(()=>{});
  }
}

export function toggleNodeInteractive(btn) {
  const li = btn.closest('li.process-item');
  const children = li ? li.querySelector(':scope > .item-children') : null;
  if (!children) return;
  const isExpanded = children.classList.contains('expanded');
  children.classList.toggle('expanded', !isExpanded);
  children.classList.toggle('collapsed', isExpanded);
  btn.classList.toggle('expanded', !isExpanded);
  btn.setAttribute('aria-expanded', String(!isExpanded));
}
