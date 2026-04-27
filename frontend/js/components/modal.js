// Modal dialog. Usage:
//   openModal({ title, body: HTMLElement, footer: HTMLElement|null, onClose? })
// `body` can also be a function (root) => void to inject contents lazily.

import { h, clear } from '../utils.js';
import { icons } from './icons.js';

let activeBackdrop = null;

export function openModal({ title = '', body, footer = null, onClose, width } = {}) {
  closeModal();
  const root = document.getElementById('modal-root');
  if (!root) return;

  const close = () => {
    if (activeBackdrop) {
      activeBackdrop.remove();
      activeBackdrop = null;
      onClose?.();
    }
  };

  const onKey = (e) => { if (e.key === 'Escape') close(); };

  const closeBtn = h('button', { class: 'btn-icon', html: icons.close, onClick: close });
  const headerEl = h('header', {}, [
    h('h2', {}, title || ''),
    closeBtn,
  ]);
  const bodyEl = h('div', { class: 'body' });
  if (typeof body === 'function') body(bodyEl);
  else if (body instanceof Node) bodyEl.appendChild(body);
  else if (body) bodyEl.textContent = String(body);

  const modal = h('div', { class: 'modal', style: width ? { width: width + 'px' } : null }, [
    headerEl, bodyEl,
  ]);
  if (footer) modal.appendChild(h('footer', {}, [].concat(footer)));

  const backdrop = h('div', {
    class: 'modal-backdrop',
    onClick: (e) => { if (e.target === backdrop) close(); },
  }, modal);

  document.body.appendChild(headerEl);   // ensure stylable
  root.appendChild(backdrop);
  activeBackdrop = backdrop;
  document.addEventListener('keydown', onKey);
  backdrop.addEventListener('remove', () => document.removeEventListener('keydown', onKey));
  return { close, body: bodyEl, modal };
}

export function closeModal() {
  if (activeBackdrop) { activeBackdrop.remove(); activeBackdrop = null; }
}

/** Confirm dialog returning a Promise<boolean>. */
export function confirmDialog({ title = 'Confirmer', message, danger = false, okLabel = 'Confirmer' } = {}) {
  return new Promise((resolve) => {
    const okBtn = h('button', {
      class: 'btn ' + (danger ? 'btn-danger' : 'btn-primary'),
      onClick: () => { resolve(true); closeModal(); },
    }, okLabel);
    const cancelBtn = h('button', {
      class: 'btn btn-secondary',
      onClick: () => { resolve(false); closeModal(); },
    }, 'Annuler');
    openModal({
      title,
      body: h('p', { class: 'muted text-sm' }, message),
      footer: [cancelBtn, okBtn],
      onClose: () => resolve(false),
    });
  });
}
