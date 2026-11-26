import React,{useRef,useState} from 'react';
import {ArrowDownToLine,Upload,Check} from 'lucide-react';
import {parseEmployeeFile,requestId} from './transfer-utils.js';

// A real sequence: get the template, upload the edited file, review, apply. Each step is numbered for that reason.
export function EmployeeImport({api,onRefresh,base='',onDone}) {
  const [payload,setPayload]=useState(null),[report,setReport]=useState(null),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[done,setDone]=useState(null),[fileName,setFileName]=useState('');
  const pending=useRef(null),saving=useRef(false);
  async function preview(file){
    if(!file)return;if(saving.current)return;saving.current=true;setBusy(true);setReport(null);setPayload(null);setMessage('');setDone(null);setFileName(file.name);pending.current=null;
    try{
      if(file.size>2_000_000)throw new Error('This file is larger than 2 MB. Remove unused sheets or rows and upload it again.');
      let data,result;
      if(file.name.toLowerCase().endsWith('.xlsx')){
        const file_base64=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error('Could not read this Excel file. Save it again as .xlsx and retry.'));reader.readAsDataURL(file)});
        result=await api('/employee-import/spreadsheet','POST',{file_base64});data=result.payload;
      }else{
        data=parseEmployeeFile(await file.text());result=await api('/employee-import/preview','POST',{payload:data});
      }
      setPayload(data);setReport(result);
    }catch(e){setMessage(e.message);setFileName('')}finally{saving.current=false;setBusy(false)}
  }
  async function apply(){
    if(saving.current||!report)return;saving.current=true;setBusy(true);setMessage('');
    if(!pending.current)pending.current=requestId();
    try{
      const r=await api('/employee-import/apply','POST',{payload,preview_token:report.preview_token,request_id:pending.current});
      pending.current=null;setReport(null);setPayload(null);setFileName('');
      setDone(r);await onRefresh();
    }catch(e){setMessage(e.message);if(e.status===409){setReport(null);pending.current=null}}
    finally{saving.current=false;setBusy(false)}
  }
  const step=n=>report?n<3?'is-done':n===3?'is-current':'':n===1?'':n===2?'is-current':'';
  return <section className="card import-page" data-update-blocked={!!payload || busy}>
    <ol className="import-steps">
      <li className={step(1)}>
        <h2>Download the template</h2>
        <p>It already lists everyone in {base?base.toLowerCase().replace(/\b\w/g,c=>c.toUpperCase()):'all plants'}. Change only the cells you need: plant, department, line, team or default shift.</p>
        <a className="secondary" href="/api/employee-template" download="employee-import-template.xlsx"><ArrowDownToLine size={15}/>Download Excel template</a>
      </li>
      <li className={step(2)}>
        <h2>Upload your edited file</h2>
        <p>Blank cells keep the current value. Type Unassigned to clear an optional field. Photos and attendance are never changed.</p>
        <label className={'import-drop'+(busy&&!report?' is-busy':'')}>
          <Upload size={18}/><span>{busy&&!report?'Checking '+fileName+'…':fileName||'Choose an .xlsx file'}</span>
          <input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/json,.json" disabled={busy} onChange={e=>{preview(e.target.files?.[0]);e.target.value=''}}/>
        </label>
      </li>
      <li className={step(3)}>
        <h2>Review and apply</h2>
        {!report&&<p>After you upload, you’ll see every change here before anything is saved.</p>}
        {report&&<>
          {payload?.format==='sgi-team-assignments-v1'&&<p>This file only moves existing people between teams and lines in {payload.plant}. Names, photos and other details stay.</p>}
          <dl className="import-summary">
            <div><dt>New people</dt><dd>{report.summary.create}</dd></div>
            <div><dt>Updated</dt><dd>{report.summary.update}</dd></div>
            <div><dt>Unchanged</dt><dd>{report.summary.unchanged}</dd></div>
            <div><dt>Not in file, kept</dt><dd>{report.summary.preserved_not_in_file}</dd></div>
          </dl>
          {report.changes.length>0&&<div className="import-changes">{report.changes.map(c=><div key={c.id} className="import-change"><strong>{c.id}<small>{c.base} · {c.action}</small></strong><ul>{Object.entries(c.changes).map(([field,v])=><li key={field}><span>{field.replace(/_id$/,'').replace(/_/g,' ')}</span> {v.before||(v.before===null||v.before===undefined?'(new)':'(blank)')} → <b>{v.after||'(blank)'}</b></li>)}</ul></div>)}</div>}
          <div className="import-actions"><button className="primary" disabled={busy} onClick={apply}>{busy?'Applying…':`Back up and apply ${report.changes.length} ${report.changes.length===1?'change':'changes'}`}</button><button className="secondary" disabled={busy} onClick={()=>{setReport(null);setPayload(null);setFileName('')}}>Cancel</button></div>
          <p className="field-help">Team shifts, rotations and date overrides still take priority over a default shift.</p>
        </>}
      </li>
    </ol>
    {done&&<div className="import-done" role="status"><Check size={18}/><div><strong>{done.summary.create} added, {done.summary.update} updated, {done.summary.unchanged} unchanged.</strong><p>Backup saved on the AI PC: {done.backup}</p></div>{onDone&&<button className="secondary" onClick={onDone}>View employees</button>}</div>}
    {message&&<p className="inline-error" role="alert">{message}</p>}
  </section>;
}
