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
