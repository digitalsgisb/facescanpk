import React, {useState} from 'react';
import {ArrowDownToLine} from 'lucide-react';

export function EmployeeShiftExport({employees,today,notify,Dialog,Field}){
  const [selection,setSelection]=useState(null);
  const [from,setFrom]=useState(today),[to,setTo]=useState(today);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const valid=from&&to&&from<=to;
  async function download(event){
    event.preventDefault();
    if(!valid||busy)return;
    setBusy(true);setError('');
    try{
      const response=await fetch('/api/employee-export',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({from,to,employee_ids:selection})});
      if(!response.ok){const result=await response.json();throw new Error(result.error||'Excel export failed');}
      const url=URL.createObjectURL(await response.blob());
      const link=document.createElement('a');link.href=url;link.download=`employee_shifts_${from}_to_${to}.xlsx`;
      document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
      setSelection(null);notify('Employee locations and shifts exported');
    }catch(e){setError(e.message)}finally{setBusy(false)}
  }
  return <><button className="text-button" disabled={!employees.length} onClick={()=>{setSelection(employees.map(e=>e.id));setError('')}}><ArrowDownToLine size={16}/>Export Excel</button>
    {selection&&<Dialog title="Export employee locations & shifts" subtitle={`${selection.length} employees matching your directory filters`} onClose={()=>{if(!busy)setSelection(null)}}>
      <form className="form-pad" onSubmit={download}>
        <p>One row per employee per work date, with their plant, department, line, team and assigned working hours.</p>
        <div className="form-grid"><Field label="From work date"><input type="date" required value={from} max={to||undefined} disabled={busy} onChange={e=>setFrom(e.target.value)}/></Field>
          <Field label="To work date"><input type="date" required value={to} min={from||undefined} disabled={busy} onChange={e=>setTo(e.target.value)}/></Field></div>
        <p className="field-help">Both dates included, up to one year. Shifts follow saved rotation, overtime and date overrides. Locations use current employee profiles. Times are Malaysia time.</p>
        {error&&<div className="inline-error" role="alert">{error}</div>}
        <button className="primary" disabled={busy||!valid}><ArrowDownToLine size={16}/>{busy?'Exporting…':'Download Excel'}</button>
      </form>
    </Dialog>}</>;
}
