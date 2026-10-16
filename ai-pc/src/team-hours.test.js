import {test} from 'node:test';
import assert from 'node:assert/strict';
import {teamHours,employeeHours} from './team-hours.js';

const settings={team_schedules:{A:'day',B:'night'},team_overtime:{A:true,B:false},rotation:{anchor_date:'2026-10-01',interval_days:7,schedule_ids:['day','night']}};
const schedules=['day','night','day-ot','night-ot','normal'].map(id=>({id}));
test('rotation swaps shifts while OT stays with the team',()=>{
  assert.equal(teamHours(settings,'A','2026-10-02').id,'day-ot');
  assert.equal(teamHours(settings,'A','2026-10-09').id,'night-ot');
  assert.equal(teamHours(settings,'B','2026-10-02').id,'night');
  assert.equal(teamHours(settings,'B','2026-10-09').id,'day');
});
test('employee preview follows changed team and respects individual and team date overrides',()=>{
  const state={settings,schedules,assignments:[]},employee={id:'1',team:'A',schedule_id:'normal'};
  assert.equal(employeeHours(employee,state,'2026-10-09').schedule.id,'night-ot');
  assert.equal(employeeHours({...employee,team:'B'},state,'2026-10-09').schedule.id,'day');
  state.assignments=[{team:'A',start_date:'2026-10-09',end_date:'2026-10-09',schedule_id:'day'}];
  assert.equal(employeeHours(employee,state,'2026-10-09').schedule.id,'day');
  state.assignments.push({employee_id:'1',start_date:'2026-10-09',end_date:'2026-10-09',schedule_id:'normal'});
  assert.equal(employeeHours(employee,state,'2026-10-09').schedule.id,'normal');
});
test('legacy rotation OT is retained until explicit team OT is configured',()=>{
  assert.equal(teamHours({rotation:{...settings.rotation,schedule_ids:['day-ot','night']}},'A','2026-10-02').id,'day-ot');
  assert.equal(employeeHours({id:'1',team:'N',schedule_id:'normal'},{settings:{},schedules},'2026-10-09').schedule.id,'normal');
});
