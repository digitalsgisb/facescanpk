import {scheduleScopes} from './organisation.js';
export const malaysiaToday=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kuala_Lumpur',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
export function teamHours(settings,team,date=malaysiaToday()){
  const rotation=settings.rotation,pair=rotation?.teams||['A','B'];
  let id=settings.team_schedules?.[team]||null,source='Team '+team+' default';
  if(rotation&&pair.includes(team)&&date>=rotation.anchor_date){
    const days=Math.floor((Date.parse(date+'T00:00:00Z')-Date.parse(rotation.anchor_date+'T00:00:00Z'))/86400000);
    let index=Math.floor(days/rotation.interval_days)%2;if(team===pair[1])index=1-index;
    id=rotation.schedule_ids[index];source='Team '+team+' rotation';
  }
  if(!id)return null;
  const base=id.replace(/-ot$/,'');
  if(['day','night'].includes(base)&&Object.hasOwn(settings.team_overtime||{},team))id=base+(settings.team_overtime[team]?'-ot':'');
  return {id,source};
}
export function employeeHours(employee,state,date=malaysiaToday()){
  const plantConfig=state.plant_controls?.[employee.base]||state.settings;
  const scopes=scheduleScopes(employee),scope=scopes.find(key=>Object.hasOwn(plantConfig.schedule_groups||{},key));
  const settings=scope?plantConfig.schedule_groups[scope]:plantConfig;
  const assignments=(state.assignments||[]).filter(a=>a.start_date<=date&&a.end_date>=date).sort((a,b)=>b.start_date.localeCompare(a.start_date));
  const personal=assignments.find(a=>a.employee_id===employee.id),team=[...scopes,''].map(key=>assignments.find(a=>!a.employee_id&&a.team===employee.team&&(a.scope||'')===key)).find(Boolean);
  const hours=teamHours(settings,employee.team,date);
  const effective=personal?{id:personal.schedule_id,source:'Employee date override'}:team?{id:team.schedule_id,source:'Team date override'+(team.scope?' · '+team.scope.split(':').slice(1).join(':'):' · Company-wide')}:hours?{...hours,source:(scope?scope.split(':').slice(1).join(':')+' · ':'Company · ')+hours.source}:{id:employee.schedule_id,source:'Individual fallback'};
  return {...effective,schedule:(state.plant_templates?.[employee.base]||state.schedules).find(s=>s.id===effective.id)||null};
}
