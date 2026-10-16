export function readJson(value,fallback){try{return typeof value==='string'?JSON.parse(value):value??fallback}catch{return fallback}}
const issues={
  schedule_unassigned:['Working hours missing','No working hours were assigned when this attendance was recorded.'],
  outside_scheduled_hours:['Outside working hours','The clock action fell outside the allowed shift window.'],
  late_arrival:['Late arrival','The employee clocked in after the late-arrival grace period.'],
  early_departure:['Early departure','The employee clocked out before the allowed departure time.'],
  stale_open_session:['Clock-out needs checking','An earlier clock-in is still open beyond the review threshold.'],
  out_of_order_scan:['Older scan received','This scan arrived before an attendance event that was already saved.'],
};
export function issueDetails(flags){return [...new Set(Array.isArray(flags)?flags:[])].map(code=>({code,title:issues[code]?.[0]||code.replaceAll('_',' '),detail:issues[code]?.[1]||'Review this attendance flag and record your decision.'}))}
export function sessionIssues(session){
  const flags=readJson(session.flags,[]);
  return issueDetails([...(Array.isArray(flags)?flags:[]),...(session.stale_session?['stale_open_session']:[])]);
}
export function issueLogDates(item,category){
  if(category==='attendance')return {from:item.work_date,to:item.work_date};
  const result=readJson(item.result,{}),date=result.work_date||new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kuala_Lumpur',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(item.occurred_at));
  // Include the previous work date because a scan after midnight may close a night shift.
  return {from:new Date(Date.parse(date+'T00:00:00Z')-86400000).toISOString().slice(0,10),to:date};
}
