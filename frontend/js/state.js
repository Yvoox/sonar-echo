// Tiny pub/sub store. Single source of truth for cross-page state
// (auth user, current KB, etc.). Persists token + user to localStorage.

const KEY_TOKEN = 'sonar.token';
const KEY_USER  = 'sonar.user';

function load() {
  try {
    return {
      token: localStorage.getItem(KEY_TOKEN) || null,
      user: JSON.parse(localStorage.getItem(KEY_USER) || 'null'),
    };
  } catch { return { token: null, user: null }; }
}

const initial = load();

const state = {
  token: initial.token,
  user: initial.user,           // { id, email, org_id, is_global_admin }
  currentKb: null,              // active KB object (when on a KB page)
  kbs: [],                      // cached list
};

const listeners = new Set();

export function getState() { return state; }

export function setState(patch) {
  Object.assign(state, patch);
  if ('token' in patch) {
    if (patch.token) localStorage.setItem(KEY_TOKEN, patch.token);
    else localStorage.removeItem(KEY_TOKEN);
  }
  if ('user' in patch) {
    if (patch.user) localStorage.setItem(KEY_USER, JSON.stringify(patch.user));
    else localStorage.removeItem(KEY_USER);
  }
  for (const fn of listeners) fn(state);
}

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function logout() {
  setState({ token: null, user: null, currentKb: null, kbs: [] });
}
