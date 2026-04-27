import { h, clear, fmtDate, escapeHTML } from '../utils.js';
import { api } from '../api.js';
import { navigate } from '../router.js';
import { toast } from '../components/toast.js';
import { field, textInput, select } from '../components/forms.js';
import { icons } from '../components/icons.js';
import { renderShell } from './_shell.js';

export async function renderSearch(root, params, ctx) {
  await renderShell(root, ctx, [{ label: 'Recherche' }], async (main) => {
    main.appendChild(h('div', { class: 'page-header' }, [
      h('div', {}, [
        h('h1', {}, 'Recherche unifiée'),
        h('p', { class: 'sub' },
          'Recherche en 4 dimensions sur une base : chunks + entités + timeline + communautés. Sans génération, JSON pur.'),
      ]),
    ]));

    let kbs = [];
    try { kbs = await api.listKbs(); }
    catch (e) { toast.error(e.detail || 'Erreur'); return; }
    if (!kbs.length) {
      main.appendChild(h('div', { class: 'empty' }, [
        h('h3', {}, 'Aucune base'),
        h('p', {}, 'Crée une base de connaissance pour commencer à rechercher.'),
        h('button', { class: 'btn btn-primary', onClick: () => navigate('#/kbs') }, 'Voir les bases'),
      ]));
      return;
    }

    let kbValue = kbs[0].id;
    let dateFromValue = '';
    let dateToValue = '';
    const kbSelect = select({
      name: 'kb', value: kbValue,
      options: kbs.map(k => ({ value: k.id, label: k.name })),
      onChange: (v) => { kbValue = v; },
    });
    const queryInput = textInput({ name: 'q', placeholder: 'Évolution du projet écoquartier 2020-2024' });
    const fromInput = h('input', { class: 'input', type: 'date', onChange: (e) => { dateFromValue = e.target.value; } });
    const toInput = h('input', { class: 'input', type: 'date', onChange: (e) => { dateToValue = e.target.value; } });

    const submitBtn = h('button', { class: 'btn btn-primary', type: 'submit' }, [
      h('span', { html: icons.search }), 'Rechercher',
    ]);
    const formEl = h('form', {
      class: 'card',
      onSubmit: async (e) => { e.preventDefault(); await runSearch(); },
    }, [
      field('Base de connaissance', kbSelect),
      h('div', { class: 'mt-4' }, field('Requête', queryInput)),
      h('div', { class: 'field-row mt-4' }, [
        field('Date début (optionnel)', fromInput),
        field('Date fin (optionnel)', toInput),
      ]),
      h('div', { class: 'mt-4 row gap-2' }, submitBtn),
    ]);
    main.appendChild(formEl);

    const resultsEl = h('div', { class: 'mt-6' });
    main.appendChild(resultsEl);

    async function runSearch() {
      const q = queryInput.value.trim();
      if (!q) { toast.warn('Saisis une requête'); return; }
      submitBtn.disabled = true;
      clear(resultsEl);
      resultsEl.appendChild(h('div', { class: 'loading-row' }, [h('span', { class: 'spinner' }), 'Recherche…']));
      try {
        const payload = { query: q, k: 10 };
        if (dateFromValue && dateToValue) payload.date_range = [dateFromValue, dateToValue];
        const out = await api.search(kbValue, payload);
        renderResults(out);
      } catch (err) {
        clear(resultsEl);
        toast.error(err.detail || 'Erreur');
      } finally { submitBtn.disabled = false; }
    }

    function renderResults(out) {
      clear(resultsEl);
      const grid = h('div', { class: 'search-results' });
      const left = h('div');
      const right = h('div');
      grid.append(left, right);
      resultsEl.appendChild(grid);

      // CHUNKS
      left.appendChild(section(`Chunks (${out.chunks.length})`,
        out.chunks.length ? out.chunks.map(c => h('div', { class: 'chunk' }, [
          h('div', { class: 'chunk-text' }, c.text),
          h('div', { class: 'citation' }, [
            h('strong', {}, c.citation.doc_title || '—'),
            c.citation.source_date ? h('span', { class: 'date' }, fmtDate(c.citation.source_date)) : '',
            c.citation.page ? h('span', {}, `p. ${c.citation.page}`) : '',
            h('span', { class: 'subtle font-mono' }, c.chunk_id),
            h('span', { class: 'subtle' }, `score ${c.score.toFixed(3)}`),
          ]),
          c.entity_ids?.length ? h('div', { class: 'mt-2' },
            c.entity_ids.slice(0, 8).map(eid =>
              h('span', {
                class: 'entity-pill',
                onClick: () => navigate(`#/kbs/${kbValue}/entities/${encodeURIComponent(eid)}`),
              }, eid))
          ) : null,
        ])) : [empty('Aucun chunk trouvé.')]));

      // TIMELINE
      if (out.timeline?.length) {
        left.appendChild(section(`Timeline (${out.timeline.length})`,
          [renderTimelineList(out.timeline, kbValue)]));
      }

      // ENTITIES (right column)
      right.appendChild(section('Entités',
        out.entities?.length
          ? [h('div', { class: 'col gap-2' }, out.entities.map(e =>
              h('div', { class: 'card hoverable', onClick: () => navigate(`#/kbs/${kbValue}/entities/${encodeURIComponent(e.id)}`), style: { padding: 'var(--sp-3) var(--sp-4)', cursor: 'pointer' } }, [
                h('div', { class: 'row between' }, [
                  h('strong', {}, e.canonical_name),
                  h('span', { class: 'badge badge-violet' }, e.type),
                ]),
                h('div', { class: 'subtle text-xs mt-2' }, `${e.mention_count} mentions · ${e.id}`),
              ])
            ))]
          : [empty('Aucune entité trouvée.')]));

      // COMMUNITIES
      if (out.communities?.length) {
        right.appendChild(section('Communautés',
          out.communities.map(c => h('div', { class: 'card', style: { padding: 'var(--sp-3) var(--sp-4)' } }, [
            h('strong', {}, c.label),
            h('p', { class: 'muted text-sm mt-2' }, (c.summary || '').slice(0, 200) + ((c.summary || '').length > 200 ? '…' : '')),
          ]))));
      }
    }

    function section(title, content) {
      return h('div', { class: 'search-section' }, [
        h('h3', {}, title),
        ...[].concat(content),
      ]);
    }
    function empty(msg) { return h('div', { class: 'subtle text-sm' }, msg); }
  });
}

export function renderTimelineList(events, kbId) {
  if (!events?.length) return h('div', { class: 'subtle text-sm' }, 'Aucun événement.');
  const tl = h('div', { class: 'timeline' });
  for (const e of events) {
    tl.appendChild(h('div', { class: 'timeline-item' }, [
      h('div', { class: 'date' }, [
        e.valid_from ? fmtDate(e.valid_from) : '?',
        ' → ',
        e.valid_to ? fmtDate(e.valid_to) : 'maintenant',
      ]),
      h('div', { class: 'title' }, [
        h('span', { class: 'entity-pill', onClick: () => kbId && navigate(`#/kbs/${kbId}/entities/${encodeURIComponent(e.entity_id)}`) }, e.entity_id),
        ' ',
        h('span', { class: 'badge badge-gray' }, e.type),
        ' ',
        e.related_entity_id ? h('span', { class: 'entity-pill', onClick: () => kbId && navigate(`#/kbs/${kbId}/entities/${encodeURIComponent(e.related_entity_id)}`) }, e.related_entity_id) : '',
      ]),
      e.source_doc_title ? h('div', { class: 'src' }, 'Source : ' + e.source_doc_title) : null,
    ]));
  }
  return tl;
}
