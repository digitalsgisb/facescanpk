import {test} from 'node:test';
import assert from 'node:assert/strict';
import {POSITIONS,productionSection,scheduleScopes,sortEmployees,employeeGroup} from './organisation.js';
import {employeeHours} from './team-hours.js';

test('production sections derive from lines, allow explicit reassignment, and exclude Office',()=>{
  assert.equal(productionSection({department:'PRODUCTION',line:'FC'}),'CONVERSION');
  assert.equal(productionSection({department:'production',line:' roll making '}),'ROLL MAKING');
  assert.equal(productionSection({department:'PRODUCTION',line:'FC',production_section:'ROLL MAKING'}),'ROLL MAKING');
  assert.equal(productionSection({department:'OFFICE',office_department:'PRODUCTION'}),'');
  assert.deepEqual(scheduleScopes({department:'PRODUCTION',line:'FC'}),['line:FC','section:CONVERSION','department:PRODUCTION']);
  assert.equal(employeeGroup({department:'PRODUCTION',line:'ROLL MAKING'}),'ROLL MAKING');
});
test('all requested positions sort in seniority order with legacy spellings and worker aliases',()=>{
  const employees=POSITIONS.map((position,index)=>({id:String(index),name:String(index),position}));
  assert.deepEqual(sortEmployees([...employees].reverse()).map(e=>e.position),POSITIONS);
  assert.deepEqual(sortEmployees([{id:'1',name:'Z',position:'ASISTANT MANAGER'},{id:'2',name:'A',position:'Executive'},{id:'3',name:'B',position:'TECHNICAL OFFICIER'},{id:'4',name:'C',position:'WORKER'}]).map(e=>e.id),['1','2','3','4']);
});
test('manual order is deterministic, retains new employees, and leaves saved input untouched',()=>{
  const employees=[{id:'1',name:'Z'},{id:'2',name:'A'},{id:'3',name:'B'},{id:'4',name:'C'}],order=['3','1'];
  assert.deepEqual(sortEmployees(employees,'manual',order).map(e=>e.id),['3','1','2','4']);
  assert.deepEqual(order,['3','1']);
  assert.deepEqual(sortEmployees(employees,'name',order).map(e=>e.id),['2','3','4','1']);
});
const state={settings:{team_schedules:{A:'normal'},schedule_groups:{
  'section:CONVERSION':{team_schedules:{A:'day',B:'night'},team_overtime:{A:true,B:false},rotation:{anchor_date:'2026-10-01',interval_days:7,schedule_ids:['day','night']}},
  'section:ROLL MAKING':{team_schedules:{A:'night'},team_overtime:{A:false},rotation:null},
  'line:MF':{team_schedules:{A:'day'},team_overtime:{A:false},rotation:null}
}},schedules:['normal','day','night','day-ot','night-ot'].map(id=>({id})),assignments:[]};
const person={id:'1',name:'Example',department:'PRODUCTION',line:'FC',team:'A',schedule_id:'normal'};
test('conversion rotation and OT are separate from Roll Making, with line overrides taking priority',()=>{
  assert.equal(employeeHours(person,state,'2026-10-09').id,'night-ot');
  assert.equal(employeeHours({...person,line:'ROLL MAKING'},state,'2026-10-09').id,'night');
  assert.equal(employeeHours({...person,line:'MF'},state,'2026-10-09').id,'day');
  assert.equal(employeeHours({...person,department:'OFFICE',office_department:'PRODUCTION'},state,'2026-10-09').id,'normal');
});
test('scoped date overrides stay in their section and employee exceptions take priority',()=>{
  const assignments=[{scope:'section:CONVERSION',team:'A',start_date:'2026-10-09',end_date:'2026-10-09',schedule_id:'normal'}];
  assert.equal(employeeHours(person,{...state,assignments},'2026-10-09').id,'normal');
  assert.equal(employeeHours({...person,line:'ROLL MAKING'},{...state,assignments},'2026-10-09').id,'night');
  assignments.push({scope:'line:FC',team:'A',start_date:'2026-10-09',end_date:'2026-10-09',schedule_id:'day'});
  assert.equal(employeeHours(person,{...state,assignments},'2026-10-09').id,'day');
  assignments.push({employee_id:'1',start_date:'2026-10-09',end_date:'2026-10-09',schedule_id:'night-ot'});
  assert.equal(employeeHours(person,{...state,assignments},'2026-10-09').id,'night-ot');
});
