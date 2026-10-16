export const malaysiaToday=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kuala_Lumpur',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
export function teamHours(settings,team,date=malaysiaToday()){
  const rotation=settings.rotation;
  let id=settings.team_schedules?.[team]||null,source='Team '+team+' default';
  if(rotation&&['A','B'].includes(team)&&date>=rotation.anchor_date){
    const days=Math.floor((Date.parse(date+'T00:00:00Z')-Date.parse(rotation.anchor_date+'T00:00:00Z'))/86400000);
    let index=Math.floor(days/rotation.interval_days)%2;if(team==='B')index=1-index;
    id=rotation.schedule_ids[index];source='Team '+team+' rotation';
  }
  if(!id)return null;
  const base=id.replace(/-ot$/,'');
  if(['day','night'].includes(base)&&Object.hasOwn(settings.team_overtime||{},team))id=base+(settings.team_overtime[team]?'-ot':'');
  return {id,source};
}
export function employeeHours(employee,state,date=malaysiaToday()){
  const assignments=(state.assignments||[]).filter(a=>a.start_date<=date&&a.end_date>=date).sort((a,b)=>b.start_date.localeCompare(a.start_date));
  const personal=assignments.find(a=>a.employee_id===employee.id),team=assignments.find(a=>a.team===employee.team);
  const effective=personal?{id:personal.schedule_id,source:'Employee date override'}:team?{id:team.schedule_id,source:'Team date override'}:teamHours(state.settings,employee.team,date)||{id:employee.schedule_id,source:'Individual fallback'};
  return {...effective,schedule:state.schedules.find(s=>s.id===effective.id)||null};
}
