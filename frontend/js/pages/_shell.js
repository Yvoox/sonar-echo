// Shared "logged-in" shell used by every authenticated page.
import { h, clear } from '../utils.js';
import { renderSidebar } from '../components/sidebar.js';
import { renderTopbar } from '../components/topbar.js';

export async function renderShell(root, _ctx, crumbs, fillMain) {
  clear(root);
  const main = h('main');
  root.appendChild(h('div', { class: 'app-shell' }, [
    renderSidebar(),
    renderTopbar(crumbs),
    main,
  ]));
  await fillMain(main);
}
