import { initTheme, toggleTheme } from './theme.js';
import { updateStatusFavicon } from './favicon.js';

const MAIL_DOMAIN = document.querySelector('meta[name="mail-domain"]')?.content || '';

document.getElementById('theme-toggle-btn')?.addEventListener('click', toggleTheme);
initTheme();
updateStatusFavicon(null);

function paintMailBeacon(status) {
  const orb = document.getElementById('status-mail-orb');
  const chip = document.getElementById('status-mail-chip');
  const kind = status.ok ? 'ok' : status.stale ? 'stale' : 'alarm';
  if (orb) {
    orb.className = `status-beacon header-status-orb status-beacon--${kind}`;
  }
  if (chip) {
    const label = kind === 'ok' ? 'ok' : kind === 'alarm' ? 'down' : 'unknown';
    chip.title = `Mail: ${label}`;
    chip.setAttribute('aria-label', `Mail: ${label}`);
  }
  updateStatusFavicon(status);
}

async function pollMailHealth() {
  try {
    const res = await fetch('/api/health', { cache: 'no-store', credentials: 'same-origin' });
    if (res.status === 401) {
      location.replace('/login');
      return;
    }
    const data = await res.json().catch(() => ({}));
    paintMailBeacon({
      overall: data.ok ? 'ok' : 'down',
      ok: Boolean(data.ok),
      stale: false,
    });
  } catch {
    paintMailBeacon({ overall: 'unknown', ok: false, stale: true });
  }
}

const MIN_PASSWORD_LEN = 6;
const body = document.getElementById('users-body');
const countEl = document.getElementById('users-count');
const errorEl = document.getElementById('users-error');
const addForm = document.getElementById('users-add');
const pwModal = document.getElementById('pw-modal');
const pwUser = document.getElementById('pw-modal-user');
const pwInput = document.getElementById('pw-modal-input');
const pwError = document.getElementById('pw-modal-error');
const pwFormView = document.getElementById('pw-modal-form-view');
const pwDoneView = document.getElementById('pw-modal-done-view');
const pwOk = document.getElementById('pw-modal-ok');
let pwLocal = '';
let pwBusy = false;
const arModal = document.getElementById('ar-modal');
const arUser = document.getElementById('ar-modal-user');
const arInput = document.getElementById('ar-modal-input');
const arStart = document.getElementById('ar-modal-start');
const arEnd = document.getElementById('ar-modal-end');
const arError = document.getElementById('ar-modal-error');
const arFormView = document.getElementById('ar-modal-form-view');
const arDoneView = document.getElementById('ar-modal-done-view');
const arOk = document.getElementById('ar-modal-ok');
let arLocal = '';
let arBusy = false;
let arLoaded = false;

const rdModal = document.getElementById('rd-modal');
const rdUser = document.getElementById('rd-modal-user');
const rdInput = document.getElementById('rd-modal-input');
const rdError = document.getElementById('rd-modal-error');
const rdFormView = document.getElementById('rd-modal-form-view');
const rdDoneView = document.getElementById('rd-modal-done-view');
const rdOk = document.getElementById('rd-modal-ok');
const rdList = document.getElementById('rd-modal-list');
let rdLocal = '';
let rdBusy = false;
let rdDests = [];
let rdLoaded = false;

function showError(message) {
  if (!errorEl) return;
  if (!message) {
    errorEl.hidden = true;
    errorEl.textContent = '';
    return;
  }
  errorEl.hidden = false;
  errorEl.textContent = message;
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || res.statusText || 'request failed');
  }
  return data;
}

function rowHtml(user) {
  const local = user.local;
  return `<tr>
    <td>${escapeHtml(local)}</td>
    <td>${escapeHtml(user.email)}</td>
    <td class="users-row-actions">
      <button type="button" class="btn btn-primary" data-action="password" data-local="${escapeAttr(local)}">Password</button>
      <button type="button" class="btn btn-primary" data-action="autoreply" data-local="${escapeAttr(local)}">Auto-reply</button>
      <button type="button" class="btn btn-primary" data-action="redirect" data-local="${escapeAttr(local)}">Redirect</button>
      <button type="button" class="btn btn-primary" data-action="delete" data-local="${escapeAttr(local)}">Delete</button>
    </td>
  </tr>`;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escapeAttr(value) {
  return escapeHtml(value);
}

async function refresh() {
  const data = await api('/api/users');
  const users = data.users || [];
  if (countEl) countEl.textContent = String(users.length);
  if (body) body.innerHTML = users.map(rowHtml).join('');
}

addForm?.addEventListener('submit', async (event) => {
  event.preventDefault();
  showError('');
  const form = new FormData(addForm);
  try {
    await api('/api/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams(form).toString(),
    });
    addForm.reset();
    await refresh();
  } catch (err) {
    showError(err.message);
  }
});

function showPwError(message) {
  if (!pwError) return;
  if (!message) {
    pwError.hidden = true;
    pwError.textContent = '';
    return;
  }
  pwError.hidden = false;
  pwError.textContent = message;
}

function setPwMode(done) {
  if (pwFormView) pwFormView.hidden = done;
  if (pwDoneView) pwDoneView.hidden = !done;
}

function closePasswordModal() {
  if (!pwModal) return;
  pwModal.hidden = true;
  pwLocal = '';
  pwBusy = false;
  if (pwInput) pwInput.value = '';
  showPwError('');
  setPwMode(false);
}

function openPasswordModal(local) {
  if (!pwModal || !pwInput) return;
  pwLocal = local;
  pwBusy = false;
  if (pwUser) pwUser.textContent = local;
  pwInput.value = '';
  showPwError('');
  setPwMode(false);
  pwModal.hidden = false;
  pwInput.focus();
}

async function submitPasswordModal() {
  if (pwBusy || !pwLocal) return;
  const password = (pwInput?.value || '').trim();
  if (password.length < MIN_PASSWORD_LEN) {
    showPwError('At least 6 characters');
    pwInput?.focus();
    return;
  }
  pwBusy = true;
  showPwError('');
  if (pwOk) pwOk.disabled = true;
  try {
    await api(`/api/users/${encodeURIComponent(pwLocal)}/password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ password }).toString(),
    });
    setPwMode(true);
    document.getElementById('pw-modal-close')?.focus();
    await refresh();
  } catch (err) {
    showPwError(err.message);
    pwInput?.focus();
  } finally {
    pwBusy = false;
    if (pwOk) pwOk.disabled = false;
  }
}

body?.addEventListener('click', async (event) => {
  const btn = event.target.closest('button[data-action]');
  if (!btn) return;
  const local = btn.getAttribute('data-local');
  const action = btn.getAttribute('data-action');
  showError('');
  if (action === 'password') {
    openPasswordModal(local);
    return;
  }
  if (action === 'autoreply') {
    openAutoreplyModal(local);
    return;
  }
  if (action === 'redirect') {
    openRedirectModal(local);
    return;
  }
  try {
    if (action === 'delete') {
      if (!confirm(`Delete ${local}? Mailbox files stay on disk.`)) return;
      await api(`/api/users/${encodeURIComponent(local)}/delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: '',
      });
      await refresh();
    }
  } catch (err) {
    showError(err.message);
  }
});

pwModal?.addEventListener('click', (event) => {
  if (event.target.closest('[data-pw-dismiss]')) closePasswordModal();
});
document.getElementById('pw-modal-cancel')?.addEventListener('click', closePasswordModal);
document.getElementById('pw-modal-close')?.addEventListener('click', closePasswordModal);
pwOk?.addEventListener('click', () => {
  submitPasswordModal();
});
pwInput?.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    event.preventDefault();
    submitPasswordModal();
  }
});
function showArError(message) {
  if (!arError) return;
  if (!message) {
    arError.hidden = true;
    arError.textContent = '';
    return;
  }
  arError.hidden = false;
  arError.textContent = message;
}

function setArMode(done) {
  if (arFormView) arFormView.hidden = done;
  if (arDoneView) arDoneView.hidden = !done;
}

function closeAutoreplyModal() {
  if (!arModal) return;
  arModal.hidden = true;
  arLocal = '';
  arBusy = false;
  arLoaded = false;
  if (arInput) arInput.value = '';
  if (arStart) arStart.value = '';
  if (arEnd) arEnd.value = '';
  if (arOk) arOk.disabled = false;
  showArError('');
  setArMode(false);
}

async function openAutoreplyModal(local) {
  if (!arModal) return;
  arLocal = local;
  arBusy = false;
  arLoaded = false;
  if (arUser) arUser.textContent = local;
  if (arInput) arInput.value = '';
  if (arStart) arStart.value = '';
  if (arEnd) arEnd.value = '';
  if (arOk) arOk.disabled = true;
  showArError('');
  setArMode(false);
  arModal.hidden = false;
  try {
    const data = await api(`/api/users/${encodeURIComponent(local)}/autoreply`);
    if (arLocal !== local) return;
    if (arInput) arInput.value = typeof data.body === 'string' ? data.body : '';
    if (arStart) arStart.value = typeof data.start_date === 'string' ? data.start_date : '';
    if (arEnd) arEnd.value = typeof data.end_date === 'string' ? data.end_date : '';
    arLoaded = true;
    if (arOk) arOk.disabled = false;
  } catch (err) {
    showArError(err.message);
  }
  arInput?.focus();
}

async function submitAutoreplyModal() {
  if (arBusy || !arLocal || !arLoaded) return;
  arBusy = true;
  showArError('');
  if (arOk) arOk.disabled = true;
  try {
    const start = (arStart?.value || '').trim();
    const end = (arEnd?.value || '').trim();
    if (start && end && end < start) {
      showArError('End is before start');
      return;
    }
    await api(`/api/users/${encodeURIComponent(arLocal)}/autoreply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ body: arInput?.value || '', start_date: start, end_date: end }).toString(),
    });
    setArMode(true);
    document.getElementById('ar-modal-close')?.focus();
    await refresh();
  } catch (err) {
    showArError(err.message);
  } finally {
    arBusy = false;
    if (arOk) arOk.disabled = false;
  }
}

arModal?.addEventListener('click', (event) => {
  if (event.target.closest('[data-ar-dismiss]')) closeAutoreplyModal();
});
document.getElementById('ar-modal-cancel')?.addEventListener('click', closeAutoreplyModal);
document.getElementById('ar-modal-close')?.addEventListener('click', closeAutoreplyModal);
arOk?.addEventListener('click', () => {
  submitAutoreplyModal();
});

function showRdError(message) {
  if (!rdError) return;
  if (!message) {
    rdError.hidden = true;
    rdError.textContent = '';
    return;
  }
  rdError.hidden = false;
  rdError.textContent = message;
}

function setRdMode(done) {
  if (rdFormView) rdFormView.hidden = done;
  if (rdDoneView) rdDoneView.hidden = !done;
}

function renderRdList() {
  if (!rdList) return;
  rdList.innerHTML = rdDests
    .map(
      (dest) => `<li class="rd-modal__item">
      <span>${escapeHtml(dest)}</span>
      <button type="button" class="btn" data-rd-remove="${escapeAttr(dest)}">Remove</button>
    </li>`
    )
    .join('');
}

function addRdDest() {
  const raw = (rdInput?.value || '').trim().toLowerCase();
  let local = raw;
  if (raw.includes('@')) {
    const parts = raw.split('@');
    if (MAIL_DOMAIN && parts[1] !== MAIL_DOMAIN) {
      showRdError(`Only @${MAIL_DOMAIN} mailboxes`);
      return;
    }
    local = parts[0];
  }
  if (!local) {
    showRdError('Enter a mailbox');
    rdInput?.focus();
    return;
  }
  if (local === rdLocal) {
    showRdError('Cannot redirect to itself');
    return;
  }
  if (rdDests.includes(local)) {
    showRdError('Already in the list');
    return;
  }
  if (rdDests.length >= 10) {
    showRdError('At most 10');
    return;
  }
  rdDests.push(local);
  if (rdInput) rdInput.value = '';
  showRdError('');
  renderRdList();
}

function closeRedirectModal() {
  if (!rdModal) return;
  rdModal.hidden = true;
  rdLocal = '';
  rdBusy = false;
  rdDests = [];
  rdLoaded = false;
  if (rdInput) rdInput.value = '';
  if (rdOk) rdOk.disabled = false;
  showRdError('');
  setRdMode(false);
}

async function openRedirectModal(local) {
  if (!rdModal) return;
  rdLocal = local;
  rdBusy = false;
  rdDests = [];
  rdLoaded = false;
  if (rdUser) rdUser.textContent = local;
  if (rdInput) rdInput.value = '';
  if (rdOk) rdOk.disabled = true;
  showRdError('');
  setRdMode(false);
  renderRdList();
  rdModal.hidden = false;
  try {
    const data = await api(`/api/users/${encodeURIComponent(local)}/redirects`);
    if (rdLocal !== local) return;
    rdDests = Array.isArray(data.destinations) ? data.destinations.slice() : [];
    rdLoaded = true;
    if (rdOk) rdOk.disabled = false;
    renderRdList();
  } catch (err) {
    showRdError(err.message);
  }
  rdInput?.focus();
}

async function submitRedirectModal() {
  if (rdBusy || !rdLocal || !rdLoaded) return;
  rdBusy = true;
  showRdError('');
  if (rdOk) rdOk.disabled = true;
  try {
    await api(`/api/users/${encodeURIComponent(rdLocal)}/redirects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ destinations: rdDests.join(',') }).toString(),
    });
    setRdMode(true);
    document.getElementById('rd-modal-close')?.focus();
    await refresh();
  } catch (err) {
    showRdError(err.message);
  } finally {
    rdBusy = false;
    if (rdOk) rdOk.disabled = false;
  }
}

rdModal?.addEventListener('click', (event) => {
  if (event.target.closest('[data-rd-dismiss]')) closeRedirectModal();
  const remove = event.target.closest('[data-rd-remove]');
  if (remove) {
    rdDests = rdDests.filter((dest) => dest !== remove.getAttribute('data-rd-remove'));
    renderRdList();
  }
});
document.getElementById('rd-modal-cancel')?.addEventListener('click', closeRedirectModal);
document.getElementById('rd-modal-close')?.addEventListener('click', closeRedirectModal);
document.getElementById('rd-modal-add')?.addEventListener('click', addRdDest);
rdOk?.addEventListener('click', () => {
  submitRedirectModal();
});
rdInput?.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    event.preventDefault();
    addRdDest();
  }
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && pwModal && !pwModal.hidden) {
    closePasswordModal();
  }
  if (event.key === 'Escape' && arModal && !arModal.hidden) {
    closeAutoreplyModal();
  }
  if (event.key === 'Escape' && rdModal && !rdModal.hidden) {
    closeRedirectModal();
  }
});

refresh().catch((err) => showError(err.message));
pollMailHealth();
setInterval(pollMailHealth, 5000);
