import { h, clear, fmtDate } from '../utils.js';
import { api } from '../api.js';
import { navigate } from '../router.js';
import { toast } from '../components/toast.js';
import { openModal, closeModal } from '../components/modal.js';
import { field, textInput, textArea } from '../components/forms.js';
import { icons } from '../components/icons.js';
import { renderShell } from './_shell.js';

export async function renderKbList(root, params, ctx) {
  await renderShell(root, ctx, [{ label: 'Bases de connaissance' }], async (main) => {
    const headerActions = h('button', {
      class: 'btn btn-primary',
      onClick: openCreateKbModal,
    }, [h('span', { html: icons.plus }), 'Nouvelle base']);

    main.appendChild(h('div', { class: 'page-header' }, [
      h('div', {}, [
        h('h1', {}, 'Bases de connaissance'),
        h('p', { class: 'sub' }, 'Choisis une base pour la consulter, l\'enrichir ou y discuter.'),
      ]),
      headerActions,
    ]));

    const grid = h('div', { class: 'grid' });
    main.appendChild(grid);

    const loadingMsg = h('div', { class: 'loading-row' }, [h('span', { class: 'spinner' }), 'Chargement…']);
    grid.appendChild(loadingMsg);

    let kbs = [];
    try { kbs = await api.listKbs(); }
    catch (e) { toast.error(e.detail || 'Erreur de chargement'); }
    loadingMsg.remove();

    if (!kbs.length) {
      grid.appendChild(h('div', { class: 'empty', style: { gridColumn: '1 / -1' } }, [
        h('h3', {}, 'Aucune base de connaissance'),
        h('p', {}, 'Crée ta première base pour commencer à ingérer des documents.'),
        h('button', { class: 'btn btn-primary', onClick: openCreateKbModal }, 'Créer une base'),
      ]));
      return;
    }

    for (const kb of kbs) {
      grid.appendChild(h('div', {
        class: 'card hoverable kb-card',
        onClick: () => navigate(`#/kbs/${kb.id}`),
        style: { cursor: 'pointer' },
      }, [
        h('h3', {}, kb.name),
        h('p', {}, kb.description || 'Aucune description'),
        h('div', { class: 'meta' }, [
          h('span', {}, 'créée ' + fmtDate(kb.created_at)),
        ]),
      ]));
    }

    function openCreateKbModal() {
      const formEl = h('form', { onSubmit: async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        try {
          const kb = await api.createKb({
            name: fd.get('name'), description: fd.get('description') || null,
          });
          toast.success('Base créée');
          closeModal();
          navigate(`#/kbs/${kb.id}`);
        } catch (err) { toast.error(err.detail || 'Erreur'); }
      } }, [
        field('Nom', textInput({ name: 'name', required: true, placeholder: 'Ex. Conseils municipaux 2020-2025' })),
        h('div', { class: 'mt-4' }, [
          field('Description', textArea({ name: 'description', placeholder: 'But, scope, période couverte…' })),
        ]),
      ]);
      const submitBtn = h('button', { class: 'btn btn-primary', onClick: () => formEl.requestSubmit() }, 'Créer');
      const cancelBtn = h('button', { class: 'btn btn-secondary', onClick: closeModal }, 'Annuler');
      openModal({ title: 'Nouvelle base de connaissance', body: formEl, footer: [cancelBtn, submitBtn] });
    }
  });
}
