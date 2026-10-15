import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createAttendanceTracker} from './attendance-events.js';

const timestamp = second => `2026-10-15T18:00:${String(second).padStart(2, '0')}+08:00`;
const employee = {id:'demo', name:'Demo Employee', nickname:'Demo', department:'Office'};
const event = (id, second, action = 'IN') => ({id, employee_id:employee.id, received_at:timestamp(second), occurred_at:timestamp(second), result:JSON.stringify({accepted:true, action})});
const snapshot = (events, second = 0) => ({time:timestamp(second), employees:[employee], recent_events:events});

test('initial records stay silent; new IN and OUT events carry employee details', () => {
  const track = createAttendanceTracker();
  assert.deepEqual(track(snapshot([event('historical', 0)])), []);
  const incoming = track(snapshot([event('out', 2, 'OUT'), event('in', 1), event('historical', 0)], 2));
  assert.deepEqual(incoming.map(item => item.action), ['IN', 'OUT']);
  assert.equal(incoming[0].employee, employee);
});

test('repeated refreshes, reconnects and stale snapshots do not replay scans', () => {
  const track = createAttendanceTracker();
  track(snapshot([]));
  assert.equal(track(snapshot([event('first', 1)], 1)).length, 1);
  assert.equal(track(snapshot([event('second', 1), event('first', 1)], 1)).length, 1);
  assert.deepEqual(track(snapshot([event('first', 1)], 1)), []);
  assert.deepEqual(track(snapshot([event('second', 1), event('first', 1)], 1)), []);
  assert.equal(track(snapshot([event('third', 2)], 2)).length, 1);
  assert.deepEqual(track(snapshot([event('first', 1)], 1)), []);
});

test('duplicate, review, rejected and malformed scan results stay silent', () => {
  const track = createAttendanceTracker();
  track(snapshot([]));
  assert.deepEqual(track(snapshot([
    event('duplicate', 1, 'DUPLICATE'), event('review', 1, 'REVIEW'),
    {...event('malformed', 1), result:'bad json'},
    {...event('rejected', 1), result:JSON.stringify({accepted:false, action:'IN'})}
  ], 1)), []);
});

test('an empty startup and delayed delivery use receipt time instead of scan time', () => {
  const track = createAttendanceTracker();
  track(snapshot([], 10));
  const delayed = {...event('delayed', 11), occurred_at:timestamp(1)};
  assert.equal(track(snapshot([delayed], 11)).length, 1);
  assert.deepEqual(track(snapshot([delayed], 12)), []);
});
