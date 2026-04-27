// Admin/editor approval queue: aggregate proposed documents across all KBs.
import { h, clear, fmtRelative, fmtDate } from '../utils.js';
import { api } from '../api.js';
import { navigate } from '../router.js';
import { toast } from '../components/toast.js';
import { renderShell } from './_shell.js';

export async function renderProposals(root, params, ctx) {
  await renderShell(root, ctx, [{ label: 'Propositions de documents' }], async (main) => {
    main.appendChild(h('div', { class: 'page-header' }, [
      h('div', {}, [
        h('h1', {}, 'Propositions à modérer'),
        h('p', { class: 'sub' }, 'Documents proposés en attente d\'approbation pour ingestion.'),
      ]),
    ]));

    const tableWrap = h('div');
    main.appendChild(tableWrap);

    async function load() {
      clear(tableWrap);
      tableWrap.appendChild(h('div', { class: 'loading-row' }, [h('span', { class: 'spinner' }), 'Chargement…']));
      let kbs = [];
      try { kbs = await api.listKbs(); }
      catch (e) { toast.error(e.detail || 'Erreur'); return; }

      // Pull "proposed" docs from each KB in parallel
      const all = (await Promise.all(kbs.map(async (kb) => {
        try {
          const docs = await api.listDocs(kb.id, { state: 'proposed' });
          return docs.map(d => ({ ...d, _kb: kb }));
        } catch { return []; }
      }))).flat();

      clear(tableWrap);
      if (!all.length) {
        tableWrap.appendChild(h('div', { class: 'empty' }, [
          h('h3', {}, 'Rien à modérer'),
          h('p', {}, 'Aucun document en attente. Tu seras notifié quand un utilisateur en proposera.'),
        ]));
        return;
      }
      const table = h('table', { class: 'table' }, [
        h('thead', {}, h('tr', {}, [
          h('th', {}, 'Document'),
          h('th', {}, 'KB'),
          h('th', {}, 'Date doc'),
          h('th', {}, 'Proposé'),
          h('th', {}, ''),
        ])),
        h('tbody', {}, all.map(d => h('tr', {}, [
          h('td', {}, [
            h('div', { class: 'font-medium' }, d.title),
            h('div', { class: 'subtle text-xs font-mono' }, d.id.slice(0, 8) + '…'),
          ]),
          h('td', {}, h('a', { href: `#/kbs/${d._kb.id}` }, d._kb.name)),
          h('td', {}, d.source_date ? fmtDate(d.source_date) : '—'),
          h('td', {}, fmtRelative(d.created_at)),
          h('td', {}, h('div', { class: 'row gap-2' }, [
            h('button', {
              class: 'btn btn-sm btn-primary', onClick: async () => {
                try { await api.approveDoc(d._kb.id, d.id, ''); toast.success('Approuvé'); load(); }
                catch (e) { toast.error(e.detail || 'Erreur'); }
              },
            }, 'Approuver'),
            h('button', {
              class: 'btn btn-sm btn-ghost', onClick: async () => {
                try { await api.rejectDoc(d._kb.id, d.id, ''); toast.warn('Rejeté'); load(); }
                catch (e) { toast.error(e.detail || 'Erreur'); }
              },
            }, 'Rejeter'),
          ])),
        ]))),
      ]);
      tableWrap.appendChild(table);
    }
    await load();
  });
}
