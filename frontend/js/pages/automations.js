import { h, clear, fmtRelative, fmtDateTime } from '../utils.js';
import { api } from '../api.js';
import { toast } from '../components/toast.js';
import { openModal, closeModal, confirmDialog } from '../components/modal.js';
import { field, textInput, textArea, select } from '../components/forms.js';
import { icons } from '../components/icons.js';
import { renderShell } from './_shell.js';

export async function renderAutomations(root, params, ctx) {
  await renderShell(root, ctx, [{ label: 'Automatisations' }], async (main) => {
    main.appendChild(h('div', { class: 'page-header' }, [
      h('div', {}, [
        h('h1', {}, 'Automatisations'),
        h('p', { class: 'sub' }, 'Lance un Gem sur une base à intervalle régulier et envoie le résultat par email.'),
      ]),
      h('button', { class: 'btn btn-primary', onClick: () => openAutoModal() }, [
        h('span', { html: icons.plus }), 'Nouvelle automation',
      ]),
    ]));

    const list = h('div');
    main.appendChild(list);

    let automations = [], gems = [], kbs = [];

    async function load() {
      clear(list);
      list.appendChild(h('div', { class: 'loading-row' }, [h('span', { class: 'spinner' }), 'Chargement…']));
      try {
        [automations, gems, kbs] = await Promise.all([
          api.listAutomations(), api.listGems(), api.listKbs(),
        ]);
      } catch (e) { toast.error(e.detail || 'Erreur'); }
      clear(list);

      if (!automations.length) {
        list.appendChild(h('div', { class: 'empty' }, [
          h('h3', {}, 'Aucune automation'),
          h('p', {}, 'Exemple : envoyer chaque lundi un résumé des nouveaux documents indexés sur la KB "Urbanisme".'),
          h('button', { class: 'btn btn-primary', onClick: () => openAutoModal() }, 'Créer une automation'),
        ]));
        return;
      }

      for (const a of automations) {
        const gem = gems.find(g => g.id === a.gem_id);
        const kb = kbs.find(k => k.id === a.kb_id);
        list.appendChild(h('div', { class: 'list-item' }, [
          h('div', { class: 'info' }, [
            h('div', { class: 'row gap-2' }, [
              h('h4', {}, a.name),
              h('span', { class: 'badge ' + (a.active ? 'badge-green' : 'badge-gray') }, a.active ? 'actif' : 'inactif'),
              h('span', { class: 'badge badge-blue' }, a.channel_type),
            ]),
            h('div', { class: 'desc' }, [
              h('span', {}, kb?.name || a.kb_id.slice(0, 8)),
              ' · Gem: ', h('span', {}, gem?.name || '—'),
              ' · cron: ', h('code', {}, a.cron_expr),
              a.last_run_at ? ' · dernière exéc. ' + fmtRelative(a.last_run_at) : ' · jamais exécutée',
            ]),
          ]),
          h('div', { class: 'actions' }, [
            h('button', {
              class: 'btn btn-secondary btn-sm', onClick: async () => {
                try { await api.triggerAutomation(a.id); toast.success('Exécution déclenchée'); }
                catch (e) { toast.error(e.detail || 'Erreur'); }
              },
            }, [h('span', { html: icons.play }), 'Lancer maintenant']),
            h('button', { class: 'btn btn-ghost btn-sm', html: icons.edit, title: 'Modifier', onClick: () => openAutoModal(a) }),
            h('button', {
              class: 'btn btn-ghost btn-sm', html: icons.trash, title: 'Supprimer',
              onClick: async () => {
                if (!await confirmDialog({ title: 'Supprimer cette automation ?', danger: true, okLabel: 'Supprimer' })) return;
                try { await api.deleteAutomation(a.id); toast.warn('Supprimée'); load(); }
                catch (e) { toast.error(e.detail || 'Erreur'); }
              },
            }),
          ]),
        ]));
      }
    }

    function openAutoModal(existing = null) {
      if (!gems.length || !kbs.length) {
        toast.warn('Crée d\'abord au moins un Gem et une base.');
        return;
      }
      let kbId = existing?.kb_id || kbs[0].id;
      let gemId = existing?.gem_id || gems[0].id;
      let channel = existing?.channel_type || 'email';
      const channelConfig = existing?.channel_config || { to: '' };

      const cronInput = textInput({
        name: 'cron_expr', value: existing?.cron_expr || '0 8 * * 1',
        placeholder: '0 8 * * 1',
      });

      const recipientInput = textInput({
        name: 'channel_to', value: channelConfig.to || '',
        placeholder: 'destinataire@example.com',
      });

      const formEl = h('form', { onSubmit: async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const payload = {
          name: fd.get('name'),
          kb_id: kbId,
          gem_id: gemId,
          user_prompt: fd.get('user_prompt'),
          cron_expr: fd.get('cron_expr'),
          channel_type: channel,
          channel_config: channel === 'email' ? { to: recipientInput.value } : {},
          active: fd.get('active') === 'on',
        };
        try {
          if (existing) await api.updateAutomation(existing.id, payload);
          else await api.createAutomation(payload);
          toast.success('Automation enregistrée');
          closeModal(); load();
        } catch (err) { toast.error(err.detail || 'Erreur'); }
      } }, [
        field('Nom', textInput({ name: 'name', value: existing?.name || '', required: true,
          placeholder: 'Rapport hebdomadaire urbanisme' })),
        h('div', { class: 'field-row mt-4' }, [
          field('Base de connaissance', select({
            name: 'kb_id', value: kbId,
            options: kbs.map(k => ({ value: k.id, label: k.name })),
            onChange: (v) => { kbId = v; },
          })),
          field('Gem', select({
            name: 'gem_id', value: gemId,
            options: gems.map(g => ({ value: g.id, label: g.name })),
            onChange: (v) => { gemId = v; },
          })),
        ]),
        h('div', { class: 'mt-4' }, field('Prompt utilisateur',
          textArea({ name: 'user_prompt', value: existing?.user_prompt || '',
            placeholder: 'Quelles sont les nouveautés de cette semaine sur le projet Tilleuls ?' }))),
        h('div', { class: 'field-row mt-4' }, [
          field('Cron', cronInput, '5 champs (min h day month dow). Ex. "0 8 * * 1" = chaque lundi 8h.'),
          field('Canal', select({
            name: 'channel_type', value: channel,
            options: [{ value: 'email', label: 'Email (SMTP)' }],
            onChange: (v) => { channel = v; },
          })),
        ]),
        h('div', { class: 'mt-4' }, field('Destinataire (email)', recipientInput)),
        h('div', { class: 'mt-4 row gap-2' }, [
          h('input', { type: 'checkbox', name: 'active', checked: existing ? existing.active : true }),
          h('label', { class: 'text-sm' }, 'Activer immédiatement'),
        ]),
      ]);
      openModal({
        title: existing ? 'Modifier l\'automation' : 'Nouvelle automation',
        body: formEl,
        footer: [
          h('button', { class: 'btn btn-secondary', onClick: closeModal }, 'Annuler'),
          h('button', { class: 'btn btn-primary', onClick: () => formEl.requestSubmit() }, 'Enregistrer'),
        ],
      });
    }

    await load();
  });
}
