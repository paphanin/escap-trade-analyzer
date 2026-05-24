const API = '';  // same-origin

// ── API helpers ────────────────────────────────────────────────────────────

async function apiFetch(path, options = {}) {
  const res = await fetch(API + path, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  return res.json();
}

async function getDocuments() {
  return apiFetch('/api/documents');
}

async function getDocument(id) {
  return apiFetch(`/api/documents/${id}`);
}

async function uploadDocument(formData) {
  return apiFetch('/api/documents', { method: 'POST', body: formData });
}

async function deleteDocument(id) {
  return apiFetch(`/api/documents/${id}`, { method: 'DELETE' });
}

async function getExtractions(docId, status) {
  const qs = status ? `?status=${status}` : '';
  return apiFetch(`/api/extractions/document/${docId}${qs}`);
}

async function updateExtraction(id, action, editedText) {
  return apiFetch(`/api/extractions/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, edited_text: editedText || null }),
  });
}

async function acceptAll(docId) {
  return apiFetch(`/api/extractions/document/${docId}/accept-all`, { method: 'POST' });
}

async function sendChat(message, sessionId) {
  return apiFetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId || null }),
  });
}

async function getChatStats() {
  return apiFetch('/api/chat/stats');
}

// ── UI helpers ─────────────────────────────────────────────────────────────

const STATUS_BADGE = {
  processing: 'bg-purple-100 text-purple-700',
  extracting: 'bg-blue-100 text-blue-700',
  parsed:     'bg-green-100 text-green-700',
  error:      'bg-red-100 text-red-700',
  pending:    'bg-amber-100 text-amber-700',
  accepted:   'bg-green-100 text-green-700',
  edited:     'bg-blue-100 text-blue-700',
  source_edited: 'bg-indigo-100 text-indigo-700',
  declined:   'bg-red-100 text-red-700',
};

const CATEGORY_BADGE = {
  data_privacy:        'bg-violet-100 text-violet-700',
  e_commerce:          'bg-sky-100 text-sky-700',
  intellectual_property: 'bg-amber-100 text-amber-700',
  customs:             'bg-emerald-100 text-emerald-700',
  general_trade:       'bg-slate-100 text-slate-600',
  dispute_resolution:  'bg-rose-100 text-rose-700',
  definitions:         'bg-gray-100 text-gray-600',
};

function statusBadgeClass(status) {
  return STATUS_BADGE[status] || 'bg-gray-100 text-gray-600';
}

function categoryBadgeClass(cat) {
  return CATEGORY_BADGE[cat] || 'bg-gray-100 text-gray-600';
}

function confidenceColor(v) {
  if (v >= 0.8) return 'bg-green-500';
  if (v >= 0.6) return 'bg-amber-500';
  return 'bg-red-400';
}

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function labelStatus(s) {
  return { processing: 'Processing', extracting: 'Extracting', parsed: 'Ready',
           error: 'Error', pending: 'Pending', accepted: 'Accepted',
           edited: 'Edited', source_edited: 'Source-edited', declined: 'Declined' }[s] || s;
}

function labelCategory(c) {
  return { data_privacy: 'Data Privacy', e_commerce: 'E-Commerce',
           intellectual_property: 'IP & Copyright', customs: 'Customs',
           general_trade: 'General Trade', dispute_resolution: 'Disputes',
           definitions: 'Definitions' }[c] || (c || '—');
}
