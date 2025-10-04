import { connectWebSocket } from './websocket.js';
import { ensureRunTab, activateRun } from './runs.js';

function todayISO() {
  const d = new Date();
  return d.toISOString().slice(0,10);
}

// Configuration fields that should be persisted in localStorage
const CONFIG_STORAGE_KEY = 'trading_agents_config';

// Load all configuration from localStorage
function loadAllConfigFromStorage() {
  try {
    const saved = localStorage.getItem(CONFIG_STORAGE_KEY);
    return saved ? JSON.parse(saved) : {};
  } catch (e) {
    console.warn('[config] Failed to load from localStorage', e);
    return {};
  }
}

// Save all configuration to localStorage
function saveAllConfigToStorage(config) {
  try {
    localStorage.setItem(CONFIG_STORAGE_KEY, JSON.stringify(config));
  } catch (e) {
    console.warn('[config] Failed to save to localStorage', e);
  }
}

// Update a single config value in localStorage
function updateConfigValue(key, value) {
  const config = loadAllConfigFromStorage();
  config[key] = value;
  saveAllConfigToStorage(config);
}

// Get a single config value from localStorage
function getConfigValue(key, defaultValue = null) {
  const config = loadAllConfigFromStorage();
  return config.hasOwnProperty(key) ? config[key] : defaultValue;
}

// Clear all saved configuration (useful for reset/testing)
export function clearAllConfig() {
  try {
    localStorage.removeItem(CONFIG_STORAGE_KEY);
    console.log('[config] All configuration cleared from localStorage');
  } catch (e) {
    console.warn('[config] Failed to clear localStorage', e);
  }
}

export async function fetchProviderConfig() {
  try {
    const resp = await fetch('/config/providers');
    if (!resp.ok) return;
    const data = await resp.json();
    populateProviders(data.providers || []);
  } catch (e) {
    console.warn('[config] provider fetch failed', e);
  }
}

function populateProviders(providers) {
  const providerSel = document.getElementById('multi_llm_provider');
  const quickSel = document.getElementById('multi_quick_think_llm');
  const deepSel = document.getElementById('multi_deep_think_llm');
  if (!providerSel || !quickSel || !deepSel) return;
  providerSel.innerHTML = '';
  providers.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p.key; opt.textContent = p.display_name || p.key;
    providerSel.appendChild(opt);
  });
  
  // Load saved provider from localStorage or use first provider as default
  const savedProvider = getConfigValue('llm_provider');
  let selectedProvider = providers[0];
  
  if (providers.length) {
    if (savedProvider && providers.find(p => p.key === savedProvider)) {
      providerSel.value = savedProvider;
      selectedProvider = providers.find(p => p.key === savedProvider);
    } else {
      providerSel.value = providers[0].key;
      selectedProvider = providers[0];
    }
    updateModelOptions(selectedProvider);
  }
  
  providerSel.addEventListener('change', () => {
    const current = providers.find(p => p.key === providerSel.value);
    if (current) {
      updateModelOptions(current);
      // Save provider selection to localStorage
      updateConfigValue('llm_provider', providerSel.value);
    }
  });
}

function updateModelOptions(provider) {
  const quickSel = document.getElementById('multi_quick_think_llm');
  const deepSel = document.getElementById('multi_deep_think_llm');
  if (!quickSel || !deepSel) return;
  const models = provider.models || {};
  const quick = models.quick || models.standard || [];
  const deep = models.deep || models.advanced || models.research || [];
  fillModelSelect(quickSel, quick);
  fillModelSelect(deepSel, deep);
  
  // Restore saved model selections from localStorage
  const savedQuickModel = getConfigValue('quick_think_llm');
  const savedDeepModel = getConfigValue('deep_think_llm');
  
  if (savedQuickModel && quick.some(m => (typeof m === 'string' ? m : m.id) === savedQuickModel)) {
    quickSel.value = savedQuickModel;
  }
  if (savedDeepModel && deep.some(m => (typeof m === 'string' ? m : m.id) === savedDeepModel)) {
    deepSel.value = savedDeepModel;
  }
  
  // Add event listeners to save selections when changed (only once)
  if (!quickSel.dataset.listenerAttached) {
    quickSel.addEventListener('change', () => {
      updateConfigValue('quick_think_llm', quickSel.value);
    });
    quickSel.dataset.listenerAttached = 'true';
  }
  if (!deepSel.dataset.listenerAttached) {
    deepSel.addEventListener('change', () => {
      updateConfigValue('deep_think_llm', deepSel.value);
    });
    deepSel.dataset.listenerAttached = 'true';
  }
}

function fillModelSelect(sel, list) {
  sel.innerHTML='';
  list.forEach(m => {
    let id, name;
    if (typeof m === 'string') { id = name = m; }
    else { id = m.id; name = m.name || m.id; }
    const opt = document.createElement('option');
    opt.value = id; opt.textContent = name;
    sel.appendChild(opt);
  });
}

function collapseConfigPanel() {
  const formWrap = document.getElementById('config-form');
  if (!formWrap) return;
  formWrap.classList.remove('config-open');
  formWrap.classList.add('config-collapsed');
}

// Initialize all configuration fields with saved values and attach listeners
function initializeConfigFields() {
  // Company Symbols
  const symbolsInput = document.getElementById('multi_company_symbols');
  if (symbolsInput) {
    const savedSymbols = getConfigValue('company_symbols');
    if (savedSymbols) {
      symbolsInput.value = savedSymbols;
    }
    symbolsInput.addEventListener('change', () => {
      updateConfigValue('company_symbols', symbolsInput.value);
      updatePositionFields(); // Regenerate position fields when symbols change
    });
    // Also trigger on input to update position fields dynamically
    symbolsInput.addEventListener('input', () => {
      updatePositionFields();
    });
  }

  // Max Debate Rounds
  const debateRounds = document.getElementById('multi_max_debate_rounds');
  if (debateRounds) {
    const savedRounds = getConfigValue('max_debate_rounds');
    if (savedRounds) {
      debateRounds.value = savedRounds;
    }
    debateRounds.addEventListener('change', () => {
      updateConfigValue('max_debate_rounds', debateRounds.value);
    });
  }

  // Cost Per Trade
  const costInput = document.getElementById('multi_cost_per_trade');
  if (costInput) {
    const savedCost = getConfigValue('cost_per_trade');
    if (savedCost !== null) {
      costInput.value = savedCost;
    }
    costInput.addEventListener('change', () => {
      updateConfigValue('cost_per_trade', costInput.value);
    });
  }

  // Analysis Date - Don't restore this as it should default to today
  // But save it when changed for consistency
  const dateInput = document.getElementById('multi_analysis_date');
  if (dateInput) {
    dateInput.addEventListener('change', () => {
      updateConfigValue('analysis_date', dateInput.value);
    });
  }
  
  // Initialize position fields for current symbols
  updatePositionFields();
}

// Generate per-instrument position configuration fields
function updatePositionFields() {
  const symbolsInput = document.getElementById('multi_company_symbols');
  const container = document.getElementById('position-instruments-list');
  if (!symbolsInput || !container) return;
  
  const symbolsStr = symbolsInput.value.trim();
  if (!symbolsStr) {
    container.innerHTML = '<p style="font-size:0.85rem; color:#999; font-style:italic;">Enter company symbols above to configure positions.</p>';
    return;
  }
  
  const symbols = symbolsStr.split(',').map(s => s.trim().toUpperCase()).filter(s => s);
  if (symbols.length === 0) {
    container.innerHTML = '<p style="font-size:0.85rem; color:#999; font-style:italic;">Enter company symbols above to configure positions.</p>';
    return;
  }
  
  // Load saved position configurations
  const savedPositions = getConfigValue('instrument_positions', {});
  
  container.innerHTML = '';
  symbols.forEach((symbol, idx) => {
    const savedPos = savedPositions[symbol] || { position: 'none', stop_loss: '0', take_profit: '0' };
    
    const fieldset = document.createElement('div');
    fieldset.className = 'position-instrument-fieldset';
    fieldset.innerHTML = `
      <div class="position-instrument-header">${symbol}</div>
      <div class="position-fields-grid">
        <div class="position-field">
          <label for="pos_${idx}_status">Position:</label>
          <select id="pos_${idx}_status" name="position_status_${symbol}" data-symbol="${symbol}" data-field="position">
            <option value="none" ${savedPos.position === 'none' ? 'selected' : ''}>None</option>
            <option value="long" ${savedPos.position === 'long' ? 'selected' : ''}>Long</option>
            <option value="short" ${savedPos.position === 'short' ? 'selected' : ''}>Short</option>
          </select>
        </div>
        <div class="position-field">
          <label for="pos_${idx}_sl">Stop Loss ($):</label>
          <input type="number" id="pos_${idx}_sl" name="stop_loss_${symbol}" value="${savedPos.stop_loss}" min="0" step="0.01" data-symbol="${symbol}" data-field="stop_loss">
        </div>
        <div class="position-field">
          <label for="pos_${idx}_tp">Take Profit ($):</label>
          <input type="number" id="pos_${idx}_tp" name="take_profit_${symbol}" value="${savedPos.take_profit}" min="0" step="0.01" data-symbol="${symbol}" data-field="take_profit">
        </div>
      </div>
    `;
    container.appendChild(fieldset);
    
    // Add event listeners to save changes
    const posSelect = fieldset.querySelector(`#pos_${idx}_status`);
    const slInput = fieldset.querySelector(`#pos_${idx}_sl`);
    const tpInput = fieldset.querySelector(`#pos_${idx}_tp`);
    
    [posSelect, slInput, tpInput].forEach(el => {
      el.addEventListener('change', () => {
        saveInstrumentPosition(symbol, {
          position: posSelect.value,
          stop_loss: slInput.value,
          take_profit: tpInput.value
        });
      });
    });
  });
}

// Save position configuration for a specific instrument
function saveInstrumentPosition(symbol, config) {
  const savedPositions = getConfigValue('instrument_positions', {});
  savedPositions[symbol] = config;
  updateConfigValue('instrument_positions', savedPositions);
}

// Get all instrument position configurations
function getAllInstrumentPositions() {
  const symbolsInput = document.getElementById('multi_company_symbols');
  if (!symbolsInput) return {};
  
  const symbols = symbolsInput.value.split(',').map(s => s.trim().toUpperCase()).filter(s => s);
  const positions = {};
  
  symbols.forEach(symbol => {
    const posSelect = document.querySelector(`select[name="position_status_${symbol}"]`);
    const slInput = document.querySelector(`input[name="stop_loss_${symbol}"]`);
    const tpInput = document.querySelector(`input[name="take_profit_${symbol}"]`);
    
    if (posSelect && slInput && tpInput) {
      positions[symbol] = {
        position: posSelect.value,
        stop_loss: parseFloat(slInput.value) || 0,
        take_profit: parseFloat(tpInput.value) || 0
      };
    }
  });
  
  return positions;
}

async function ensureExecutionTreeLoaded() {
  const host = document.getElementById('execution-tree-container');
  if (!host || !host.dataset.empty) return; // already loaded or missing
  try {
    const resp = await fetch('/status');
    if (!resp.ok) return;
    const html = await resp.text();
    host.innerHTML = html; // includes instruments header, tabs, etc.
    delete host.dataset.empty;
    // If the partial still renders a placeholder and we are about to start runs, remove it
    const ph = host.querySelector('.placeholder');
    if (ph) ph.remove();
  } catch(e) { console.warn('[exec-tree] load failed', e); }
}

export function initMultiRunForm() {
  const form = document.getElementById('multi-run-form');
  if (!form) return;
  // Set default date if blank
  const dateInput = document.getElementById('multi_analysis_date');
  if (dateInput && !dateInput.value) dateInput.value = todayISO();
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const fd = new FormData(form);
    
    // Add per-instrument position configurations as JSON
    const positions = getAllInstrumentPositions();
    fd.append('instrument_positions', JSON.stringify(positions));
    
    if (!window.wsConnected) connectWebSocket();
    try {
      const resp = await fetch('/start-multi', {method:'POST', body: fd});
      const js = await resp.json();
      if (js.error) { alert(js.error); return; }
  await ensureExecutionTreeLoaded();
  (js.runs||[]).forEach(r => ensureRunTab(r.run_id, r.ticker, r.status || 'in_progress'));
  if (js.runs && js.runs.length) activateRun(js.runs[0].run_id);
  collapseConfigPanel();
    } catch (e) {
      console.error('[multi-run] start failed', e);
    }
  });
}

// Bootstrap when imported
document.addEventListener('DOMContentLoaded', () => {
  initializeConfigFields(); // Load saved config values
  fetchProviderConfig();
  initMultiRunForm();
});
