import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseEmployeeFile,employeeLocation} from './transfer-utils.js';
test('plant imports require the expected format and actual rows',()=>{
  assert.throws(()=>parseEmployeeFile('{}'),/SGI/);
  assert.throws(()=>parseEmployeeFile('{"format":"sgi-employees-v1","employees":[]}'),/SGI/);
  assert.equal(parseEmployeeFile('{"format":"sgi-employees-v1","employees":[{"id":"PK"}]}').employees.length,1);
  assert.equal(parseEmployeeFile('{"format":"sgi-team-assignments-v1","plant":"SENDAYAN","employees":[{"id":"5000643","team":"D"}]}').employees[0].id,'5000643');
  assert.equal(parseEmployeeFile('{"format":"sgi-employee-roster-v1","employees":[{"id":"PK","team":"A"}]}').employees.length,1);
});
test('missing locations are explicit rather than assigned to a plant',()=>{
  assert.equal(employeeLocation({base:'SENDAYAN'}),'SENDAYAN');
  assert.equal(employeeLocation({}),'Location unassigned');
});
