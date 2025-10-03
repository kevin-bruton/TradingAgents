import { connectWebSocket } from './websocket.js';
import { ensureRunTab, activateRun, selectNode, toggleNodeInteractive } from './runs.js';
import './config.js'; // side-effect: populates provider/model selects & form handler

// Event delegation for tree interactions
document.addEventListener('click', (e) => {
  const toggleBtn = e.target.closest('button.toggle-btn[data-action="toggle-node"]');
  if (toggleBtn) { toggleNodeInteractive(toggleBtn); return; }
  const item = e.target.closest('.item-name.clickable[data-item-id]');
  if (item) { selectNode({ currentTarget: item, stopPropagation: ()=>{} }); }
});

document.addEventListener('DOMContentLoaded', () => { connectWebSocket(); });

// Expose a minimal surface for legacy inline handlers (if any remain)
window.connectWebSocket = connectWebSocket;
window.selectNode = () => {}; // legacy no-op
