import test from 'node:test';
import assert from 'node:assert/strict';
import { createUpdateGuard, startAutoUpdates } from './autoUpdate.js';

const tick = () => new Promise(resolve => setImmediate(resolve));
function event(target, type, element) { const value = new Event(type); Object.defineProperty(value, 'target', { value: element }); target.dispatchEvent(value); }
function fixture() {
  const win = new EventTarget(), doc = new EventTarget(), intervals = new Map();
  Object.assign(win, { navigator: { onLine: true }, setInterval(fn) { const id = Symbol(); intervals.set(id, fn); return id; }, clearInterval(id) { intervals.delete(id); }, fetch: async () => Response.json({ version: 'new' }) });
  Object.assign(doc, { visibilityState: 'visible', blocker: false, querySelector() { return this.blocker ? {} : null; } });
  let clock = 100000, busy = false, activations = 0;
  const updater = options => startAutoUpdates({ version: 'old', activate: async () => { activations++; }, guard: { busy: () => busy, lastActivity: () => 0 }, win, doc, now: () => clock, ...options });
  return { win, doc, intervals, updater, clock: value => { clock = value; }, busy: value => { busy = value; }, count: () => activations };
}
test('a deployed version reloads an idle device once and checks without browser cache', async () => {
  const f = fixture(), calls = [];
  f.win.fetch = async (url, options) => { calls.push([url, options]); return Response.json({ version: 'new' }); };
  const updater = f.updater(); await tick();
  assert.equal(f.count(), 1); assert.equal(calls[0][0], '/app-version.json'); assert.equal(calls[0][1].cache, 'no-store');
  await updater.check(); assert.equal(f.count(), 1); updater.stop(); assert.equal(f.intervals.size, 0);
});
test('unsaved edits defer the update until the guard clears', async () => {
  const f = fixture(); f.busy(true); const updater = f.updater(); await tick(); assert.equal(f.count(), 0);
  f.busy(false); await updater.apply(); assert.equal(f.count(), 1); updater.stop();
});
test('activity and explicit page-level blockers postpone reload until the idle window', async () => {
  const f = fixture(); let lastActivity = 99000, blocked = true;
  const updater = f.updater({ blocked: () => blocked, guard: { busy: () => false, lastActivity: () => lastActivity } });
  await tick(); assert.equal(f.count(), 0); blocked = false; await updater.apply(); assert.equal(f.count(), 0);
  lastActivity = 80000; await updater.apply(); assert.equal(f.count(), 1); updater.stop();
});
test('offline, unchanged versions and invalid HTML never reload the device', async () => {
  for (const variant of ['offline', 'same', 'html']) {
    const f = fixture();
    if (variant === 'offline') f.win.navigator.onLine = false;
    f.win.fetch = async () => variant === 'html' ? new Response('<html>sign in</html>', { headers: { 'Content-Type': 'text/html' } }) : Response.json({ version: 'old' });
    const updater = f.updater(); await tick(); assert.equal(f.count(), 0); updater.stop();
  }
});
test('reconnection checks for a new version and hidden devices wait until visible', async () => {
  const f = fixture(); f.win.navigator.onLine = false; f.doc.visibilityState = 'hidden'; const updater = f.updater(); await tick();
  f.win.navigator.onLine = true; f.win.dispatchEvent(new Event('online')); await tick(); assert.equal(f.count(), 0);
  f.doc.visibilityState = 'visible'; f.doc.dispatchEvent(new Event('visibilitychange')); await tick(); assert.equal(f.count(), 1); updater.stop();
});
test('editing that starts during the final version request blocks activation', async () => {
  const f = fixture(); let calls = 0, complete;
  f.win.fetch = async () => { if (++calls === 2) return new Promise(resolve => { complete = resolve; }); return Response.json({ version: 'new' }); };
  const updater = f.updater(); await tick(); f.busy(true); complete(Response.json({ version: 'new' })); await tick();
  assert.equal(f.count(), 0); updater.stop();
});
test('failed activation backs off and a stopped updater ignores outstanding requests', async () => {
  const f = fixture(); let attempts = 0;
  const updater = f.updater({ activate: async () => { attempts++; return false; } }); await tick();
  await updater.apply(); assert.equal(attempts, 1); f.clock(131000); await updater.apply(); assert.equal(attempts, 2); updater.stop();
  const g = fixture(); let complete; g.win.fetch = () => new Promise(resolve => { complete = resolve; });
  const other = g.updater(); other.stop(); complete(Response.json({ version: 'new' })); await tick(); assert.equal(g.count(), 0);
});
test('the guard protects dirty forms and in-flight saves, clearing only a successful unchanged submission', async () => {
  const f = fixture(); let complete;
  f.win.fetch = () => new Promise(resolve => { complete = resolve; });
  const guard = createUpdateGuard({ win: f.win, doc: f.doc, now: () => 1000 });
  const input = { type: 'text', name: 'lot', value: 'old' }, form = { tagName: 'FORM', elements: [input], isConnected: true, hasAttribute: () => false };
  event(f.doc, 'focusin', { closest: () => form }); input.value = 'new'; assert.equal(guard.busy(), true);
  event(f.doc, 'submit', form); const save = f.win.fetch('/api/setup', { method: 'POST' }); assert.equal(guard.busy(), true);
  complete(Response.json({ ok: true })); await save; assert.equal(guard.busy(), false);
  input.value = 'unsaved'; event(f.doc, 'submit', form); const failed = f.win.fetch('/api/setup', { method: 'POST' });
  complete(Response.json({ error: 'No connection' }, { status: 503 })); await failed; assert.equal(guard.busy(), true);
  event(f.doc, 'submit', form); const saving = f.win.fetch('/api/setup', { method: 'POST' }); input.value = 'typed during save';
  complete(Response.json({ ok: true })); await saving; assert.equal(guard.busy(), true);
  form.isConnected = false; assert.equal(guard.busy(), false); f.doc.blocker = true; assert.equal(guard.busy(), true);
  guard.stop();
});
