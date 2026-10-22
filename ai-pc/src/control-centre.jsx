import React,{useState} from 'react';
import {Sun,Moon,Clock3,Users,Settings2,Check,CalendarDays} from 'lucide-react';
import './control-centre.css';
import {employeeHours,malaysiaToday,teamHours} from './team-hours.js';
import {POSITION_HIERARCHY,scopeOptions,scheduleScopes,employeeGroup,sortEmployees} from './organisation.js';

export function EmployeeHoursPreview({employee,state}){
  const result=employeeHours(employee,state);
  return <div className="hours-preview span-two" role="status"><Clock3 size={22}/><div><small>WORKING HOURS TODAY · {result.source}</small><strong>{result.schedule?`${result.schedule.name} · ${result.schedule.start} – ${result.schedule.end}`:'Working hours not assigned'}</strong>{result.schedule&&<span>{result.schedule.ot?'Overtime on':'Overtime off'}{result.schedule.end<=result.schedule.start?' · Ends next day':''}</span>}</div></div>;
}
export function ControlCentre(props){
  const {state,mutate}=props;
  const [scope,setScope]=useState(''),[reset,setReset]=useState(0),[error,setError]=useState(''),[removing,setRemoving]=useState(false);
  const groups=state.settings.schedule_groups||{},options=scopeOptions(state.employees).map(([key,label])=>[key,key?label:'Plant defaults']);
  const representative=state.employees.find(e=>scheduleScopes(e).includes(scope));
  const parents=scope&&representative?scheduleScopes(representative).slice(scheduleScopes(representative).indexOf(scope)+1):[];
  const inherited=parents.find(key=>groups[key]);
  const config=scope?(groups[scope]||groups[inherited]||state.settings):state.settings;
  const employees=scope?state.employees.filter(e=>scheduleScopes(e).includes(scope)):state.employees;
  async function save(path,method,data,message){
    if(!scope)return mutate(path,method,data,message);
    return mutate(path,method,{schedule_groups:{...groups,[scope]:data}},'Working hours saved for '+options.find(([key])=>key===scope)?.[1]);
  }
  async function inherit(){setRemoving(true);setError('');try{const next={...groups};delete next[scope];await mutate('/settings','PUT',{schedule_groups:next},'Inherited working hours restored');setReset(value=>value+1);}catch(e){setError(e.message)}finally{setRemoving(false)}}
  return <><details className="schedule-scope card"><summary>Department overrides</summary><div><h2>Shift group</h2><p>Choose a section or department.</p></div><label>Department, section or line<select value={scope} onChange={e=>{setScope(e.target.value);setError('')}}>{options.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label><div className="scope-status"><strong>{scope?(groups[scope]?'Separate hours configured':'Inheriting '+(inherited?options.find(([key])=>key===inherited)?.[1]:'company defaults')):'Plant defaults'}</strong><small>{scope?(groups[scope]?'Group shifts.':'Save separate group shifts.'):'Save to apply.'}</small>{scope&&groups[scope]&&<button className="secondary" disabled={removing} onClick={inherit}>Use inherited hours</button>}</div>{error&&<p role="alert" className="inline-error">{error}</p>}</details><TeamSetup key={scope+reset} {...props} state={{...state,employees,settings:config}} mutate={save} onAssignment={()=>props.onAssignment(scope)} scopeLabel={options.find(([key])=>key===scope)?.[1]}/>{!props.plantMode&&<EmployeeOrdering state={state} mutate={mutate}/>}</>;
}
function EmployeeOrdering({state,mutate}){
  const [mode,setMode]=useState(state.settings.employee_sort||'position'),[order,setOrder]=useState(()=>sortEmployees(state.employees,state.settings.employee_order?.length?'manual':'position',state.settings.employee_order||[]).map(e=>e.id)),[group,setGroup]=useState('OFFICE'),[error,setError]=useState(''),[saving,setSaving]=useState(false),[saved,setSaved]=useState(false);
  const allGroups=[...new Set(state.employees.filter(e=>e.active).map(employeeGroup))].sort();
  const selected=allGroups.includes(group)?group:allGroups[0];
  const people=sortEmployees(state.employees.filter(e=>e.active&&employeeGroup(e)===selected),'manual',order);
  function move(index,direction){const ids=sortEmployees(state.employees,'manual',order).map(e=>e.id),a=ids.indexOf(people[index].id),b=ids.indexOf(people[index+direction].id);[ids[a],ids[b]]=[ids[b],ids[a]];setOrder(ids);setMode('manual');setSaved(false)}
  async function save(event){event.preventDefault();setSaving(true);setError('');try{await mutate('/settings','PUT',{employee_sort:mode,employee_order:sortEmployees(state.employees,'manual',order).map(e=>e.id)},'Employee display order saved');setSaved(true)}catch(e){setError(e.message)}finally{setSaving(false)}}
  return <form className="team-setup employee-ordering" onSubmit={save}><div className="control-section-title"><div><h2>Employee display order</h2><p>Applies to the employee directory. The TV board automatically sorts by position within each group and team.</p></div><label>Sort by<select value={mode} onChange={e=>{setMode(e.target.value);setSaved(false)}}><option value="position">Position seniority</option><option value="manual">Manual order</option><option value="name">Name A–Z</option></select></label></div><p className="position-hierarchy">{POSITION_HIERARCHY.map(role=>role.toLowerCase().replace(/\b\w/g,c=>c.toUpperCase())).join(' → ')}</p><label className="order-group">Arrange group<select value={selected||''} onChange={e=>setGroup(e.target.value)}>{allGroups.map(name=><option key={name}>{name}</option>)}</select></label><p className="field-help">Use the arrows to set manual order. Choosing position seniority preserves your manual list for later.</p><div className="manual-order-list">{people.map((employee,index)=><div key={employee.id}><span className="order-number">{index+1}</span><div><strong>{employee.nickname||employee.name}</strong><small>{employee.position||'Position unassigned'}{employee.office_department?' · '+employee.office_department:''}{employee.team?' · Team '+employee.team:''}</small></div><button type="button" className="secondary" disabled={!index} aria-label={'Move '+employee.name+' up'} onClick={()=>move(index,-1)}>↑</button><button type="button" className="secondary" disabled={index===people.length-1} aria-label={'Move '+employee.name+' down'} onClick={()=>move(index,1)}>↓</button></div>)}</div><div className="control-save">{error&&<p className="inline-error" role="alert">{error}</p>}<button className="primary" disabled={saving}>{saving?'Saving…':saved?'Display order saved':'Save display order'}<Check size={17}/></button></div></form>;
}
function TeamSetup({state,mutate,navigate,onEditSchedule,onAssignment,scopeLabel,plantMode=false,teamNames=['A','B','N']}){
  const initial=state.settings,rotation=initial.rotation,pair=teamNames.slice(0,2);
  const seed=team=>initial.team_schedules?.[team]||(pair.includes(team)?rotation?.schedule_ids[team===pair[0]?0:1]:null)||'';
  const [teams,setTeams]=useState(()=>Object.fromEntries(teamNames.map(team=>[team,seed(team).replace(/-ot$/,'')])));
  const [ot,setOt]=useState(()=>Object.fromEntries(teamNames.map(team=>[team,initial.team_overtime?.[team]??seed(team).endsWith('-ot')])));
  const [automatic,setAutomatic]=useState(!!rotation),[anchor,setAnchor]=useState(rotation?.anchor_date||malaysiaToday()),[interval,setIntervalDays]=useState(rotation?.interval_days||7);
  const [error,setError]=useState(''),[saving,setSaving]=useState(false),[saved,setSaved]=useState(false);
  const draft={...initial,team_schedules:Object.fromEntries(Object.entries(teams).map(([team,id])=>[team,id||null])),team_overtime:ot,rotation:automatic?{anchor_date:anchor,interval_days:interval,schedule_ids:pair.map(team=>teams[team]),teams:pair}:null};
  function change(fn){fn();setSaved(false);}
  function choose(team,id){setTeams(previous=>({...previous,[team]:id}));if(!['day','night'].includes(id))setOt(previous=>({...previous,[team]:false}));}
  async function save(event){event.preventDefault();setError('');setSaving(true);try{
    if(automatic&&pair.some(team=>!teams[team]))throw new Error('Choose hours for both rotating teams.');
    await mutate('/settings','PUT',{team_schedules:draft.team_schedules,team_overtime:ot,rotation:draft.rotation},'Team working hours saved');setSaved(true);
  }catch(e){setError(e.message);}finally{setSaving(false);}}
  return <div className="control-centre">
    {!plantMode&&<div className="control-shortcuts">{[['clock','Clock in / out','Individual and batch attendance',Clock3],['employees','Manage people','Teams, photos and employee details',Users],['settings','System settings','Kiosks, rules and backups',Settings2]].map(([page,title,detail,Icon])=><button key={page} className="control-shortcut" onClick={()=>navigate(page)}><Icon size={23}/><div><strong>{title}</strong><small>{detail}</small></div><span>↗</span></button>)}</div>}
    <form className="team-setup" onSubmit={save}>
      <div className="control-section-title"><div><div className="eyebrow">TEAM WORKING HOURS · {scopeLabel}</div><h2>Team shifts</h2><p>Set hours and overtime.</p></div><div className="segmented" role="group" aria-label="Team scheduling mode"><button type="button" aria-pressed={!automatic} onClick={()=>change(()=>setAutomatic(false))}>Fixed teams</button><button type="button" aria-pressed={automatic} onClick={()=>change(()=>setAutomatic(true))}>Rotate {pair.join("/")}</button></div></div>
      <div className="team-setup-grid">{teamNames.map(team=>{
        const effective=teamHours(draft,team),schedule=state.schedules.find(s=>s.id===effective?.id);
        return <section key={team} className="team-setup-card"><header><span className="team-letter">{team}</span><div><h3>Team {team}</h3><small>{state.employees.filter(e=>e.active&&e.team===team).length} employees{automatic&&team!=='N'?' · Starting shift':''}</small></div></header><div className="shift-choices" role="group" aria-label={'Team '+team+' shift'}>{[['day','Day',Sun],['night','Night',Moon],['normal','Normal',Clock3]].map(([id,label,Icon])=><button type="button" key={id} aria-pressed={teams[team]===id} onClick={()=>change(()=>choose(team,id))}><Icon size={17}/>{label}</button>)}</div><label className="control-team-fallback">Or use<select aria-label={'Team '+team+' base schedule'} value={teams[team]} onChange={e=>change(()=>choose(team,e.target.value))}><option value="">Individual employee defaults</option>{state.schedules.filter(s=>!s.ot).map(s=><option key={s.id} value={s.id}>{s.name} · {s.start} – {s.end}</option>)}</select></label><label className={'ot-switch '+(ot[team]?'on':'')}><div><strong>Overtime</strong><small>{['day','night'].includes(teams[team])?(ot[team]?'OT ON':'OT OFF'):'Choose Day or Night for OT'}</small></div><input type="checkbox" role="switch" aria-label={'Team '+team+' overtime'} disabled={!['day','night'].includes(teams[team])} checked={ot[team]&&['day','night'].includes(teams[team])} onChange={e=>change(()=>setOt({...ot,[team]:e.target.checked}))}/></label><div className="team-time-preview"><small>{automatic&&team!=='N'?'TODAY’S HOURS':'WORKING HOURS'}</small><strong>{schedule?`${schedule.start} – ${schedule.end}`:'Employee defaults'}</strong><span>{schedule?.name||'Each person uses their individual schedule'}{schedule&&schedule.end<=schedule.start?' · Next day':''}</span></div></section>;
      })}</div>
      {automatic&&<div className="rotation-controls"><CalendarDays size={23}/><label>Rotation starts<input type="date" required value={anchor} onChange={e=>change(()=>setAnchor(e.target.value))} onInput={e=>change(()=>setAnchor(e.target.value))}/></label><label>Swap every (days)<input type="number" min="1" max="60" required value={interval} onChange={e=>change(()=>setIntervalDays(Number(e.target.value)))} onInput={e=>change(()=>setIntervalDays(Number(e.target.value)))}/></label><p>{pair.join(" and ")} swap at this interval. OT stays with each team.</p></div>}
      <div className="control-save"><p>Applies to future attendance.</p><button className="primary" disabled={saving}>{saving?'Saving…':saved?'Team hours saved':'Save shifts'}<Check size={17}/></button></div>
      {error&&<div className="inline-error" role="alert">{error}</div>}
    </form>
    <details className="control-templates card"><summary>Shift times</summary><div className="control-section-title"><div><h2>Shift times</h2><p>Edit this plant’s times.</p></div>{!plantMode&&<button className="secondary" onClick={onAssignment}>Date override</button>}</div><div className="control-template-grid">{state.schedules.map(schedule=><button key={schedule.id} onClick={()=>onEditSchedule(schedule)}><small>{schedule.ot?'OVERTIME':'STANDARD'}</small><strong>{schedule.name}</strong><span>{schedule.start} – {schedule.end}{schedule.end<=schedule.start?' +1 day':''}</span><em>Edit hours ↗</em></button>)}</div></details>
  </div>;
}
