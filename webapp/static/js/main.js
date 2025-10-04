import { connectWebSocket } from './websocket.js';
import { ensureRunTab, activateRun, selectNode, toggleNodeInteractive } from './runs.js';
import { openLogFilterModal, applyLogFilters, reloadRightPanelLogs } from './logs.js';
import './config.js'; // side-effect: populates provider/model selects & form handler

// Event delegation for tree interactions
document.addEventListener('click', (e) => {
  const toggleBtn = e.target.closest('button.toggle-btn[data-action="toggle-node"]');
  if (toggleBtn) { toggleNodeInteractive(toggleBtn); return; }
  const item = e.target.closest('.item-name.clickable[data-item-id]');
  if (item) { selectNode({ currentTarget: item, stopPropagation: ()=>{} }); }
});

document.addEventListener('DOMContentLoaded', () => { connectWebSocket(); });

// Expose functions for legacy inline handlers
window.connectWebSocket = connectWebSocket;
window.selectNode = () => {}; // legacy no-op
window.openLogFilterModal = openLogFilterModal;
window.applyLogFilters = applyLogFilters;
window.reloadRightPanelLogs = reloadRightPanelLogs;
