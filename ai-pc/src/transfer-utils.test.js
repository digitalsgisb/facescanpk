import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseEmployeeFile,employeeLocation} from './transfer-utils.js';
test('plant imports require the expected format and actual rows',()=>{
  assert.throws(()=>parseEmployeeFile('{}'),/SGI/);
  assert.throws(()=>parseEmployeeFile('{"format":"sgi-employees-v1","employees":[]}'),/SGI/);
  assert.equal(parseEmployeeFile('{"format":"sgi-employees-v1","employees":[{"id":"PK"}]}').employees.length,1);
});
test('missing locations are explicit rather than assigned to a plant',()=>{
  assert.equal(employeeLocation({base:'SENDAYAN'}),'SENDAYAN');
  assert.equal(employeeLocation({}),'Location unassigned');
});
