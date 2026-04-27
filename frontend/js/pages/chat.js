import { h, clear, fmtRelative, renderCitations, fmtDate, initials } from '../utils.js';
import { api } from '../api.js';
import { navigate } from '../router.js';
import { toast } from '../components/toast.js';
import { openModal, closeModal } from '../components/modal.js';
import { field, textInput, select } from '../components/forms.js';
import { icons } from '../components/icons.js';
import { renderShell } from './_shell.js';
import { readSSE } from '../sse.js';
import { getState } from '../state.js';

export async function renderChat(root, params, ctx) {
  const queryParams = parseQuery();
  await renderShell(root, ctx, [{ label: 'Chat' }], async (main) => {
    main.appendChild(buildChatPage(queryParams));
  });
}

function parseQuery() {
  const hash = location.hash;
  const qIdx = hash.indexOf('?');
  if (qIdx < 0) return {};
  const out = {};
  for (const [k, v] of new URLSearchParams(hash.slice(qIdx + 1))) out[k] = v;
  return out;
}

function buildChatPage(qp) {
  const page = h('div', { class: 'chat-page' });
  const sidebar = h('aside', { class: 'chat-sidebar' });
  const mainCol = h('section', { class: 'chat-main' });
  page.append(sidebar, mainCol);

  // State scoped to this page
  let conversations = [];
  let activeConvId = qp.conv || null;
  let activeKbId = qp.kb || null;
  let activeGemId = null;
  let kbs = [];
  let gems = [];
  let messages = [];
  let isStreaming = false;

  const convList = h('div', { class: 'conv-list' });

  sidebar.append(
    h('header', {}, [
      h('h2', {}, 'Conversations'),
      h('button', {
        class: 'btn btn-icon', html: icons.plus, title: 'Nouvelle conversation',
        onClick: () => openNewConvModal(),
      }),
    ]),
    convList,
  );

  const headerEl = h('div', { class: 'chat-header' });
  const messagesEl = h('div', { class: 'chat-messages' });
  const inputRow = h('div', { class: 'chat-input-row' });
  mainCol.append(headerEl, messagesEl, inputRow);

  const textareaEl = h('textarea', {
    placeholder: 'Pose une question à la base de connaissance…',
    rows: 1,
    onKeyDown: (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    },
    onInput: (e) => {
      e.target.style.height = 'auto';
      e.target.style.height = Math.min(e.target.scrollHeight, 200) + 'px';
    },
  });
  const sendBtn = h('button', { class: 'chat-send-btn', html: icons.send, onClick: sendMessage });
  const includeSupersededCheckbox = h('input', { type: 'checkbox' });

  const inputForm = h('form', {
    class: 'chat-input-form',
    onSubmit: (e) => { e.preventDefault(); sendMessage(); },
  }, [textareaEl, sendBtn]);
  const optsEl = h('div', { class: 'chat-options' }, [
    h('label', {}, [includeSupersededCheckbox, 'Inclure les versions remplacées']),
  ]);
  inputRow.append(inputForm, optsEl);

  // Bootstrap data
  init();

  async function init() {
    try {
      [kbs, gems, conversations] = await Promise.all([
        api.listKbs(), api.listGems(), api.listConversations(),
      ]);
    } catch (e) {
      toast.error(e.detail || 'Erreur de chargement');
    }
    renderSidebarList();
    if (activeConvId) await openConversation(activeConvId);
    else if (kbs.length) showWelcome();
    else showNoKb();
  }

  function renderSidebarList() {
    clear(convList);
    if (!conversations.length) {
      convList.appendChild(h('div', { class: 'subtle text-sm', style: { padding: 'var(--sp-4)' } },
        'Aucune conversation pour le moment.'));
      return;
    }
    for (const c of conversations) {
      const kb = kbs.find(k => k.id === c.kb_id);
      const item = h('div', {
        class: 'conv-item' + (c.id === activeConvId ? ' active' : ''),
        onClick: () => openConversation(c.id),
      }, [
        h('div', { class: 'title truncate' }, c.title || 'Sans titre'),
        h('div', { class: 'meta' }, [
          h('span', { class: 'truncate' }, kb?.name || c.kb_id.slice(0, 8)),
          h('span', {}, '·'),
          h('span', {}, fmtRelative(c.created_at)),
        ]),
      ]);
      convList.appendChild(item);
    }
  }

  function showWelcome() {
    clear(headerEl);
    headerEl.appendChild(h('div', { class: 'col gap-2' }, [
      h('div', { class: 'title' }, 'Démarre une conversation'),
      h('div', { class: 'meta' }, 'Choisis une base de connaissance pour commencer.'),
    ]));
    clear(messagesEl);
    messagesEl.appendChild(h('div', { class: 'empty', style: { margin: 'auto', maxWidth: 480 } }, [
      h('h3', {}, 'Bienvenue 👋'),
      h('p', {}, 'Crée une nouvelle conversation et pose tes questions à une base. Les réponses citent toujours leurs sources avec dates.'),
      h('button', {
        class: 'btn btn-primary',
        onClick: () => openNewConvModal(),
      }, 'Nouvelle conversation'),
    ]));
    textareaEl.disabled = true; sendBtn.disabled = true;
  }

  function showNoKb() {
    clear(headerEl);
    headerEl.appendChild(h('div', {}, [h('div', { class: 'title' }, 'Aucune base accessible')]));
    clear(messagesEl);
    messagesEl.appendChild(h('div', { class: 'empty', style: { margin: 'auto', maxWidth: 480 } }, [
      h('h3', {}, 'Pas encore de base'),
      h('p', {}, 'Demande à un administrateur l\'accès à une base, ou crées-en une depuis l\'onglet "Bases".'),
      h('button', { class: 'btn btn-primary', onClick: () => navigate('#/kbs') }, 'Voir les bases'),
    ]));
    textareaEl.disabled = true; sendBtn.disabled = true;
  }

  async function openConversation(id) {
    activeConvId = id;
    const conv = conversations.find(c => c.id === id);
    if (!conv) {
      toast.error('Conversation introuvable');
      return;
    }
    activeKbId = conv.kb_id;
    activeGemId = conv.gem_id || null;
    renderSidebarList();
    renderHeader(conv);
    clear(messagesEl);
    messagesEl.appendChild(h('div', { class: 'loading-row' }, [h('span', { class: 'spinner' }), 'Chargement…']));
    try {
      messages = await api.listMessages(id);
    } catch (e) {
      toast.error(e.detail || 'Erreur');
      messages = [];
    }
    clear(messagesEl);
    for (const m of messages) renderMessage(m);
    textareaEl.disabled = false; sendBtn.disabled = false;
    textareaEl.focus();
    location.hash = `#/chat?conv=${id}`;
  }

  function renderHeader(conv) {
    clear(headerEl);
    const kb = kbs.find(k => k.id === conv.kb_id);
    const gem = gems.find(g => g.id === conv.gem_id);
    headerEl.append(
      h('div', { class: 'col gap-2' }, [
        h('div', { class: 'title' }, conv.title || 'Sans titre'),
        h('div', { class: 'meta' }, [
          (kb?.name || 'KB ' + conv.kb_id.slice(0, 8)) + (gem ? ` · Gem: ${gem.name}` : ''),
        ]),
      ]),
      h('a', { href: `#/kbs/${conv.kb_id}` }, h('button', { class: 'btn btn-secondary' }, 'Voir la base')),
    );
  }

  function renderMessage(m) {
    const wrap = h('div', { class: `chat-msg ${m.role}` });
    const avatar = h('div', { class: 'avatar' }, m.role === 'user' ? initials(getState().user?.email) : 'AI');
    const body = h('div', { class: 'body' });
    body.appendChild(h('div', { class: 'who' }, m.role === 'user' ? 'Vous' : 'Sonar-Echo'));
    const content = h('div', { class: 'content', html: renderCitations(m.content || '') });
    body.appendChild(content);

    if (m.role === 'assistant' && Array.isArray(m.citations) && m.citations.length) {
      body.appendChild(renderCitationsBlock(m.citations));
    }
    if (m.role === 'assistant' && m.retrieval) {
      const rb = renderRetrievalAside(m.retrieval);
      if (rb) body.appendChild(rb);
      body.appendChild(renderMessageActions(m));
    }

    wrap.append(avatar, body);
    messagesEl.appendChild(wrap);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return { wrap, content, body };
  }

  function renderCitationsBlock(citations) {
    return h('div', { class: 'citations' }, [
      h('h5', {}, 'Sources'),
      h('ol', {}, citations.map(c => h('li', {}, [
        h('strong', {}, c.doc_title),
        c.source_date ? ' · ' : '',
        c.source_date ? h('span', { class: 'date' }, fmtDate(c.source_date)) : '',
        c.page ? ` · p. ${c.page}` : '',
        ' · ',
        h('span', { class: 'subtle' }, c.chunk_id),
      ]))),
    ]);
  }

  function renderRetrievalAside(retrieval) {
    const ents = retrieval?.entities || [];
    const tl   = retrieval?.timeline || [];
    const cms  = retrieval?.communities || [];
    if (!ents.length && !tl.length && !cms.length) return null;
    const detail = h('details', {}, [
      h('summary', {}, `Contexte récupéré · ${ents.length} entités · ${tl.length} events · ${cms.length} communautés`),
    ]);
    if (ents.length) {
      detail.appendChild(h('h6', {}, 'Entités'));
      detail.appendChild(h('div', { class: 'group-row' }, ents.map(e =>
        h('span', {
          class: 'entity-pill',
          onClick: () => navigate(`#/kbs/${activeKbId}/entities/${encodeURIComponent(e.id)}`),
        }, [
          h('span', { class: 'type' }, e.type),
          h('span', {}, e.canonical_name || e.id),
        ])
      )));
    }
    if (tl.length) {
      detail.appendChild(h('h6', {}, 'Timeline'));
      detail.appendChild(h('ul', { style: { paddingLeft: '1.2rem', listStyle: 'disc' } }, tl.slice(0, 10).map(t =>
        h('li', { style: { marginBottom: '4px', color: 'var(--color-text-muted)' } },
          `${t.valid_from || '?'} → ${t.valid_to || '?'} : ${t.entity_id} ―${t.type}― ${t.related_entity_id || '?'}`),
      )));
    }
    if (cms.length) {
      detail.appendChild(h('h6', {}, 'Communautés'));
      detail.appendChild(h('ul', { style: { paddingLeft: '1.2rem', listStyle: 'disc' } }, cms.map(c =>
        h('li', { style: { marginBottom: '4px' } }, [
          h('strong', {}, c.label),
          ' — ',
          h('span', { class: 'muted' }, (c.summary || '').slice(0, 160)),
        ]),
      )));
    }
    return h('div', { class: 'retrieval-aside' }, detail);
  }

  function renderMessageActions(m) {
    let rating = 0;
    const upBtn   = h('button', { html: icons.thumbsUp, title: 'Bonne réponse' });
    const downBtn = h('button', { html: icons.thumbsDown, title: 'Mauvaise réponse' });
    upBtn.onclick   = async () => sendFeedback(1, upBtn);
    downBtn.onclick = async () => sendFeedback(-1, downBtn);

    async function sendFeedback(r, btn) {
      try {
        await api.feedback(m.id, r, null);
        rating = r;
        upBtn.classList.toggle('active', r === 1);
        downBtn.classList.toggle('active', r === -1);
        toast.success('Merci pour le feedback !');
      } catch (e) { toast.error(e.detail || 'Erreur'); }
    }

    return h('div', { class: 'meta-row' }, [
      h('span', {}, m.cost_usd ? `coût $${Number(m.cost_usd).toFixed(4)}` : ''),
      upBtn, downBtn,
    ]);
  }

  async function sendMessage() {
    const content = textareaEl.value.trim();
    if (!content || isStreaming || !activeConvId) return;
    isStreaming = true;
    sendBtn.disabled = true; textareaEl.disabled = true;

    // optimistic user bubble
    renderMessage({ role: 'user', content });
    textareaEl.value = '';
    textareaEl.style.height = 'auto';

    // assistant bubble (placeholder, will be filled progressively)
    const asst = renderMessage({ role: 'assistant', content: '', citations: [], retrieval: {} });
    asst.content.classList.add('streaming-cursor');
    asst.content.textContent = '';
    let retrievalPayload = null;
    let messageMeta = null;

    try {
      const resp = await api.postMessageStream(activeConvId, {
        content, include_superseded: includeSupersededCheckbox.checked,
      });
      if (!resp.ok) throw new Error('SSE init failed');

      await readSSE(resp, (evt) => {
        if (evt.type === 'status') {
          asst.content.textContent = evt.stage === 'retrieval' ? '🔍 Recherche…' : '✍️ Génération…';
        } else if (evt.type === 'retrieval') {
          retrievalPayload = evt.payload;
          asst.content.textContent = `🧩 ${retrievalPayload.chunks?.length || 0} chunks · ${retrievalPayload.entities?.length || 0} entités`;
        } else if (evt.type === 'message') {
          messageMeta = evt;
          asst.content.classList.remove('streaming-cursor');
          asst.content.innerHTML = renderCitations(evt.text || '');
          if (evt.citations?.length) asst.body.appendChild(renderCitationsBlock(evt.citations));
          const r = renderRetrievalAside(retrievalPayload || {
            entities: evt.entities, timeline: evt.timeline, communities: evt.communities,
          });
          if (r) asst.body.appendChild(r);
          asst.body.appendChild(renderMessageActions({
            id: evt.message_id,
            cost_usd: 0,
          }));
          // refresh sidebar conversation list (potential title update)
          api.listConversations().then(cs => {
            conversations = cs;
            renderSidebarList();
          }).catch(() => {});
        } else if (evt.type === 'done') {
          // nothing extra
        }
      });
    } catch (err) {
      asst.content.classList.remove('streaming-cursor');
      asst.content.textContent = `⚠️ Erreur : ${err.message || err}`;
      toast.error('Échec de la génération');
    } finally {
      isStreaming = false;
      sendBtn.disabled = false; textareaEl.disabled = false;
      textareaEl.focus();
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
  }

  function openNewConvModal() {
    if (!kbs.length) { toast.warn('Crée d\'abord une base.'); return; }

    let kbValue = activeKbId || kbs[0].id;
    let gemValue = '';
    let titleValue = '';

    const kbSelect = select({
      name: 'kb', value: kbValue,
      options: kbs.map(k => ({ value: k.id, label: k.name })),
      onChange: (v) => { kbValue = v; },
    });
    const gemSelect = select({
      name: 'gem', value: gemValue,
      options: [{ value: '', label: '— Aucune (réponse standard) —' }].concat(
        gems.map(g => ({ value: g.id, label: g.name }))
      ),
      onChange: (v) => { gemValue = v; },
    });
    const titleInput = textInput({ name: 'title', placeholder: 'Optionnel', onInput: (v) => { titleValue = v; } });

    const submit = async () => {
      try {
        const c = await api.createConversation({
          kb_id: kbValue,
          gem_id: gemValue || null,
          title: titleValue || null,
        });
        conversations = [c, ...conversations];
        renderSidebarList();
        closeModal();
        await openConversation(c.id);
      } catch (e) { toast.error(e.detail || 'Erreur'); }
    };

    openModal({
      title: 'Nouvelle conversation',
      body: h('div', { class: 'col gap-4' }, [
        field('Base de connaissance', kbSelect),
        field('Gem (system prompt)', gemSelect, 'Optionnel — surcharge le prompt système avec un Gem.'),
        field('Titre', titleInput, 'Sera auto-généré si vide.'),
      ]),
      footer: [
        h('button', { class: 'btn btn-secondary', onClick: closeModal }, 'Annuler'),
        h('button', { class: 'btn btn-primary', onClick: submit }, 'Créer'),
      ],
    });
  }

  return page;
}
