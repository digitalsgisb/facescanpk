import {test} from 'node:test';
import assert from 'node:assert/strict';
import {plantTeams,filterBoardPlant} from './plant-view.js';
import {teamHours,employeeHours} from './team-hours.js';
test('plant team choices use PK A/B and Sendayan C/D without changing employee data',()=>{
  assert.deepEqual(plantTeams('PORT KLANG'),['A','B','N']);
  assert.deepEqual(plantTeams('SENDAYAN'),['C','D','N']);
  const employees=[{id:'p',base:'PORT KLANG'},{id:'s',base:'SENDAYAN'},{id:'u'}];
  assert.deepEqual(filterBoardPlant(employees,'SENDAYAN').map(e=>e.id),['s']);
  assert.deepEqual(filterBoardPlant(employees,'PORT KLANG').map(e=>e.id),['p']);
  assert.equal(filterBoardPlant(employees,'*').length,3);
  assert.equal(employees.length,3);
});
test('C/D rotation swaps base shifts and keeps overtime with its team',()=>{
  const settings={rotation:{anchor_date:'2026-01-01',interval_days:7,schedule_ids:['day','night'],teams:['C','D']},team_overtime:{C:true,D:false},team_schedules:{N:'normal'}};
  assert.equal(teamHours(settings,'C','2026-01-01').id,'day-ot');
  assert.equal(teamHours(settings,'D','2026-01-01').id,'night');
  assert.equal(teamHours(settings,'C','2026-01-08').id,'night-ot');
  assert.equal(teamHours(settings,'D','2026-01-08').id,'day');
  assert.equal(teamHours(settings,'N','2026-01-08').id,'normal');
});
test('employee hours preview uses its own plant settings and exact template times',()=>{
  const state={settings:{team_schedules:{C:'night'}},assignments:[],schedules:[{id:'day',start:'08:00'}],plant_controls:{SENDAYAN:{team_schedules:{C:'day'}}},plant_templates:{SENDAYAN:[{id:'day',start:'09:00'}]}};
  const hours=employeeHours({id:'s',base:'SENDAYAN',team:'C'},state,'2026-01-01');
  assert.equal(hours.id,'day');assert.equal(hours.schedule.start,'09:00');
});
