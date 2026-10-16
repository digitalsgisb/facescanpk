import React,{useEffect,useMemo,useRef,useState} from 'react';
import {Clock3,LockKeyhole,Search,ShieldCheck,Pencil} from 'lucide-react';
import './clock-controls.css';
import {productionSection} from './organisation.js';

const requestId=()=>Array.from(crypto.getRandomValues(new Uint8Array(16)),byte=>byte.toString(16).padStart(2,'0')).join('');
function Face({employee}){
  const [failed,setFailed]=useState(false);
  useEffect(()=>setFailed(false),[employee.photo_url]);
  return <span className="clock-face">{employee.photo_url&&!failed?<img src={employee.photo_url} alt="" onError={()=>setFailed(true)}/>:employee.name.split(' ').filter(Boolean).slice(0,2).map(part=>part[0]).join('')}</span>;
}
export function ClockControls({employees,api,unlocked,onUnlocked,onRefresh,onEdit,initialId}){
  const [password,setPassword]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[results,setResults]=useState([]);
  const [query,setQuery]=useState(''),[department,setDepartment]=useState('all'),[team,setTeam]=useState('all');
  const [section,setSection]=useState('all');
  const [selected,setSelected]=useState(()=>new Set(initialId?[initialId]:[]));
  const pending=useRef(null),saving=useRef(false);
  const shown=useMemo(()=>employees.filter(e=>(department==='all'||(e.department||'Unassigned')===department)&&(section==='all'||productionSection(e)===section)&&(team==='all'||e.team===team)&&(!query||[e.name,e.nickname,e.id,e.department,e.line,e.office_department].some(value=>value?.toLowerCase().includes(query.toLowerCase())))),[employees,query,department,team,section]);
  const ids=employees.filter(e=>selected.has(e.id)).map(e=>e.id);
  useEffect(()=>{api('/clock-access').then(data=>onUnlocked(data.unlocked)).catch(()=>onUnlocked(false));},[]);
  async function unlock(event){
    event.preventDefault();if(saving.current)return;saving.current=true;setBusy(true);setError('');
    try{await api('/auth/unlock-attendance','POST',{password});setPassword('');onUnlocked(true);}catch(e){setError(e.message);}finally{setBusy(false);saving.current=false;}
  }
  async function apply(action,employeeIds){
    if(saving.current||!employeeIds.length)return;saving.current=true;setBusy(true);setError('');setResults([]);
    const key=action+':'+[...employeeIds].sort().join(',');
    if(pending.current?.key!==key)pending.current={key,id:requestId()};
    try{
      const response=await api('/clock/batch','POST',{employee_ids:employeeIds,action,batch_id:pending.current.id});
      setResults(response.results);pending.current=null;
      const completed=new Set(response.results.filter(result=>['saved','skipped'].includes(result.status)).map(result=>result.employee_id));
      setSelected(previous=>new Set([...previous].filter(id=>!completed.has(id))));
      await onRefresh();
    }catch(e){setError(e.message);if(e.status===403)onUnlocked(false);}
    finally{setBusy(false);saving.current=false;}
  }
  function filter(setter,value){setter(value);setSelected(new Set());}
  const saved=results.filter(result=>result.status==='saved').length;
  return <section className="clock-admin">
    <div className="clock-access"><ShieldCheck size={26}/><div><strong>Administrator attendance controls</strong><p>Clock people in or out individually, or select several people for a batch. The TV board stays view only.</p></div>{unlocked&&<button className="secondary" disabled={busy} onClick={async()=>{try{await api('/clock-access','DELETE');onUnlocked(false);}catch(e){setError(e.message);}}}><LockKeyhole size={16}/>Lock controls</button>}</div>
    {!unlocked?<form className="clock-unlock card" onSubmit={unlock}><LockKeyhole size={30}/><h2>Unlock clock controls</h2><p>Enter the administrator password. Controls lock again after 30 minutes; the TV stays signed in.</p><label>Administrator password<input autoComplete="current-password" type="password" value={password} onChange={event=>setPassword(event.target.value)} required/></label><button className="primary" disabled={busy}>{busy?'Checking…':'Unlock admin controls'}</button></form>:<>
      <div className="clock-filters"><div className="search"><Search size={17}/><input aria-label="Find employee to clock in or out" placeholder="Search name, ID or line…" value={query} onChange={event=>filter(setQuery,event.target.value)}/></div><select aria-label="Clock controls department" value={department} onChange={event=>filter(setDepartment,event.target.value)}><option value="all">All departments</option>{[...new Set(employees.map(e=>e.department||'Unassigned'))].sort().map(name=><option key={name}>{name}</option>)}</select><select aria-label="Clock controls production section" value={section} onChange={event=>filter(setSection,event.target.value)}><option value="all">All sections</option><option value="CONVERSION">Conversion</option><option value="ROLL MAKING">Roll Making</option></select><select aria-label="Clock controls team" value={team} onChange={event=>filter(setTeam,event.target.value)}><option value="all">All teams</option>{[...new Set(employees.map(e=>e.team).filter(Boolean))].sort().map(name=><option key={name} value={name}>Team {name}</option>)}</select></div>
      <div className="clock-batch-bar"><label><input type="checkbox" checked={!!shown.length&&shown.every(e=>selected.has(e.id))} disabled={!shown.length||busy} onChange={event=>{const checked=event.target.checked;setSelected(previous=>{const next=new Set(previous);shown.forEach(e=>checked?next.add(e.id):next.delete(e.id));return next;});}}/>Select shown ({shown.length})</label><strong>{ids.length} selected</strong><button className="clock-in-action" disabled={busy||!ids.length} onClick={()=>apply('IN',ids)}><Clock3 size={17}/>Clock in selected</button><button className="clock-out-action" disabled={busy||!ids.length} onClick={()=>apply('OUT',ids)}><Clock3 size={17}/>Clock out selected</button><button className="text-button" disabled={busy||!ids.length} onClick={()=>setSelected(new Set())}>Clear</button></div>
      <p className="clock-hint">Clock in turns the TV card green. Clock out turns it red. People already in the requested state are skipped.</p>
      <div className="clock-person-list">{shown.map(employee=><article className="clock-person" key={employee.id}><input type="checkbox" aria-label={'Select '+employee.name} checked={selected.has(employee.id)} disabled={busy} onChange={event=>{const checked=event.target.checked;setSelected(previous=>{const next=new Set(previous);checked?next.add(employee.id):next.delete(employee.id);return next;});}}/><Face employee={employee}/><div className="clock-person-name"><strong>{employee.nickname||employee.name}</strong><small>{employee.id} · {employee.department||'Unassigned'}{employee.line?' · '+employee.line:''}{employee.team?' · Team '+employee.team:''}</small></div><span className={'staff-status '+(employee.status==='IN'?'in':'out')}>{employee.status}</span><button className={employee.status==='IN'?'clock-out-action':'clock-in-action'} disabled={busy} aria-label={(employee.status==='IN'?'Clock out ':'Clock in ')+employee.name} onClick={()=>apply(employee.status==='IN'?'OUT':'IN',[employee.id])}>{employee.status==='IN'?'Clock out':'Clock in'}</button><button className="secondary" disabled={busy} aria-label={'Edit attendance for '+employee.name} onClick={()=>onEdit(employee)}><Pencil size={15}/>Edit attendance</button></article>)}{!shown.length&&<p className="empty">No matching employees.</p>}</div>
    </>}
    {error&&<div className="inline-error" role="alert">{error}</div>}
    {!!results.length&&<div className="clock-results" role="status"><strong>{saved} saved · {results.filter(result=>result.status==='skipped').length} skipped · {results.filter(result=>['error','review'].includes(result.status)).length} need attention</strong>{results.filter(result=>result.status!=='saved').map(result=><p key={result.employee_id}>{employees.find(e=>e.id===result.employee_id)?.name||result.employee_id}: {result.message}</p>)}</div>}
  </section>;
}
