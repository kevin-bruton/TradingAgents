import { runContentState } from './state.js';
import { isLikelyMarkdown, scheduleMathRender, contentHasRenderableMath } from './utils.js';

export function renderContentForItem(itemId, raw) {
  if (!raw) return '';
  const isReport = /_report$/.test(itemId);
  const isMessages = /_messages$/.test(itemId);
  if (isReport || isMessages || isLikelyMarkdown(raw)) {
    try { 
      return window.marked.parse(raw, { 
        breaks: true, 
        gfm: true,
        // Disable single-tilde strikethrough to prevent ~$250 from being treated as strikethrough
        // GFM standard uses ~~ for strikethrough, not single ~
        extensions: [{
          name: 'del',
          level: 'inline',
          start(src) { return src.match(/~~/)?.index; },
          tokenizer(src) {
            const match = src.match(/^~~(?=\S)([\s\S]*?\S)~~/);
            if (match) {
              return {
                type: 'del',
                raw: match[0],
                text: match[1]
              };
            }
          },
          renderer(token) {
            return `<del>${this.parser.parseInline(token.text)}</del>`;
          }
        }]
      }); 
    } catch { return raw; }
  }
  return raw;
}

export function applyContentPatches(msg) {
  const { run_id, seq, patches } = msg;
  const state = runContentState[run_id] || (runContentState[run_id] = { seq: 0, nodes: {} });
  if (seq <= state.seq) return;
  if (seq !== state.seq + 1) {
    console.warn('[content-patch] gap; requesting resync');
    try { window.ws && window.ws.send(JSON.stringify({action:'resync', run_id})); } catch {}
    return;
  }
  patches.forEach(p => {
    const existing = state.nodes[p.id] || '';
    if (p.mode === 'append') state.nodes[p.id] = existing + (p.text || '');
    else if (p.mode === 'replace') state.nodes[p.id] = p.content || '';
    const rendered = renderContentForItem(p.id, state.nodes[p.id]);
    const panel = document.getElementById('right-panel');
    if (panel && panel.dataset.currentItemId === p.id) {
      const body = panel.querySelector('.content-body');
      if (body) {
        body.innerHTML = rendered;
        if (contentHasRenderableMath(state.nodes[p.id])) scheduleMathRender(body);
      }
    }
    state.nodes[p.id] = rendered;
  });
  state.seq = seq;
}

export function applyContentOverride(runId, itemId) {
  if (!runId) return;
  const state = runContentState[runId];
  if (!state) return;
  const content = state.nodes[itemId];
  if (!content) return;
  const panel = document.getElementById('right-panel');
  if (!panel) return;
  const body = panel.querySelector('.content-body');
  if (body) {
    body.innerHTML = content;
    if (contentHasRenderableMath(body.textContent)) scheduleMathRender(body);
  }
}
