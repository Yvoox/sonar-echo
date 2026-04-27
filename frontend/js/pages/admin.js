// Admin: invite users + GDPR erasure (global admin only).
import { h, clear, fmtCurrency } from '../utils.js';
import { api } from '../api.js';
import { toast } from '../components/toast.js';
import { openModal, closeModal, confirmDialog } from '../components/modal.js';
import { field, textInput } from '../components/forms.js';
import { icons } from '../components/icons.js';
import { renderShell } from './_shell.js';
import { getState } from '../state.js';

export async function renderAdmin(root, params, ctx) {
  await renderShell(root, ctx, [{ label: 'Administration' }], async (main) => {
    if (!getState().user?.is_global_admin) {
      main.appendChild(h('div', { class: 'empty' }, [
        h('h3', {}, 'Accès refusé'),
        h('p', {}, 'Cette page est réservée aux administrateurs globaux.'),
      ]));
      return;
    }

    main.appendChild(h('div', { class: 'page-header' }, [
      h('div', {}, [
        h('h1', {}, 'Administration'),
        h('p', { class: 'sub' }, 'Invite de nouveaux utilisateurs et gère les demandes RGPD.'),
      ]),
      h('button', {
        class: 'btn btn-primary',
        onClick: () => openInviteModal(),
      }, [h('span', { html: icons.plus }), 'Inviter un utilisateur']),
    ]));

    const me = getState().user;
    const myUsage = h('div', { class: 'card' });
    main.appendChild(h('h2', { style: { fontSize: 'var(--fz-lg)', marginBottom: 'var(--sp-3)' } }, 'Mon usage LLM'));
    main.appendChild(myUsage);
    try {
      const u = await api.userUsage(me.id);
      myUsage.appendChild(h('div', { class: 'kb-stats' }, [
        stat('Tokens chat (in)', u.chat?.tokens_in || 0),
        stat('Tokens chat (out)', u.chat?.tokens_out || 0),
        stat('Coût chat', fmtCurrency(u.chat?.cost_usd)),
        stat('Tokens ingestion (in)', u.ingestion?.tokens_in || 0),
        stat('Tokens ingestion (out)', u.ingestion?.tokens_out || 0),
        stat('Coût total', fmtCurrency(u.total_cost_usd)),
      ]));
    } catch (e) {
      myUsage.appendChild(h('p', { class: 'subtle text-sm' }, 'Statistiques indisponibles.'));
    }

    main.appendChild(h('h2', { class: 'mt-6', style: { fontSize: 'var(--fz-lg)', marginBottom: 'var(--sp-3)' } }, 'RGPD — droit à l\'effacement'));
    main.appendChild(h('div', { class: 'card' }, [
      h('p', { class: 'muted text-sm mb-4' },
        'Pour donner suite à une demande d\'effacement, saisis l\'ID utilisateur. ' +
        'Cela déclenchera le nettoyage en cascade (Postgres + Neo4j + Qdrant + MinIO).'),
      h('form', { class: 'field-row', onSubmit: async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const uid = fd.get('uid');
        if (!uid) return;
        const ok = await confirmDialog({
          title: 'Effacer l\'utilisateur ?',
          message: `Action IRRÉVERSIBLE. Toutes les données personnelles de ${uid} seront supprimées ou pseudonymisées.`,
          danger: true, okLabel: 'Effacer',
        });
        if (!ok) return;
        try { await api.eraseUser(uid); toast.success('Effacement programmé'); }
        catch (err) { toast.error(err.detail || 'Erreur'); }
      } }, [
        textInput({ name: 'uid', placeholder: 'UUID utilisateur', required: true }),
        h('button', { class: 'btn btn-danger', type: 'submit' }, 'Effacer'),
      ]),
    ]));

    function openInviteModal() {
      const formEl = h('form', { onSubmit: async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        try {
          await api.register({
            email: fd.get('email'),
            password: fd.get('password'),
            org_id: getState().user.org_id,
            is_global_admin: fd.get('is_global_admin') === 'on',
          });
          toast.success('Utilisateur créé');
          closeModal();
        } catch (err) { toast.error(err.detail || 'Erreur'); }
      } }, [
        field('Email', textInput({ name: 'email', type: 'email', required: true })),
        h('div', { class: 'mt-4' },
          field('Mot de passe initial', textInput({
            name: 'password', type: 'password', required: true,
            placeholder: 'min. 8 caractères',
          }), 'Communique-le à l\'utilisateur — il pourra le changer à la première connexion.')),
        h('div', { class: 'mt-4 row gap-2' }, [
          h('input', { type: 'checkbox', name: 'is_global_admin' }),
          h('label', { class: 'text-sm' }, 'Promouvoir comme administrateur global'),
        ]),
      ]);
      openModal({
        title: 'Inviter un utilisateur',
        body: formEl,
        footer: [
          h('button', { class: 'btn btn-secondary', onClick: closeModal }, 'Annuler'),
          h('button', { class: 'btn btn-primary', onClick: () => formEl.requestSubmit() }, 'Créer'),
        ],
      });
    }
  });
}

function stat(label, value) {
  return h('div', { class: 'stat' }, [
    h('div', { class: 'label' }, label),
    h('div', { class: 'value' }, value),
  ]);
}
