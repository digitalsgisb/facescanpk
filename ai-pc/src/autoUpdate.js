// Shared browser update policy. The server remains the source of saved production data.
export function createUpdateGuard({ win = window, doc = document, now = Date.now } = {}) {
  const baseline = new Map(), submitted = [], writes = new Set();
  let activity = now();
  const fingerprint = form => JSON.stringify([...form.elements].map(element => [element.type, element.name, element.value, element.checked, element.multiple && element.selectedOptions ? [...element.selectedOptions].map(o => o.value) : null]));
  function touch(event) {
    activity = now();
    const form = event.target?.closest?.('form');
    if (form && !baseline.has(form)) baseline.set(form, fingerprint(form));
  }
  function submit(event) {
    if (event.target?.tagName === 'FORM') submitted.push({ form: event.target, value: fingerprint(event.target), at: now() });
  }
  const original = win.fetch;
  const wrapped = async function(input, init) {
    const method = (init?.method || input?.method || 'GET').toUpperCase();
    if (['GET', 'HEAD', 'OPTIONS'].includes(method)) return original.call(win, input, init);
    const id = Symbol(); writes.add(id);
    const submission = submitted.find(item => now() - item.at < 5000);
    if (submission) submitted.splice(submitted.indexOf(submission), 1);
    try {
      const response = await original.call(win, input, init);
      if (response.ok && submission?.form.isConnected && fingerprint(submission.form) === submission.value) baseline.set(submission.form, submission.value);
      return response;
    } finally { writes.delete(id); activity = now(); }
  };
  win.fetch = wrapped;
  for (const event of ['pointerdown', 'keydown', 'focusin']) doc.addEventListener(event, touch, true);
  doc.addEventListener('submit', submit, true);
  return {
    busy() {
      if (writes.size || doc.querySelector('[role="dialog"], [aria-modal="true"], [data-update-blocked="true"]')) return true;
      for (const [form, value] of baseline) {
        if (!form.isConnected) { baseline.delete(form); continue; }
        if (form.hasAttribute('data-update-blocked')) continue;
        if (fingerprint(form) !== value) return true;
      }
      return false;
    },
    lastActivity: () => activity,
    stop() {
      if (win.fetch === wrapped) win.fetch = original;
      for (const event of ['pointerdown', 'keydown', 'focusin']) doc.removeEventListener(event, touch, true);
      doc.removeEventListener('submit', submit, true);
    }
  };
}

export function startAutoUpdates({ version, activate, guard, blocked = () => false, onState = () => {}, win = window, doc = document, now = Date.now, pollMs = 60000, idleMs = 10000 }) {
  let pending = null, stopped = false, checking = false, applying = false, finished = false, retryAt = 0;
  async function readVersion() {
    const response = await win.fetch('/app-version.json', { cache: 'no-store', credentials: 'same-origin', signal: AbortSignal.timeout(5000) });
    if (!response.ok || response.redirected || !response.headers.get('content-type')?.includes('application/json')) throw new Error('Version unavailable');
    const result = await response.json();
    if (typeof result.version !== 'string' || !result.version || result.version.length > 128) throw new Error('Invalid version');
    return result.version;
  }
  function safe() { return !stopped && !finished && win.navigator.onLine !== false && doc.visibilityState !== 'hidden' && !blocked() && !guard.busy() && now() - guard.lastActivity() >= idleMs; }
  async function apply() {
    if (!pending || applying || now() < retryAt || !safe()) return;
    applying = true;
    try {
      // Recheck availability and the guard after the network wait; typing may have started.
      const latest = await readVersion();
      if (stopped) return;
      if (latest === version) { pending = null; onState(false); return; }
      pending = latest;
      if (!safe()) return;
      if (await activate() === false) throw new Error('Activation failed');
      finished = true;
    } catch { retryAt = now() + 30000; }
    finally { applying = false; }
  }
  async function check() {
    if (stopped || checking || finished || win.navigator.onLine === false) return;
    checking = true;
    try { const latest = await readVersion(); if (!stopped) { pending = latest === version ? null : latest; onState(!!pending); } }
    catch { /* Offline/restarting servers never trigger a reload. */ }
    finally { checking = false; }
    await apply();
  }
  const resume = () => { if (doc.visibilityState !== 'hidden') check(); };
  win.addEventListener('online', resume); win.addEventListener('focus', resume); doc.addEventListener('visibilitychange', resume);
  const poll = win.setInterval(check, pollMs), idle = win.setInterval(apply, 1000);
  check();
  return { check, apply, stop() { stopped = true; win.clearInterval(poll); win.clearInterval(idle); win.removeEventListener('online', resume); win.removeEventListener('focus', resume); doc.removeEventListener('visibilitychange', resume); } };
}
