import { h, clear, fmtDate } from '../utils.js';
import { api } from '../api.js';
import { navigate } from '../router.js';
import { toast } from '../components/toast.js';
import { renderShell } from './_shell.js';
import { renderTimelineList } from './search.js';
import { icons } from '../components/icons.js';

export async function renderEntityTimeline(root, { id, eid }, ctx) {
  let kb, entity, timeline;
  try {
    [kb, timeline] = await Promise.all([
      api.getKb(id),
      api.entityTimeline(id, eid),
    ]);
    entity = timeline.entity;
  } catch (e) {
    toast.error(e.detail || 'Erreur de chargement');
    navigate(`#/kbs/${id}/graph`);
    return;
  }

  await renderShell(root, ctx, [
    { label: 'Bases', href: '#/kbs' },
    { label: kb.name, href: `#/kbs/${id}` },
    { label: entity.canonical_name },
  ], async (main) => {
    main.appendChild(h('div', { class: 'page-header' }, [
      h('div', {}, [
        h('h1', {}, entity.canonical_name),
        h('p', { class: 'sub' }, [
          h('span', { class: 'badge badge-violet' }, entity.type),
          ' · ',
          h('span', { class: 'font-mono text-xs' }, entity.id),
        ]),
      ]),
      h('div', { class: 'row gap-2' }, [
        h('button', { class: 'btn btn-secondary', onClick: () => navigate(`#/kbs/${id}/graph`) }, [
          h('span', { html: icons.network }), 'Voir dans le graphe',
        ]),
      ]),
    ]));

    if (entity.aliases?.length) {
      main.appendChild(h('div', { class: 'card mb-4' }, [
        h('div', { class: 'subtle text-xs mb-2' }, 'Alias connus'),
        h('div', { class: 'row gap-2', style: { flexWrap: 'wrap' } },
          entity.aliases.map(a => h('span', { class: 'badge badge-gray' }, a))),
      ]));
    }

    main.appendChild(h('h2', { style: { fontSize: 'var(--fz-lg)', marginBottom: 'var(--sp-4)' } },
      `Timeline (${timeline.events.length})`));

    main.appendChild(renderTimelineList(
      timeline.events.map(e => ({
        entity_id: e.entity_id,
        related_entity_id: e.related_entity_id,
        type: e.type,
        valid_from: e.valid_from,
        valid_to: e.valid_to,
        source_doc_title: e.source_doc_title,
      })),
      id,
    ));
  });
}
