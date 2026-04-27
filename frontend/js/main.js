// Application entry point.
// - Boots auth state from localStorage
// - Registers routes
// - Re-renders the active page on every hash change

import { defineRoute, handleRoute, navigate, onRouteChange } from './router.js';
import { getState, subscribe } from './state.js';
import { api } from './api.js';
import { renderLogin } from './pages/login.js';
import { renderKbList } from './pages/kbs.js';
import { renderKbDetail } from './pages/kb_detail.js';
import { renderChat } from './pages/chat.js';
import { renderSearch } from './pages/search.js';
import { renderGems } from './pages/gems.js';
import { renderAutomations } from './pages/automations.js';
import { renderEntityTimeline } from './pages/timeline.js';
import { renderProposals } from './pages/proposals.js';
import { renderAdmin } from './pages/admin.js';

const root = document.getElementById('app');

function requireAuth(handler) {
  return (params) => {
    if (!getState().token) {
      navigate('#/login');
      return;
    }
    handler(root, params, {});
  };
}

defineRoute('#/login',                              (p) => renderLogin(root, p, {}));
defineRoute('#/',                                   requireAuth((root, p) => navigate('#/chat')));
defineRoute('#/chat',                               requireAuth(renderChat));
defineRoute('#/search',                             requireAuth(renderSearch));
defineRoute('#/kbs',                                requireAuth(renderKbList));
defineRoute('#/kbs/:id',                            requireAuth((root, p) => renderKbDetail(root, { id: p.id, tab: 'documents' }, {})));
defineRoute('#/kbs/:id/:tab',                       requireAuth((root, p) => renderKbDetail(root, { id: p.id, tab: p.tab }, {})));
defineRoute('#/kbs/:id/entities/:eid',              requireAuth((root, p) => renderEntityTimeline(root, p, {})));
defineRoute('#/gems',                               requireAuth(renderGems));
defineRoute('#/automations',                        requireAuth(renderAutomations));
defineRoute('#/proposals',                          requireAuth(renderProposals));
defineRoute('#/admin',                              requireAuth(renderAdmin));

// Re-render shell pages when nav changes (so the active sidebar item updates).
onRouteChange(() => { /* nothing — each handler renders its full shell */ });

// Validate token on boot: if invalid, force login.
async function boot() {
  if (getState().token) {
    try { await api.me(); }
    catch { /* api.me will trigger logout/redirect on 401 */ }
  } else if (location.hash !== '#/login') {
    navigate('#/login');
  }
  handleRoute();
}

// Re-render active page when state.user toggles (e.g., post-login).
let lastUserId = getState().user?.id;
subscribe((s) => {
  if (s.user?.id !== lastUserId) {
    lastUserId = s.user?.id;
  }
});

boot();
