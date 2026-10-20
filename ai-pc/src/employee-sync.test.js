import {test} from 'node:test';
import assert from 'node:assert/strict';
import {syncLabel} from './employee-sync.js';
test('unknown or missing acknowledgement never implies successful sync',()=>{
  assert.match(syncLabel(),/unavailable/);
  assert.match(syncLabel('pending'),/Waiting/);
  assert.match(syncLabel('offline'),/offline/);
  assert.match(syncLabel('no_kiosk'),/No active/);
  assert.match(syncLabel('synced'),/Confirmed/);
});
