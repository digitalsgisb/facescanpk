import React,{useEffect,useState} from 'react';
import {ControlCentre} from './control-centre.jsx';

export function PlantShiftControls({state,api,onRefresh,navigate}){
  const fixed=state.plant||'',plants=[...new Set(['PORT KLANG','SENDAYAN',...state.employees.map(e=>e.base).filter(Boolean)])];
  const [base,setBase]=useState(fixed||'PORT KLANG'),[data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[version,setVersion]=useState(0),[edit,setEdit]=useState(null);
  useEffect(()=>{let active=true;setData(null);setEdit(null);setError('');api('/plant-controls?base='+encodeURIComponent(base)).then(d=>{if(active)setData(d)}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[base]);
  async function save(path,method,patch){
    setBusy(true);setError('');
    try{const result=await api('/plant-controls','PUT',{base,...patch});const next=await api('/plant-controls?base='+encodeURIComponent(base));setData(next);setVersion(v=>v+1);await onRefresh();return result}
    catch(e){setError(e.message);throw e}finally{setBusy(false)}
  }
  return <>
    <section className="card form-pad compact-controls"><label>Plant{fixed?<strong>{fixed}</strong>:<select aria-label="Shift control plant" value={base} disabled={busy} onChange={e=>setBase(e.target.value)}>{plants.map(p=><option key={p}>{p}</option>)}</select>}</label></section>
    {error&&<p className="inline-error" role="alert">{error}</p>}
    {data&&<ControlCentre key={base+version} state={{...state,plant:base,employees:state.employees.filter(e=>e.base===base),settings:data.settings,schedules:data.schedules}} mutate={save} navigate={navigate} plantMode teamNames={data.teams} onEditSchedule={s=>setEdit({...s})}/>}
    {edit&&<section className="card form-pad"><form className="form-grid" onSubmit={async e=>{e.preventDefault();try{await save('', '',{schedules:{...data.template_overrides,[edit.id]:{name:edit.name,start:edit.start,end:edit.end,ot:edit.ot}}});setEdit(null)}catch{}}}>
      <strong>{base} · {edit.name}</strong><label>Name<input required value={edit.name} onChange={e=>setEdit({...edit,name:e.target.value})}/></label>
      <label>Start<input required type="time" value={edit.start} onChange={e=>setEdit({...edit,start:e.target.value})}/></label><label>End<input required type="time" value={edit.end} onChange={e=>setEdit({...edit,end:e.target.value})}/></label>
      <button className="primary" disabled={busy}>Save times</button><button type="button" className="secondary" disabled={busy} onClick={()=>setEdit(null)}>Cancel</button>
    </form></section>}
  </>;
}

export function AutomaticClockout({api}){
  const [config,setConfig]=useState(null),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  useEffect(()=>{api('/automatic-clockout').then(setConfig).catch(e=>setMessage(e.message))},[]);
  return <details className="card form-pad daily-clockout"><summary>Daily clock-out · All plants</summary>
    {config&&<form className="form-grid" onSubmit={async e=>{e.preventDefault();setBusy(true);setMessage('');try{await api('/automatic-clockout','PUT',{enabled:config.enabled,clock_time:config.clock_time});setConfig(await api('/automatic-clockout'));setMessage('Saved. Runs on the AI PC.')}catch(error){setMessage(error.message)}finally{setBusy(false)}}}>
      <label className="checkbox-label"><input type="checkbox" checked={config.enabled} disabled={busy} onChange={e=>setConfig({...config,enabled:e.target.checked})}/>Enabled</label>
      <label>Malaysia time<input type="time" required value={config.clock_time} disabled={busy} onChange={e=>setConfig({...config,clock_time:e.target.value})}/></label>
      <p>Closes all open sessions across every plant. Backs up first. Later clock-ins stay open.</p>
      <button className="primary" disabled={busy}>{busy?'Saving…':'Save daily clock-out'}</button>
      <button className="secondary" type="button" disabled={busy} onClick={async()=>{setBusy(true);try{const latest=await api('/automatic-clockout');setConfig(c=>({...c,last_run:latest.last_run}))}catch(error){setMessage(error.message)}finally{setBusy(false)}}}>Refresh status</button>
      {config.last_run&&<small>Last run: {config.last_run.run_date} · {config.last_run.closed} clocked out.</small>}
    </form>}{message&&<p role="status">{message}</p>}
  </details>;
}
