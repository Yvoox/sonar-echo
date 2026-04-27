import { h } from '../utils.js';
import { icons } from './icons.js';
import { getState, logout } from '../state.js';
import { navigate, currentPath } from '../router.js';

const NAV = [
  { group: 'Travail' },
  { path: '#/chat',         label: 'Chat',           icon: 'chat' },
  { path: '#/kbs',          label: 'Bases',          icon: 'database' },
  { path: '#/search',       label: 'Recherche',      icon: 'search' },

  { group: 'Personnaliser' },
  { path: '#/gems',         label: 'Gems',           icon: 'gem' },
  { path: '#/automations',  label: 'Automatisations', icon: 'zap' },

  { group: 'Modération', adminOnly: true },
  { path: '#/proposals',    label: 'Propositions',   icon: 'inbox', adminOnly: true },

  { group: 'Administration', adminOnly: true },
  { path: '#/admin',        label: 'Utilisateurs',   icon: 'shield', adminOnly: true },
];

export function renderSidebar() {
  const { user } = getState();
  const isAdmin = !!user?.is_global_admin;

  const nav = h('nav', { class: 'sidebar-nav' });
  for (const item of NAV) {
    if (item.adminOnly && !isAdmin) continue;
    if (item.group) {
      nav.appendChild(h('div', { class: 'group' }, item.group));
      continue;
    }
    const link = h('a', {
      href: item.path,
      class: currentPath().startsWith(item.path) ? 'active' : '',
      onClick: (e) => { e.preventDefault(); navigate(item.path); },
    }, [
      h('span', { class: 'ico', html: icons[item.icon] || '' }),
      h('span', {}, item.label),
    ]);
    nav.appendChild(link);
  }

  const foot = h('div', { class: 'sidebar-foot' }, [
    h('button', {
      class: 'btn btn-ghost w-full',
      style: { justifyContent: 'flex-start', gap: 'var(--sp-2)' },
      onClick: () => { logout(); navigate('#/login'); },
    }, [
      h('span', { html: icons.logout }),
      h('span', { class: 'text-sm' }, 'Déconnexion'),
    ]),
  ]);

  return h('aside', { class: 'sidebar' }, [
    h('div', { class: 'sidebar-brand' }, [
      h('img', { src: '/assets/logo.svg', alt: 'Sonar-Echo' }),
      h('strong', {}, 'Sonar-Echo'),
    ]),
    nav,
    foot,
  ]);
}
