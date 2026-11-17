import test from 'node:test';
import assert from 'node:assert/strict';
import {shiftBoardState} from './checksheet-shift.js';

test('grey board state is independent of the real IN or OUT state', () => {
  const employee = {status: 'IN', checksheet_shift: {state: 'finished', line: 'ABB2', overtime: false, greyAt: '2026-11-02T08:45:00Z'}};
  assert.equal(shiftBoardState(employee).finished, true);
  assert.equal(shiftBoardState(employee).label, 'Shift finished');
  assert.match(shiftBoardState(employee).detail, /NO OT/);
  assert.equal(employee.status, 'IN');
  employee.checksheet_shift.state = 'grace';
  assert.equal(shiftBoardState(employee).finished, false);
  assert.equal(shiftBoardState(employee).label, 'Shift ending');
});
test('unlinked and unavailable shifts fall back to ordinary attendance display', () => {
  assert.deepEqual(shiftBoardState({status: 'IN'}), {finished: false, label: '', detail: ''});
});

test('rotation off-shift cards turn grey and show the team hours', () => {
  const employee = {status: 'IN', checksheet_shift: {state: 'off', source: 'rotation', shift: 'Night', line: 'Team B · Night rotation', overtime: true,
    startAt: '2026-11-16T12:00:00Z', endAt: '2026-11-17T00:00:00Z', greyAt: '2026-11-17T00:30:00Z'}};
  const state = shiftBoardState(employee);
  assert.equal(state.finished, true);
  assert.equal(state.label, 'Off shift');
  assert.match(state.detail, /Team B · Night rotation · WITH OT · hours 08:00 pm–08:00 am/i);
});
