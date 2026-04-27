// Hash-based router. Matches `#/path/segments` against registered patterns.
// A pattern segment starting with ":" captures into params.

const routes = [];

export function defineRoute(pattern, handler) {
  routes.push({ pattern: split(pattern), handler });
}

function split(p) { return p.replace(/^#?\//, '').split('/').filter(Boolean); }

function match(parts) {
  for (const r of routes) {
    if (r.pattern.length !== parts.length) continue;
    const params = {};
    let ok = true;
    for (let i = 0; i < parts.length; i++) {
      const pp = r.pattern[i];
      if (pp.startsWith(':')) params[pp.slice(1)] = decodeURIComponent(parts[i]);
      else if (pp !== parts[i]) { ok = false; break; }
    }
    if (ok) return { handler: r.handler, params };
  }
  return null;
}

export function navigate(path) {
  if (location.hash === path) handleRoute();
  else location.hash = path;
}

let onChange = () => {};
export function onRouteChange(fn) { onChange = fn; }

export function handleRoute() {
  const path = location.hash || '#/';
  const parts = split(path);
  const m = match(parts);
  onChange(path);
  if (m) m.handler(m.params);
  else if (routes.length) routes[0].handler({});
}

window.addEventListener('hashchange', handleRoute);

export function currentPath() { return location.hash || '#/'; }
