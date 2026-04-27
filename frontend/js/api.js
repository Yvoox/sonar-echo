// HTTP client over the FastAPI backend.
// All routes are proxied by nginx under /api/* (see nginx.conf).

import { getState, logout } from './state.js';
import { toast } from './components/toast.js';

const BASE = '/api/v1';

class ApiError extends Error {
  constructor(status, detail, body) {
    super(typeof detail === 'string' ? detail : 'API error');
    this.status = status;
    this.detail = detail;
    this.body = body;
  }
}

async function request(path, { method = 'GET', body, headers = {}, raw = false } = {}) {
  const { token } = getState();
  const isForm = body instanceof FormData;
  const h = {
    ...(isForm ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...headers,
  };

  let resp;
  try {
    resp = await fetch(BASE + path, {
      method,
      headers: h,
      body: body == null ? undefined : (isForm ? body : JSON.stringify(body)),
    });
  } catch (err) {
    toast.error('Réseau injoignable. Vérifie que le backend tourne.');
    throw err;
  }

  if (resp.status === 401) {
    if (getState().token) {
      logout();
      location.hash = '#/login';
      toast.error('Session expirée — reconnecte-toi.');
    }
    throw new ApiError(401, 'unauthenticated');
  }

  if (raw) return resp;

  if (!resp.ok) {
    let detail = 'Erreur inconnue';
    let bodyJ = null;
    try { bodyJ = await resp.json(); detail = bodyJ.detail || detail; } catch {}
    throw new ApiError(resp.status, detail, bodyJ);
  }

  if (resp.status === 204) return null;
  const ct = resp.headers.get('content-type') || '';
  return ct.includes('application/json') ? resp.json() : resp.text();
}

export const api = {
  // Auth
  login: (email, password) => request('/auth/login', { method: 'POST', body: { email, password } }),
  me: () => request('/auth/me'),
  register: (payload) => request('/auth/register', { method: 'POST', body: payload }),

  // KBs
  listKbs: () => request('/kbs'),
  createKb: (payload) => request('/kbs', { method: 'POST', body: payload }),
  getKb: (id) => request(`/kbs/${id}`),
  listMembers: (kbId) => request(`/kbs/${kbId}/members`),
  addMember: (kbId, email, role) => request(`/kbs/${kbId}/members`, { method: 'POST', body: { email, role } }),

  // Documents
  listDocs: (kbId, params = {}) => request(`/kbs/${kbId}/documents${qs(params)}`),
  uploadDoc: (kbId, file, { title, supersedes } = {}) => {
    const fd = new FormData();
    fd.append('file', file);
    if (title) fd.append('title', title);
    if (supersedes) fd.append('supersedes', supersedes);
    return request(`/kbs/${kbId}/documents`, { method: 'POST', body: fd });
  },
  approveDoc: (kbId, docId, reason) =>
    request(`/kbs/${kbId}/documents/${docId}/approve`, { method: 'POST', body: { reason } }),
  rejectDoc: (kbId, docId, reason) =>
    request(`/kbs/${kbId}/documents/${docId}/reject`, { method: 'POST', body: { reason } }),
  deleteDoc: (kbId, docId, hard = false) =>
    request(`/kbs/${kbId}/documents/${docId}${hard ? '?hard=true' : ''}`, { method: 'DELETE' }),
  getJob: (kbId, docId) => request(`/kbs/${kbId}/documents/${docId}/job`),

  // Search & retrieval
  search: (kbId, payload) => request(`/kbs/${kbId}/search`, { method: 'POST', body: payload }),
  graph: (kbId, limit = 200) => request(`/kbs/${kbId}/graph?limit=${limit}`),
  listEntities: (kbId, params = {}) => request(`/kbs/${kbId}/entities${qs(params)}`),
  getEntity: (kbId, eid) => request(`/kbs/${kbId}/entities/${encodeURIComponent(eid)}`),
  entityTimeline: (kbId, eid, params = {}) =>
    request(`/kbs/${kbId}/entities/${encodeURIComponent(eid)}/timeline${qs(params)}`),

  // Communities
  listCommunities: (kbId) => request(`/kbs/${kbId}/communities`),
  getCommunity: (kbId, cid) => request(`/kbs/${kbId}/communities/${cid}`),
  rebuildCommunities: (kbId) => request(`/kbs/${kbId}/communities/rebuild`, { method: 'POST' }),

  // Chat
  listConversations: () => request('/chat/conversations'),
  createConversation: (payload) => request('/chat/conversations', { method: 'POST', body: payload }),
  listMessages: (cid) => request(`/chat/conversations/${cid}/messages`),
  postMessageStream: (cid, payload) =>
    request(`/chat/conversations/${cid}/messages`, { method: 'POST', body: payload, raw: true }),
  feedback: (mid, rating, comment) =>
    request(`/chat/messages/${mid}/feedback`, { method: 'POST', body: { rating, comment } }),

  // Gems
  listGems: () => request('/gems'),
  createGem: (payload) => request('/gems', { method: 'POST', body: payload }),
  updateGem: (id, payload) => request(`/gems/${id}`, { method: 'PATCH', body: payload }),
  deleteGem: (id) => request(`/gems/${id}`, { method: 'DELETE' }),

  // Automations
  listAutomations: () => request('/automations'),
  createAutomation: (payload) => request('/automations', { method: 'POST', body: payload }),
  updateAutomation: (id, payload) => request(`/automations/${id}`, { method: 'PATCH', body: payload }),
  deleteAutomation: (id) => request(`/automations/${id}`, { method: 'DELETE' }),
  triggerAutomation: (id) => request(`/automations/${id}/trigger`, { method: 'POST' }),

  // Users / GDPR
  userUsage: (uid) => request(`/users/${uid}/usage`),
  eraseUser: (uid) => request(`/users/${uid}/erase`, { method: 'DELETE' }),
};

function qs(obj) {
  const e = Object.entries(obj).filter(([, v]) => v !== undefined && v !== null && v !== '');
  if (!e.length) return '';
  return '?' + e.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&');
}

export { ApiError };
