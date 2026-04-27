import { h, clear, fmtDate, fmtDateTime, fmtRelative, escapeHTML } from '../utils.js';
import { api } from '../api.js';
import { navigate } from '../router.js';
import { toast } from '../components/toast.js';
import { openModal, closeModal, confirmDialog } from '../components/modal.js';
import { field, textInput, select } from '../components/forms.js';
import { icons } from '../components/icons.js';
import { renderGraph, knownTypes, colorForType } from '../components/graph_viz.js';
import { renderShell } from './_shell.js';

const TABS = [
  { id: 'documents',   label: 'Documents'   },
  { id: 'graph',       label: 'Graphe'      },
  { id: 'communities', label: 'Communautés' },
  { id: 'members',     label: 'Membres'     },
];

export async function renderKbDetail(root, { id, tab = 'documents' }, ctx) {
  let kb;
  try { kb = await api.getKb(id); }
  catch (e) { toast.error(e.detail || 'KB introuvable'); navigate('#/kbs'); return; }

  await renderShell(root, ctx, [
    { label: 'Bases', href: '#/kbs' },
    { label: kb.name },
  ], async (main) => {
    main.appendChild(h('div', { class: 'page-header' }, [
      h('div', {}, [
        h('h1', {}, kb.name),
        h('p', { class: 'sub' }, kb.description || 'Aucune description'),
      ]),
      h('div', { class: 'row' }, [
        h('button', {
          class: 'btn btn-secondary',
          onClick: () => navigate(`#/chat?kb=${id}`),
        }, [h('span', { html: icons.chat }), 'Démarrer un chat']),
        h('button', {
          class: 'btn btn-primary',
          onClick: () => openUploadModal(kb, refreshDocs),
        }, [h('span', { html: icons.upload }), 'Importer un document']),
      ]),
    ]));

    // Tabs nav
    const tabsNav = h('div', { class: 'tabs' });
    for (const t of TABS) {
      tabsNav.appendChild(h('button', {
        class: t.id === tab ? 'active' : '',
        onClick: () => navigate(`#/kbs/${id}/${t.id}`),
      }, t.label));
    }
    main.appendChild(tabsNav);

    const tabRoot = h('div');
    main.appendChild(tabRoot);

    let refreshDocs = () => {};
    if (tab === 'documents')        refreshDocs = await renderDocsTab(tabRoot, kb);
    else if (tab === 'graph')       await renderGraphTab(tabRoot, kb);
    else if (tab === 'communities') await renderCommunitiesTab(tabRoot, kb);
    else if (tab === 'members')     await renderMembersTab(tabRoot, kb);
  });
}

// ─── Documents ──────────────────────────────────────────────────────
async function renderDocsTab(root, kb) {
  clear(root);
  const tableWrap = h('div');
  root.appendChild(tableWrap);

  async function refresh() {
    clear(tableWrap);
    const loading = h('div', { class: 'loading-row' }, [h('span', { class: 'spinner' }), 'Chargement des documents…']);
    tableWrap.appendChild(loading);
    let docs = [];
    try { docs = await api.listDocs(kb.id, { include_deleted: false }); }
    catch (e) { toast.error(e.detail || 'Erreur'); }
    loading.remove();

    if (!docs.length) {
      tableWrap.appendChild(h('div', { class: 'empty' }, [
        h('h3', {}, 'Aucun document'),
        h('p', {}, 'Importe un PDF, une image scannée, ou un document texte pour démarrer l\'ingestion.'),
        h('button', { class: 'btn btn-primary', onClick: () => openUploadModal(kb, refresh) }, 'Importer'),
      ]));
      return;
    }

    const table = h('table', { class: 'table' }, [
      h('thead', {}, h('tr', {}, [
        h('th', {}, 'Titre'),
        h('th', {}, 'État'),
        h('th', {}, 'Version'),
        h('th', {}, 'Date doc'),
        h('th', {}, 'Importé'),
        h('th', {}, ''),
      ])),
      h('tbody', {}, docs.map(d => h('tr', { class: 'doc-row' }, [
        h('td', {}, [
          h('div', { class: 'title' }, d.title),
          h('div', { class: 'ts font-mono' }, d.id.slice(0, 8) + '…'),
        ]),
        h('td', {}, stateBadge(d.state)),
        h('td', {}, 'v' + d.version),
        h('td', {}, d.source_date ? fmtDate(d.source_date) : '—'),
        h('td', {}, fmtRelative(d.created_at)),
        h('td', {}, h('div', { class: 'row gap-2' }, docActions(kb, d, refresh))),
      ]))),
    ]);
    tableWrap.appendChild(table);
  }

  await refresh();
  return refresh;
}

function stateBadge(state) {
  const map = {
    proposed:         ['Proposé',         'badge-amber'],
    approved:         ['Approuvé',        'badge-blue'],
    rejected:         ['Rejeté',          'badge-red'],
    ingesting:        ['Ingestion…',      'badge-violet'],
    ingested:         ['Indexé',          'badge-green'],
    ingestion_failed: ['Échec ingestion', 'badge-red'],
    superseded:       ['Remplacé',        'badge-gray'],
    deleted:          ['Supprimé',        'badge-gray'],
  };
  const [label, cls] = map[state] || [state, 'badge-gray'];
  return h('span', { class: `badge ${cls}` }, label);
}

function docActions(kb, d, refresh) {
  const items = [];
  if (d.state === 'proposed') {
    items.push(h('button', {
      class: 'btn btn-sm btn-secondary',
      onClick: async () => {
        try { await api.approveDoc(kb.id, d.id, ''); toast.success('Approuvé'); refresh(); }
        catch (e) { toast.error(e.detail || 'Erreur'); }
      },
    }, 'Approuver'));
    items.push(h('button', {
      class: 'btn btn-sm btn-ghost',
      onClick: async () => {
        try { await api.rejectDoc(kb.id, d.id, ''); toast.warn('Rejeté'); refresh(); }
        catch (e) { toast.error(e.detail || 'Erreur'); }
      },
    }, 'Rejeter'));
  }
  if (d.state === 'ingestion_failed') {
    items.push(h('button', {
      class: 'btn btn-sm btn-ghost',
      onClick: async () => { await showJobModal(kb.id, d.id); },
    }, 'Voir l\'erreur'));
  }
  if (d.state === 'ingesting' || d.state === 'ingested') {
    items.push(h('button', {
      class: 'btn btn-sm btn-ghost',
      onClick: async () => { await showJobModal(kb.id, d.id); },
    }, 'Job'));
  }
  if (d.state !== 'deleted') {
    items.push(h('button', {
      class: 'btn btn-sm btn-icon', html: icons.trash, title: 'Supprimer',
      onClick: async () => {
        const ok = await confirmDialog({
          title: 'Supprimer ce document ?',
          message: 'Le document sera supprimé du graphe et des chunks vectoriels. Action réversible si vous gardez l\'archive.',
          danger: true, okLabel: 'Supprimer',
        });
        if (!ok) return;
        try { await api.deleteDoc(kb.id, d.id, false); toast.warn('Supprimé'); refresh(); }
        catch (e) { toast.error(e.detail || 'Erreur'); }
      },
    }));
  }
  return items;
}

async function showJobModal(kbId, docId) {
  let job;
  try { job = await api.getJob(kbId, docId); }
  catch (e) { toast.error('Pas de job pour ce document'); return; }

  openModal({
    title: 'Job d\'ingestion',
    body: h('div', { class: 'col gap-2 text-sm' }, [
      kv('Statut', job.status),
      kv('Étape saga', job.saga_step || '—'),
      kv('Tokens in', String(job.token_usage_in)),
      kv('Tokens out', String(job.token_usage_out)),
      kv('Coût', '$' + Number(job.cost_usd || 0).toFixed(4)),
      kv('Démarré', job.started_at ? fmtDateTime(job.started_at) : '—'),
      kv('Terminé', job.finished_at ? fmtDateTime(job.finished_at) : '—'),
      job.error ? h('div', { class: 'mt-4' }, [
        h('div', { class: 'subtle text-xs mb-2' }, 'Erreur :'),
        h('pre', { class: 'font-mono', style: { whiteSpace: 'pre-wrap', background: '#fef2f2', color: '#7f1d1d', padding: '12px', borderRadius: '8px' } }, job.error),
      ]) : null,
    ]),
    footer: [h('button', { class: 'btn btn-secondary', onClick: closeModal }, 'Fermer')],
  });
}
function kv(k, v) {
  return h('div', { class: 'row between' }, [
    h('span', { class: 'subtle' }, k),
    h('span', { class: 'font-medium' }, v),
  ]);
}

function openUploadModal(kb, onDone) {
  let file = null;

  const fileLabel = h('div', { class: 'subtle text-xs' }, 'Aucun fichier sélectionné.');
  const titleInput = textInput({ name: 'title', placeholder: 'Optionnel — défaut = nom du fichier' });

  const drop = h('div', { class: 'upload-zone' }, [
    h('div', { html: icons.upload, style: { color: 'var(--color-text-muted)', display: 'flex', justifyContent: 'center' } }),
    h('p', { class: 'mt-2' }, 'Glisse un fichier ici ou clique pour choisir.'),
    h('p', { class: 'subtle text-xs mt-2' }, 'PDF, image scannée, texte. ≤ 200 MB.'),
    fileLabel,
  ]);
  const fileInput = h('input', {
    type: 'file', accept: '.pdf,.png,.jpg,.jpeg,.tif,.tiff,.txt,.md',
    style: { display: 'none' },
    onChange: (e) => onFile(e.target.files[0]),
  });
  drop.appendChild(fileInput);
  drop.addEventListener('click', () => fileInput.click());
  drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('dragover'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('dragover'));
  drop.addEventListener('drop', (e) => {
    e.preventDefault(); drop.classList.remove('dragover');
    onFile(e.dataTransfer.files[0]);
  });
  function onFile(f) {
    file = f || null;
    fileLabel.textContent = f ? `${f.name} (${(f.size / 1024 / 1024).toFixed(2)} MB)` : 'Aucun fichier sélectionné.';
  }

  const upload = async () => {
    if (!file) { toast.warn('Choisis un fichier'); return; }
    submitBtn.disabled = true; submitBtn.textContent = 'Upload…';
    try {
      await api.uploadDoc(kb.id, file, { title: titleInput.value || undefined });
      toast.success('Document importé. L\'ingestion démarre.');
      closeModal();
      onDone?.();
    } catch (err) {
      toast.error(err.detail || 'Échec upload');
      submitBtn.disabled = false; submitBtn.textContent = 'Importer';
    }
  };

  const submitBtn = h('button', { class: 'btn btn-primary', onClick: upload }, 'Importer');
  const cancelBtn = h('button', { class: 'btn btn-secondary', onClick: closeModal }, 'Annuler');

  openModal({
    title: 'Importer un document',
    body: h('div', { class: 'col gap-4' }, [
      drop,
      field('Titre (facultatif)', titleInput),
    ]),
    footer: [cancelBtn, submitBtn],
  });
}

// ─── Graph ──────────────────────────────────────────────────────────
async function renderGraphTab(root, kb) {
  clear(root);
  const container = h('div', { class: 'graph-container' });
  root.appendChild(container);

  const cytoBox = h('div', { style: { width: '100%', height: '100%' } });
  container.appendChild(cytoBox);

  const controls = h('div', { class: 'graph-controls' }, [
    h('button', { class: 'btn btn-sm btn-secondary', onClick: () => load() }, [h('span', { html: icons.refresh }), 'Recharger']),
  ]);
  container.appendChild(controls);

  const legend = h('div', { class: 'graph-legend' });
  for (const t of knownTypes()) {
    legend.appendChild(h('div', {}, [
      h('span', { class: 'swatch', style: { background: colorForType(t) } }),
      h('span', {}, t),
    ]));
  }
  container.appendChild(legend);

  async function load() {
    cytoBox.innerHTML = '';
    cytoBox.appendChild(h('div', { class: 'loading-row' }, [h('span', { class: 'spinner' }), 'Chargement du graphe…']));
    try {
      const data = await api.graph(kb.id, 250);
      cytoBox.innerHTML = '';
      if (!data.nodes?.length) {
        cytoBox.appendChild(h('div', { class: 'empty', style: { margin: 'auto', maxWidth: 400 } }, [
          h('h3', {}, 'Graphe vide'),
          h('p', {}, 'Importe et indexe au moins un document pour voir apparaître entités et relations.'),
        ]));
        return;
      }
      renderGraph(cytoBox, data, {
        onNodeClick: (n) => navigate(`#/kbs/${kb.id}/entities/${encodeURIComponent(n.id)}`),
      });
    } catch (e) {
      cytoBox.innerHTML = '';
      cytoBox.appendChild(h('div', { class: 'empty' }, [h('h3', {}, 'Erreur'), h('p', {}, e.detail || String(e))]));
    }
  }
  await load();
}

// ─── Communities ────────────────────────────────────────────────────
async function renderCommunitiesTab(root, kb) {
  clear(root);
  root.appendChild(h('div', { class: 'row between mb-4' }, [
    h('p', { class: 'muted text-sm' },
      'Communautés détectées par algorithme de Leiden sur le sous-graphe entités-relations.'),
    h('button', {
      class: 'btn btn-secondary',
      onClick: async () => {
        try {
          await api.rebuildCommunities(kb.id);
          toast.success('Recalcul lancé en arrière-plan. Recharge dans quelques minutes.');
        } catch (e) { toast.error(e.detail || 'Erreur'); }
      },
    }, [h('span', { html: icons.refresh }), 'Recalculer (Leiden)']),
  ]));

  let comms = [];
  try { comms = await api.listCommunities(kb.id); }
  catch (e) { toast.error(e.detail || 'Erreur'); }

  if (!comms.length) {
    root.appendChild(h('div', { class: 'empty' }, [
      h('h3', {}, 'Aucune communauté détectée'),
      h('p', {}, 'Indexe quelques documents puis lance "Recalculer". Nécessite le plugin Neo4j GDS.'),
    ]));
    return;
  }

  const list = h('div', { class: 'community-list' });
  for (const c of comms) {
    list.appendChild(h('div', { class: 'community' }, [
      h('div', { class: 'head' }, [
        h('h4', {}, c.label),
        h('span', { class: 'subtle text-xs' }, `${c.member_entity_ids?.length || 0} entités`),
      ]),
      h('p', { class: 'summary' }, c.summary || ''),
      h('div', { class: 'mt-4 row gap-2', style: { flexWrap: 'wrap' } },
        (c.member_entity_ids || []).slice(0, 30).map(eid =>
          h('span', {
            class: 'entity-pill',
            onClick: () => navigate(`#/kbs/${kb.id}/entities/${encodeURIComponent(eid)}`),
          }, [h('span', {}, eid)]),
        )),
    ]));
  }
  root.appendChild(list);
}

// ─── Members ────────────────────────────────────────────────────────
async function renderMembersTab(root, kb) {
  clear(root);

  const refreshBtn = h('button', {
    class: 'btn btn-primary',
    onClick: () => openInviteModal(),
  }, [h('span', { html: icons.plus }), 'Ajouter un membre']);

  root.appendChild(h('div', { class: 'row between mb-4' }, [
    h('p', { class: 'muted text-sm' }, 'Gère les rôles d\'accès à cette base de connaissance.'),
    refreshBtn,
  ]));

  const tableWrap = h('div');
  root.appendChild(tableWrap);

  async function load() {
    clear(tableWrap);
    let members = [];
    try { members = await api.listMembers(kb.id); }
    catch (e) { toast.error(e.detail || 'Erreur'); }

    if (!members.length) {
      tableWrap.appendChild(h('div', { class: 'empty' }, [
        h('h3', {}, 'Aucun membre'),
        h('p', {}, 'Ajoute des collaborateurs pour partager cette base.'),
      ]));
      return;
    }
    const table = h('table', { class: 'table members-table' }, [
      h('thead', {}, h('tr', {}, [
        h('th', {}, 'Email'), h('th', {}, 'Rôle'),
      ])),
      h('tbody', {}, members.map(m => h('tr', {}, [
        h('td', {}, m.email),
        h('td', {}, h('span', { class: 'badge ' + roleBadge(m.role), style: { width: '90px', justifyContent: 'center' } }, m.role)),
      ]))),
    ]);
    tableWrap.appendChild(table);
  }

  function openInviteModal() {
    let role = 'reader';
    const formEl = h('form', { onSubmit: async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      try {
        await api.addMember(kb.id, fd.get('email'), role);
        toast.success('Membre ajouté');
        closeModal();
        load();
      } catch (err) { toast.error(err.detail || 'Erreur'); }
    } }, [
      field('Email', textInput({ name: 'email', type: 'email', required: true, placeholder: 'collaborateur@example.com' })),
      h('div', { class: 'mt-4' }, [
        field('Rôle', select({
          name: 'role', value: role,
          options: [
            { value: 'reader',   label: 'Reader — lecture seule' },
            { value: 'proposer', label: 'Proposer — peut proposer des documents' },
            { value: 'editor',   label: 'Editor — peut importer directement (sans approbation)' },
            { value: 'admin',    label: 'Admin — gère membres et approbations' },
          ],
          onChange: (v) => { role = v; },
        })),
      ]),
      h('p', { class: 'login-help mt-4' },
        'L\'utilisateur doit déjà exister dans l\'organisation. ' +
        'Demande à un administrateur global de créer son compte si besoin.'),
    ]);
    openModal({
      title: 'Ajouter un membre',
      body: formEl,
      footer: [
        h('button', { class: 'btn btn-secondary', onClick: closeModal }, 'Annuler'),
        h('button', { class: 'btn btn-primary', onClick: () => formEl.requestSubmit() }, 'Ajouter'),
      ],
    });
  }

  function roleBadge(r) {
    return ({ admin: 'badge-violet', editor: 'badge-blue', reader: 'badge-gray', proposer: 'badge-amber' }[r] || 'badge-gray');
  }

  await load();
}
