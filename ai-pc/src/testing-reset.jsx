import React,{useRef,useState} from 'react';
import {requestId} from './transfer-utils.js';

export function TestingReset({api,onRefresh,onLocked,base=''}) {
  const [open,setOpen]=useState(false),[confirmation,setConfirmation]=useState(''),[reason,setReason]=useState('');
  const [busy,setBusy]=useState(false),[message,setMessage]=useState('');
  const pending=useRef(null),saving=useRef(false);
  async function reset(event){
    event.preventDefault();if(saving.current)return;saving.current=true;setBusy(true);setMessage('');
    const key=JSON.stringify({confirmation,reason});
    if(pending.current?.key!==key)pending.current={key,id:requestId()};
    try{
      const result=await api('/clock/reset','POST',{confirmation,reason,request_id:pending.current.id});
      pending.current=null;setOpen(false);setConfirmation('');setReason('');
      setMessage(`${result.closed} open sessions closed. Backup saved on AI PC: ${result.backup}`);
      await onRefresh();
    }catch(e){setMessage(e.message);if(e.status===403)onLocked()}
    finally{setBusy(false);saving.current=false}
  }
  return <section className="card form-pad"><h3>Testing reset</h3>
    <p>Scope: <strong>{base||'All plants'}</strong>. Close every open clock-in, including old test sessions. Attendance history is kept and marked as a testing reset. A backup is saved first.</p>
    {!open?<button className="clock-out-action" onClick={()=>setOpen(true)}>Clock out everyone — testing reset</button>:<form className="form-grid" onSubmit={reset}>
      <label>Reason<input required minLength={5} maxLength={500} value={reason} disabled={busy} onChange={e=>setReason(e.target.value)}/></label>
      <label>Type CLOCK OUT EVERYONE<input required pattern="CLOCK OUT EVERYONE" value={confirmation} disabled={busy} onChange={e=>setConfirmation(e.target.value)}/></label>
      <button className="clock-out-action" disabled={busy||confirmation!=='CLOCK OUT EVERYONE'||reason.trim().length<5}>{busy?'Closing sessions…':'Back up and clock out everyone'}</button>
      <button className="secondary" type="button" disabled={busy} onClick={()=>setOpen(false)}>Cancel</button>
    </form>}
    {message&&<p role="status">{message}</p>}
    <small>Pause kiosk scanning and let queued scans finish before resetting. New scans after the reset may clock employees in again.</small>
  </section>;
}
