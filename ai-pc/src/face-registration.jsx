import React,{useState} from 'react';

export default function FaceRegistration({employees,exportCsv}){
  const [status,setStatus]=useState('pending'),[search,setSearch]=useState(''),[message,setMessage]=useState('');
  const active=employees.filter(e=>e.active);
  const rows=active.filter(e=>(e.face_registration||'unknown')===status &&
    [e.id,e.name,e.nickname,e.department,e.base,e.line,e.team].some(v=>String(v||'').toLowerCase().includes(search.toLowerCase())));
  const label={pending:'Pending registration',registered:'Registered',unknown:'Status unknown'};
  const copy=async()=>{
    const text=(status==='pending'?'Please register your face at the attendance kiosk:\n':'Face registration — '+label[status]+'\n')+
      rows.map(e=>`${e.id} — ${e.name}${e.base?' · '+e.base:''}${e.department?' · '+e.department:''}${e.line?' · '+e.line:''}`).join('\n');
    try{await navigator.clipboard.writeText(text);setMessage('List copied. Paste it into your message to staff.')}
    catch{setMessage('Copy unavailable in this browser. Use Export CSV.')}
  };
  return <section className="card"><div className="section-heading"><div><h2>Face registration</h2><p>Registration reported by the attendance kiosks. Profile photos are separate.</p></div></div>
    <div className="form-pad"><p>{active.filter(e=>e.face_registration==='pending').length} pending · {active.filter(e=>e.face_registration==='registered').length} registered · {active.filter(e=>!e.face_registration||e.face_registration==='unknown').length} unknown</p>
      <div className="filters"><select aria-label="Face registration status" value={status} onChange={e=>{setStatus(e.target.value);setMessage('')}}>{Object.entries(label).map(([key,text])=><option key={key} value={key}>{text}</option>)}</select>
        <input aria-label="Search face registration list" placeholder="Search name, ID, plant, department or line" value={search} onChange={e=>setSearch(e.target.value)}/>
        <button className="secondary" disabled={!rows.length} onClick={()=>exportCsv(rows.map(e=>({ID:e.id,Name:e.name,Plant:e.base||'',Department:e.department,Line:e.line,Team:e.team,FaceRegistration:label[status],LastReport:e.face_reported_at||''})),'face-registration-'+status+'.csv')}>Export CSV</button>
        <button className="secondary" disabled={!rows.length} onClick={copy}>Copy list for reminder</button></div>
      <p className="field-help">Pending means absent from the current reports from this plant’s kiosks. Unknown means no recent report; update or reconnect the Pi. Registered means present on at least one reporting kiosk. Reports refresh about every 20 seconds.</p>
      {message&&<p role="status">{message}</p>}
      <details><summary>View {rows.length} employees · {label[status]}</summary><div className="table-wrap"><table><thead><tr><th>ID</th><th>NAME</th><th>PLANT / DEPARTMENT</th><th>LINE / TEAM</th><th>LAST REPORT</th></tr></thead><tbody>{rows.map(e=><tr key={e.id}><td>{e.id}</td><td>{e.name}</td><td>{[e.base,e.department].filter(Boolean).join(' · ')}</td><td>{[e.line,e.team].filter(Boolean).join(' · ')}</td><td>{e.face_reported_at?new Date(e.face_reported_at).toLocaleString('en-MY',{timeZone:'Asia/Kuala_Lumpur'}):'Not reported'}</td></tr>)}</tbody></table>{!rows.length&&<p>No employees match this list.</p>}</div></details>
    </div></section>;
}
