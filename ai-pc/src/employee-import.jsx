import React,{useRef,useState} from 'react';
import {parseEmployeeFile,requestId} from './transfer-utils.js';

export function EmployeeImport({api,onRefresh,base=''}) {
  const [payload,setPayload]=useState(null),[report,setReport]=useState(null),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  const pending=useRef(null),saving=useRef(false);
  async function preview(file){
    if(!file)return;if(saving.current)return;saving.current=true;setBusy(true);setReport(null);setPayload(null);setMessage('');pending.current=null;
    try{
      if(file.size>2_000_000)throw new Error('Choose an employee update file smaller than 2 MB.');
      const data=parseEmployeeFile(await file.text());
      const result=await api('/employee-import/preview','POST',{payload:data});setPayload(data);setReport(result);
    }catch(e){setMessage(e.message)}finally{saving.current=false;setBusy(false)}
  }
  async function apply(){
    if(saving.current||!report)return;saving.current=true;setBusy(true);setMessage('');
    if(!pending.current)pending.current=requestId();
    try{
      const r=await api('/employee-import/apply','POST',{payload,preview_token:report.preview_token,request_id:pending.current});
      pending.current=null;setReport(null);setPayload(null);
      setMessage(`${r.summary.create} added, ${r.summary.update} updated, ${r.summary.unchanged} unchanged. Backup saved on AI PC: ${r.backup}`);await onRefresh();
    }catch(e){setMessage(e.message);if(e.status===409){setReport(null);pending.current=null}}
    finally{saving.current=false;setBusy(false)}
  }
  return <section className="card form-pad employee-import"><h2>Import employee details</h2>
    <p>Location: {base||'All plants'}. Choose a prepared employee JSON file, review the changes, then apply. Existing photos, teams, lines, schedules and active status are preserved. Position follows the sheet’s Job Type exactly.</p>
    <label>Employee update file<input type="file" accept="application/json,.json" disabled={busy} onChange={e=>{preview(e.target.files?.[0]);e.target.value=''}}/></label>
    {report&&<><p role="status">{report.summary.create} new · {report.summary.update} updates · {report.summary.unchanged} unchanged · {report.summary.preserved_not_in_file} existing employees absent from the file will be kept.</p>
      <details><summary>Review employee changes ({report.changes.length})</summary><div style={{maxHeight:400,overflow:'auto'}}>{report.changes.map(c=><div key={c.id}><strong>{c.id} · {c.base} · {c.action}</strong>{Object.entries(c.changes).map(([field,v])=><p key={field}>{field}: {v.before??'(new)'} → {v.after}</p>)}</div>)}</div></details>
      <button className="primary" disabled={busy} onClick={apply}>{busy?'Applying…':'Back up and apply reviewed changes'}</button></>}
    {message&&<p role="status">{message}</p>}
  </section>;
}
