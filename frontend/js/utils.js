// Tiny DOM + formatting helpers, used everywhere.

export function h(tag, attrs = {}, children = []) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === 'class' || k === 'className') el.className = v;
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'html') el.innerHTML = v;
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c == null || c === false) continue;
    el.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); }

export function fmtDate(input) {
  if (!input) return '—';
  const d = (input instanceof Date) ? input : new Date(input);
  if (isNaN(d)) return String(input);
  return d.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' });
}
export function fmtDateTime(input) {
  if (!input) return '—';
  const d = (input instanceof Date) ? input : new Date(input);
  if (isNaN(d)) return String(input);
  return d.toLocaleString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}
export function fmtRelative(input) {
  if (!input) return '';
  const d = new Date(input);
  const sec = Math.round((Date.now() - d.getTime()) / 1000);
  if (sec < 60) return 'à l\'instant';
  if (sec < 3600) return `il y a ${Math.round(sec / 60)} min`;
  if (sec < 86400) return `il y a ${Math.round(sec / 3600)} h`;
  if (sec < 86400 * 7) return `il y a ${Math.round(sec / 86400)} j`;
  return fmtDate(input);
}
export function fmtCurrency(n) {
  if (n == null) return '—';
  return '$' + Number(n).toFixed(4);
}
export function initials(email) {
  if (!email) return '?';
  const at = email.indexOf('@');
  const name = at >= 0 ? email.slice(0, at) : email;
  const parts = name.split(/[._-]/).filter(Boolean);
  return (parts[0]?.[0] || '?').toUpperCase() + (parts[1]?.[0]?.toUpperCase() || '');
}
export function debounce(fn, ms = 300) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}
export function escapeHTML(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}
/** Replace [n] tokens by clickable <sup data-cite="n">[n]</sup>. */
export function renderCitations(text) {
  return escapeHTML(text).replace(/\[(\d+)\]/g, (_, n) => `<sup data-cite="${n}">[${n}]</sup>`);
}
export function bytes(n) {
  if (!n) return '0 B';
  const u = ['B', 'KB', 'MB', 'GB'];
  let i = 0; let v = n;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v < 10 ? 1 : 0)} ${u[i]}`;
}
