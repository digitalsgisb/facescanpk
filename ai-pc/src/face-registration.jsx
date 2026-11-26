import React,{useState} from 'react';
import {Search,Copy,ArrowDownToLine} from 'lucide-react';

const STATES=[
  ['pending','Not registered','Not found on this plant’s reporting kiosks. Ask these people to register at a kiosk.'],
  ['registered','Registered','Found on at least one reporting kiosk.'],
  ['unknown','No report','No recent kiosk report. Check the kiosk is switched on and connected.'],
];
const stateOf=e=>e.face_registration||'unknown';

export default function FaceRegistration({employees,exportCsv}){
  const active=employees.filter(e=>e.active);
  // Open on the first list that has people in it, starting with the ones to chase.
  const [status,setStatus]=useState(()=>['pending','unknown','registered'].find(key=>active.some(e=>stateOf(e)===key))||'pending'),[search,setSearch]=useState(''),[message,setMessage]=useState('');
  const count=key=>active.filter(e=>stateOf(e)===key).length;
  const q=search.toLowerCase();
  const rows=active.filter(e=>stateOf(e)===status&&[e.id,e.name,e.nickname,e.department,e.base,e.line,e.team].some(v=>String(v||'').toLowerCase().includes(q)));
  const [,label,help]=STATES.find(([key])=>key===status);
  const copy=async()=>{
    const text=(status==='pending'?'Please register your face at the attendance kiosk:\n':'Face registration: '+label+'\n')+
      rows.map(e=>`${e.id} ${e.name}${e.base?', '+e.base:''}${e.department?', '+e.department:''}${e.line?', '+e.line:''}`).join('\n');
    try{await navigator.clipboard.writeText(text);setMessage(`${rows.length} names copied. Paste them into your message to staff.`)}
    catch{setMessage('This browser blocked copying. Use Export CSV instead.')}
  };
  const total=active.length||1;
  return <section className="card face-page">
    <div className="face-meter" aria-hidden="true">{STATES.map(([key])=><i key={key} className={'is-'+key} style={{flexGrow:count(key)/total}}/>)}</div>
    <div className="face-tabs" role="tablist" aria-label="Registration status">{STATES.map(([key,text])=><button key={key} role="tab" aria-selected={status===key} className={'face-tab is-'+key+(status===key?' is-current':'')} onClick={()=>{setStatus(key);setMessage('')}}><strong>{count(key)}</strong><span>{text}</span></button>)}</div>
    <p className="face-help">{help} Kiosk reports refresh about every 20 seconds. Profile photos are separate.</p>
    <div className="face-toolbar">
      <label className="people-search"><Search size={17} aria-hidden="true"/><input aria-label="Search this list" placeholder="Search name, ID, plant, department or line" value={search} onChange={e=>setSearch(e.target.value)}/></label>
      <button className="secondary" disabled={!rows.length} onClick={copy}><Copy size={15}/>{status==='pending'?'Copy reminder list':'Copy list'}</button>
      <button className="secondary" disabled={!rows.length} onClick={()=>exportCsv(rows.map(e=>({ID:e.id,Name:e.name,Plant:e.base||'',Department:e.department,Line:e.line,Team:e.team,FaceRegistration:label,LastReport:e.face_reported_at||''})),'face-registration-'+status+'.csv')}><ArrowDownToLine size={15}/>Export CSV</button>
    </div>
    {message&&<p className="face-message" role="status">{message}</p>}
    {rows.length?<div className="table-wrap"><table><thead><tr><th>ID</th><th>Name</th><th>Plant and department</th><th>Line and team</th><th>Last kiosk report</th></tr></thead><tbody>{rows.map(e=><tr key={e.id}><td>{e.id}</td><td>{e.name}</td><td>{[e.base,e.department].filter(Boolean).join(', ')}</td><td>{[e.line,e.team&&'Team '+e.team].filter(Boolean).join(', ')||'—'}</td><td>{e.face_reported_at?new Date(e.face_reported_at).toLocaleString('en-MY',{timeZone:'Asia/Kuala_Lumpur'}):'Never'}</td></tr>)}</tbody></table></div>
      :<p className="face-empty">{search?'No one in this list matches your search.':status==='pending'?(count('unknown')?`No one is marked as not registered, but ${count('unknown')} have no kiosk report yet.`:'Everyone has registered.'):'No one in this list.'}</p>}
  </section>;
}
