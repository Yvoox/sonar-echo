import { h, initials } from '../utils.js';
import { getState } from '../state.js';

export function renderTopbar(crumbs = []) {
  const { user } = getState();

  const crumbsEl = h('div', { class: 'crumbs' });
  crumbs.forEach((c, i) => {
    if (i > 0) crumbsEl.appendChild(h('span', { class: 'subtle' }, ' / '));
    if (c.href) crumbsEl.appendChild(h('a', { href: c.href }, c.label));
    else crumbsEl.appendChild(h('strong', {}, c.label));
  });

  const userChip = h('div', { class: 'userchip' }, [
    h('span', {}, user?.email || ''),
    h('span', { class: 'avatar' }, initials(user?.email)),
  ]);

  return h('header', { class: 'topbar' }, [crumbsEl, userChip]);
}
