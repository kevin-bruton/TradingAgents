// Utility & shared helpers
export function statusIconFor(status) {
  switch (status) {
    case 'completed': return '✅';
    case 'in_progress': return '⏳';
    case 'error': return '❌';
    case 'canceled': return '⛔';
    default: return '⏸️';
  }
}

export function escapeHtml(str = '') {
  return str.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[c]));
}

export function capitalizeFirstLetter(str='') { return str ? str.charAt(0).toUpperCase() + str.slice(1) : str; }

export function autoScroll(container) {
  if (!container) return;
  const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 30;
  if (nearBottom) container.scrollTop = container.scrollHeight;
}

export function contentHasRenderableMath(str) {
  if (!str) return false;
  if (/\$\$[\s\S]*?\$\$/m.test(str)) return true;
  const inlineMatches = str.match(/\$(?!\s)([^\n$]{1,80}?)\$/g);
  return inlineMatches && inlineMatches.length > 0;
}

export function isLikelyMarkdown(text) {
  if (!text) return false;
  if (/<(p|h1|h2|h3|ul|ol|table|div|section|article)\b/i.test(text)) return false;
  return /(^|\n)#{1,6}\s|\*\*|`{1,3}[^`]|\n[-*+]\s|\n\d+\.\s/.test(text);
}

export function debounce(fn, delay=150) {
  let t; return (...args) => { clearTimeout(t); t = setTimeout(()=>fn(...args), delay); };
}

export function scheduleMathRender(rootEl) {
  if (!rootEl) return;
  if (!window.renderMathInElement) { setTimeout(()=>scheduleMathRender(rootEl), 150); return; }
  const textContent = rootEl.textContent || '';
  if (!contentHasRenderableMath(textContent)) return;
  try {
    window.renderMathInElement(rootEl, {
      delimiters: [
        {left: '$$', right: '$$', display: true},
        {left: '$', right: '$', display: false},
        {left: '\\(', right: '\\)', display: false},
        {left: '\\[', right: '\\]', display: true}
      ],
      throwOnError: false,
      strict: 'ignore'
    });
  } catch(e) { console.warn('[math] render failed', e); }
}
