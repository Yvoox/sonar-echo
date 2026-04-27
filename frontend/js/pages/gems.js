import { h, clear } from '../utils.js';
import { api } from '../api.js';
import { toast } from '../components/toast.js';
import { openModal, closeModal, confirmDialog } from '../components/modal.js';
import { field, textInput, textArea, select } from '../components/forms.js';
import { icons } from '../components/icons.js';
import { renderShell } from './_shell.js';

export async function renderGems(root, params, ctx) {
  await renderShell(root, ctx, [{ label: 'Gems' }], async (main) => {
    main.appendChild(h('div', { class: 'page-header' }, [
      h('div', {}, [
        h('h1', {}, 'Gems'),
        h('p', { class: 'sub' }, 'Gems = system prompts réutilisables. Inspirés des Gems de Gemini ou des GPTs.'),
      ]),
      h('button', { class: 'btn btn-primary', onClick: () => openGemModal() }, [
        h('span', { html: icons.plus }), 'Nouveau Gem',
      ]),
    ]));

    const list = h('div');
    main.appendChild(list);

    let gems = [];
    let kbs = [];
    async function load() {
      clear(list);
      list.appendChild(h('div', { class: 'loading-row' }, [h('span', { class: 'spinner' }), 'Chargement…']));
      try { [gems, kbs] = await Promise.all([api.listGems(), api.listKbs()]); }
      catch (e) { toast.error(e.detail || 'Erreur'); }
      clear(list);

      if (!gems.length) {
        list.appendChild(h('div', { class: 'empty' }, [
          h('h3', {}, 'Aucun Gem'),
          h('p', {}, 'Crée un Gem pour avoir un assistant spécialisé (analyste juridique, urbanisme, concurrence…).'),
          h('button', { class: 'btn btn-primary', onClick: () => openGemModal() }, 'Créer un Gem'),
        ]));
        return;
      }

      for (const g of gems) {
        const kb = kbs.find(k => k.id === g.kb_id);
        list.appendChild(h('div', { class: 'list-item' }, [
          h('div', { class: 'info' }, [
            h('div', { class: 'row gap-2' }, [
              h('h4', {}, g.name),
              h('span', { class: `badge ${visBadge(g.visibility)}` }, g.visibility),
              kb ? h('span', { class: 'badge badge-gray' }, kb.name) : null,
            ]),
            h('div', { class: 'desc' }, g.description || (g.system_prompt || '').slice(0, 140)),
          ]),
          h('div', { class: 'actions' }, [
            h('button', { class: 'btn btn-ghost btn-sm', html: icons.edit, title: 'Modifier', onClick: () => openGemModal(g) }),
            h('button', {
              class: 'btn btn-ghost btn-sm', html: icons.trash, title: 'Supprimer',
              onClick: async () => {
                if (!await confirmDialog({ title: 'Supprimer ce Gem ?', danger: true, okLabel: 'Supprimer' })) return;
                try { await api.deleteGem(g.id); toast.warn('Gem supprimé'); load(); }
                catch (e) { toast.error(e.detail || 'Erreur'); }
              },
            }),
          ]),
        ]));
      }
    }

    function openGemModal(existing = null) {
      let visibility = existing?.visibility || 'private';
      let kbId = existing?.kb_id || '';
      const kbOptions = [{ value: '', label: '— Tous KB (visibilité private/org seulement) —' }]
        .concat(kbs.map(k => ({ value: k.id, label: k.name })));

      const formEl = h('form', { onSubmit: async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const payload = {
          name: fd.get('name'),
          description: fd.get('description') || null,
          system_prompt: fd.get('system_prompt'),
          kb_id: kbId || null,
          visibility,
          config: {},
        };
        try {
          if (existing) await api.updateGem(existing.id, payload);
          else await api.createGem(payload);
          toast.success('Gem enregistré');
          closeModal(); load();
        } catch (err) { toast.error(err.detail || 'Erreur'); }
      } }, [
        field('Nom', textInput({ name: 'name', value: existing?.name || '', required: true })),
        h('div', { class: 'mt-4' }, field('Description (optionnel)',
          textInput({ name: 'description', value: existing?.description || '' }))),
        h('div', { class: 'mt-4' }, field('System prompt',
          textArea({ name: 'system_prompt', value: existing?.system_prompt || '', rows: 8,
            placeholder: 'Tu es un analyste spécialisé en urbanisme municipal. Réponds toujours…' }))),
        h('div', { class: 'field-row mt-4' }, [
          field('Visibilité', select({
            name: 'visibility', value: visibility,
            options: [
              { value: 'private', label: 'Privé — pour toi uniquement' },
              { value: 'kb',      label: 'KB — visible aux membres de la base' },
              { value: 'org',     label: 'Organisation — visible à tous' },
            ],
            onChange: (v) => { visibility = v; },
          })),
          field('Base associée (optionnel)', select({
            name: 'kb_id', value: kbId,
            options: kbOptions,
            onChange: (v) => { kbId = v; },
          })),
        ]),
      ]);
      openModal({
        title: existing ? 'Modifier le Gem' : 'Nouveau Gem',
        body: formEl,
        footer: [
          h('button', { class: 'btn btn-secondary', onClick: closeModal }, 'Annuler'),
          h('button', { class: 'btn btn-primary', onClick: () => formEl.requestSubmit() }, 'Enregistrer'),
        ],
      });
    }

    function visBadge(v) { return ({ private: 'badge-gray', kb: 'badge-blue', org: 'badge-violet' }[v] || 'badge-gray'); }

    await load();
  });
}
