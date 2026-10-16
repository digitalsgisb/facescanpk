import React,{useState} from 'react';
import {Sun,Moon,Clock3,Users,Settings2,Check,CalendarDays} from 'lucide-react';
import './control-centre.css';
import {employeeHours,malaysiaToday,teamHours} from './team-hours.js';

export function EmployeeHoursPreview({employee,state}){
  const result=employeeHours(employee,state);
  return <div className="hours-preview span-two" role="status"><Clock3 size={22}/><div><small>WORKING HOURS TODAY · {result.source}</small><strong>{result.schedule?`${result.schedule.name} · ${result.schedule.start} – ${result.schedule.end}`:'Working hours not assigned'}</strong>{result.schedule&&<span>{result.schedule.ot?'Overtime on':'Overtime off'}{result.schedule.end<=result.schedule.start?' · Ends next day':''}</span>}</div></div>;
}
export function ControlCentre({state,mutate,navigate,onEditSchedule,onAssignment}){
  const initial=state.settings,rotation=initial.rotation;
  const seed=team=>initial.team_schedules?.[team]||(['A','B'].includes(team)?rotation?.schedule_ids[team==='A'?0:1]:null)||'';
  const [teams,setTeams]=useState(()=>Object.fromEntries(['A','B','N'].map(team=>[team,seed(team).replace(/-ot$/,'')])));
  const [ot,setOt]=useState(()=>Object.fromEntries(['A','B','N'].map(team=>[team,initial.team_overtime?.[team]??seed(team).endsWith('-ot')])));
  const [automatic,setAutomatic]=useState(!!rotation),[anchor,setAnchor]=useState(rotation?.anchor_date||malaysiaToday()),[interval,setIntervalDays]=useState(rotation?.interval_days||7);
  const [error,setError]=useState(''),[saving,setSaving]=useState(false),[saved,setSaved]=useState(false);
  const draft={...initial,team_schedules:Object.fromEntries(Object.entries(teams).map(([team,id])=>[team,id||null])),team_overtime:ot,rotation:automatic?{anchor_date:anchor,interval_days:interval,schedule_ids:[teams.A,teams.B]}:null};
  function change(fn){fn();setSaved(false);}
  function choose(team,id){setTeams(previous=>({...previous,[team]:id}));if(!['day','night'].includes(id))setOt(previous=>({...previous,[team]:false}));}
  async function save(event){event.preventDefault();setError('');setSaving(true);try{
    if(automatic&&(!teams.A||!teams.B))throw new Error('Choose starting hours for both Team A and Team B before enabling rotation.');
    await mutate('/settings','PUT',{team_schedules:draft.team_schedules,team_overtime:ot,rotation:draft.rotation},'Team working hours saved');setSaved(true);
  }catch(e){setError(e.message);}finally{setSaving(false);}}
  return <div className="control-centre">
    <div className="control-shortcuts">{[['clock','Clock in / out','Individual and batch attendance',Clock3],['employees','Manage people','Teams, photos and employee details',Users],['settings','System settings','Kiosks, rules and backups',Settings2]].map(([page,title,detail,Icon])=><button key={page} className="control-shortcut" onClick={()=>navigate(page)}><Icon size={23}/><div><strong>{title}</strong><small>{detail}</small></div><span>↗</span></button>)}</div>
    <form className="team-setup" onSubmit={save}>
      <div className="control-section-title"><div><div className="eyebrow">TEAM WORKING HOURS</div><h2>Set each team once.</h2><p>Employees follow their team's hours automatically. Date overrides still take priority.</p></div><div className="segmented" role="group" aria-label="Team scheduling mode"><button type="button" aria-pressed={!automatic} onClick={()=>change(()=>setAutomatic(false))}>Fixed teams</button><button type="button" aria-pressed={automatic} onClick={()=>change(()=>setAutomatic(true))}>Automatic A/B swap</button></div></div>
      <div className="team-setup-grid">{['A','B','N'].map(team=>{
        const effective=teamHours(draft,team),schedule=state.schedules.find(s=>s.id===effective?.id);
        return <section key={team} className="team-setup-card"><header><span className="team-letter">{team}</span><div><h3>Team {team}</h3><small>{state.employees.filter(e=>e.active&&e.team===team).length} employees{automatic&&team!=='N'?' · Starting shift':''}</small></div></header><div className="shift-choices" role="group" aria-label={'Team '+team+' shift'}>{[['day','Day',Sun],['night','Night',Moon],['normal','Normal',Clock3]].map(([id,label,Icon])=><button type="button" key={id} aria-pressed={teams[team]===id} onClick={()=>change(()=>choose(team,id))}><Icon size={17}/>{label}</button>)}</div><label className="control-team-fallback">Or use<select aria-label={'Team '+team+' base schedule'} value={teams[team]} onChange={e=>change(()=>choose(team,e.target.value))}><option value="">Individual employee defaults</option>{state.schedules.filter(s=>!s.ot).map(s=><option key={s.id} value={s.id}>{s.name} · {s.start} – {s.end}</option>)}</select></label><label className={'ot-switch '+(ot[team]?'on':'')}><div><strong>Overtime</strong><small>{['day','night'].includes(teams[team])?(ot[team]?'OT ON':'OT OFF'):'Choose Day or Night for OT'}</small></div><input type="checkbox" role="switch" aria-label={'Team '+team+' overtime'} disabled={!['day','night'].includes(teams[team])} checked={ot[team]&&['day','night'].includes(teams[team])} onChange={e=>change(()=>setOt({...ot,[team]:e.target.checked}))}/></label><div className="team-time-preview"><small>{automatic&&team!=='N'?'TODAY’S HOURS':'WORKING HOURS'}</small><strong>{schedule?`${schedule.start} – ${schedule.end}`:'Employee defaults'}</strong><span>{schedule?.name||'Each person uses their individual schedule'}{schedule&&schedule.end<=schedule.start?' · Next day':''}</span></div></section>;
      })}</div>
      {automatic&&<div className="rotation-controls"><CalendarDays size={23}/><label>Rotation starts<input type="date" required value={anchor} onChange={e=>change(()=>setAnchor(e.target.value))} onInput={e=>change(()=>setAnchor(e.target.value))}/></label><label>Swap every (days)<input type="number" min="1" max="60" required value={interval} onChange={e=>change(()=>setIntervalDays(Number(e.target.value)))} onInput={e=>change(()=>setIntervalDays(Number(e.target.value)))}/></label><p>A and B swap their starting schedules at this interval. Each team's OT switch stays with that team.</p></div>}
      <div className="control-save"><p>New hours apply to future clock actions. Saved attendance keeps its original planned times.</p><button className="primary" disabled={saving}>{saving?'Saving…':saved?'Team hours saved':'Save team working hours'}<Check size={17}/></button></div>
      {error&&<div className="inline-error" role="alert">{error}</div>}
    </form>
    <section className="control-templates"><div className="control-section-title"><div><h2>Working-hour templates</h2><p>Edit the exact start and end times used by Day, Night and OT.</p></div><button className="secondary" onClick={onAssignment}>Date override</button></div><div className="control-template-grid">{state.schedules.map(schedule=><button key={schedule.id} onClick={()=>onEditSchedule(schedule)}><small>{schedule.ot?'OVERTIME':'STANDARD'}</small><strong>{schedule.name}</strong><span>{schedule.start} – {schedule.end}{schedule.end<=schedule.start?' +1 day':''}</span><em>Edit hours ↗</em></button>)}</div></section>
  </div>;
}
