// Lightweight toast notifications.

import { h } from '../utils.js';

function show(message, type = 'info', duration = 3500) {
  const root = document.getElementById('toast-root');
  if (!root) return;
  const el = h('div', { class: `toast ${type}` }, message);
  root.appendChild(el);
  setTimeout(() => {
    el.style.transition = 'opacity .2s, transform .2s';
    el.style.opacity = '0';
    el.style.transform = 'translateY(8px)';
    setTimeout(() => el.remove(), 200);
  }, duration);
}

export const toast = {
  info:    (m) => show(m, 'info'),
  success: (m) => show(m, 'success'),
  warn:    (m) => show(m, 'warn'),
  error:   (m) => show(m, 'error', 5000),
};
