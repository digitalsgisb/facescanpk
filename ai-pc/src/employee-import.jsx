import React,{useRef,useState} from 'react';
import {parseEmployeeFile,requestId} from './transfer-utils.js';

export function EmployeeImport({api,onRefresh,base=''}) {
  const [payload,setPayload]=useState(null),[report,setReport]=useState(null),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  const pending=useRef(null),saving=useRef(false);
  async function preview(file){
    if(!file)return;if(saving.current)return;saving.current=true;setBusy(true);setReport(null);setPayload(null);setMessage('');pending.current=null;
    try{
      if(file.size>2_000_000)throw new Error('Choose an employee update file smaller than 2 MB.');
      let data,result;
      if(file.name.toLowerCase().endsWith('.xlsx')){
        const file_base64=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error('Could not read Excel file'));reader.readAsDataURL(file)});
        result=await api('/employee-import/spreadsheet','POST',{file_base64});data=result.payload;
      }else{
        data=parseEmployeeFile(await file.text());result=await api('/employee-import/preview','POST',{payload:data});
      }
      setPayload(data);setReport(result);
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
  return <details className="card form-pad employee-import"><summary>Import employees & shifts from Excel</summary>
    <p>{base||'All plants'} · Bulk-update locations, departments, lines, teams and default shifts. Preview before applying.</p>
    <a className="secondary" href="/api/employee-template" download="employee-import-template.xlsx">Download Excel template with current employees</a>
    <p className="field-help">Edit the template and upload it below. Blank cells keep existing values; type Unassigned to clear an optional field. Team shifts, rotations and date overrides take priority over a default shift. Photos and attendance stay.</p>
    <label>Employee update file<input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/json,.json" disabled={busy} onChange={e=>{preview(e.target.files?.[0]);e.target.value=''}}/></label>
    {report&&<>{payload?.format==='sgi-team-assignments-v1'&&<p><strong>Existing employee assignments only.</strong> Updates team/line within {payload.plant}. Names, photos and other profile details stay.</p>}<p role="status">{report.summary.create} new · {report.summary.update} updates · {report.summary.unchanged} unchanged · {report.summary.preserved_not_in_file} existing employees absent from the file will be kept.</p>
      <details><summary>Review employee changes ({report.changes.length})</summary><div style={{maxHeight:400,overflow:'auto'}}>{report.changes.map(c=><div key={c.id}><strong>{c.id} · {c.base} · {c.action}</strong>{Object.entries(c.changes).map(([field,v])=><p key={field}>{field}: {v.before??'(new)'} → {v.after}</p>)}</div>)}</div></details>
      <button className="primary" disabled={busy} onClick={apply}>{busy?'Applying…':'Back up and apply reviewed changes'}</button></>}
    {message&&<p role="status">{message}</p>}
  </details>;
}
