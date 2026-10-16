import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readJson,issueDetails,sessionIssues,issueLogDates} from './attention.js';

test('attendance issues explain each flag and count a stale session flag once',()=>{
  const issues=sessionIssues({flags:'["late_arrival","early_departure","stale_open_session"]',stale_session:true});
  assert.deepEqual(issues.map(issue=>issue.code),['late_arrival','early_departure','stale_open_session']);
  assert.equal(issues[0].title,'Late arrival');
  assert.match(issues[1].detail,/clocked out/);
});
test('old open sessions are actionable even without stored flags',()=>{
  assert.equal(sessionIssues({flags:'[]',stale_session:true})[0].code,'stale_open_session');
  assert.deepEqual(sessionIssues({flags:'[]',stale_session:false}),[]);
  assert.equal(issueDetails(['schedule_unassigned'])[0].title,'Working hours missing');
});
test('issue helpers tolerate missing JSON and preserve unknown flags for review',()=>{
  assert.deepEqual(readJson('invalid',{}),{});
  assert.deepEqual(sessionIssues({flags:null}),[]);
  assert.equal(issueDetails(['custom_flag'])[0].title,'custom flag');
});
test('attendance links select the exact work date and scan links include the previous night shift',()=>{
  assert.deepEqual(issueLogDates({work_date:'2026-10-09'},'attendance'),{from:'2026-10-09',to:'2026-10-09'});
  assert.deepEqual(issueLogDates({occurred_at:'2026-10-09T17:00:00Z',result:'{}'},'scans'),{from:'2026-10-09',to:'2026-10-10'});
  assert.deepEqual(issueLogDates({occurred_at:'2026-10-10T08:00:00+08:00',result:'{"work_date":"2026-10-09"}'},'scans'),{from:'2026-10-08',to:'2026-10-09'});
});
