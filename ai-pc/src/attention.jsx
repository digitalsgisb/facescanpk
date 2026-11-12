import React,{useEffect,useRef,useState} from 'react';
import {CalendarDays,Clock3,AlertTriangle,CheckCircle2} from 'lucide-react';
import {readJson,issueDetails,sessionIssues} from './attention.js';
import {requestId} from './transfer-utils.js';
import './attention.css';

const categories=[['hours','Hours',CalendarDays],['attendance','Attendance',Clock3],['scans','Scans',AlertTriangle]];
const dateTime=v=>new Intl.DateTimeFormat('en-MY',{timeZone:'Asia/Kuala_Lumpur',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(v));
export function AttentionCentre({summary,revision,api,onEmployee,onAttendance,onScan,onLog,onRefresh,employees=[],plant=''}){
  const [category,setCategory]=useState('attendance'),[offset,setOffset]=useState(0),[base,setBase]=useState(plant),[data,setData]=useState(null),[error,setError]=useState(''),[retry,setRetry]=useState(0);
  const [enabled,setEnabled]=useState(true),[selected,setSelected]=useState(new Set()),[before,setBefore]=useState(''),[batch,setBatch]=useState(null),[reason,setReason]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  const pending=useRef(null),saving=useRef(false),limit=50;
  const plants=[...new Set(employees.map(e=>e.base).filter(Boolean))].sort();
  useEffect(()=>{let active=true;api(`/attention?category=${category}&base=${encodeURIComponent(base)}&offset=${offset}&limit=${limit}`).then(d=>{if(active){setData(d);setError('')}}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[category,base,offset,revision,retry]);
  useEffect(()=>{let active=true;api('/plant-controls?base='+encodeURIComponent(base)).then(d=>{if(active)setEnabled(d.settings.review_enabled)}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[base]);
  useEffect(()=>{setSelected(new Set());setBatch(null);pending.current=null},[category,base,offset,before]);
  async function toggle(value){setBusy(true);try{await api('/plant-controls','PUT',{base,review_enabled:value});setEnabled(value);setRetry(r=>r+1);await onRefresh()}catch(e){setError(e.message)}finally{setBusy(false)}}
  async function preview(all){
    if(saving.current)return;saving.current=true;setBusy(true);setError('');setMessage('');setBatch(null);pending.current=null;
    const input={category,base,before,...(all?{}:{ids:[...selected]})};
    try{const result=await api('/reviews/preview','POST',input);setBatch({...input,...result});setReason('')}catch(e){setError(e.message)}finally{saving.current=false;setBusy(false)}
  }
  async function apply(){
    if(saving.current||!batch)return;saving.current=true;setBusy(true);setError('');
    if(!pending.current)pending.current=requestId();
    try{const r=await api('/reviews/bulk','POST',{category:batch.category,base:batch.base,before:batch.before,...(batch.ids?{ids:batch.ids}:{}),preview_token:batch.preview_token,request_id:pending.current,reason});setMessage(`${r.reviewed} marked reviewed. Clock times unchanged.`);setBatch(null);setSelected(new Set());pending.current=null;setRetry(v=>v+1);await onRefresh()}
    catch(e){setError(e.message);if(e.status===409){setBatch(null);pending.current=null}}finally{saving.current=false;setBusy(false)}
  }
  const counts=data?.summary||summary,items=data?.items||[];
  return <section className="attention-centre">
    <div className="review-toolbar card form-pad">
      {!plant&&<label>Plant<select value={base} disabled={busy} onChange={e=>{setBase(e.target.value);setOffset(0)}}><option value="">All plants</option>{plants.map(p=><option key={p}>{p}</option>)}</select></label>}
      <label className="checkbox-label"><input type="checkbox" checked={enabled} disabled={busy} onChange={e=>toggle(e.target.checked)}/>Review prompts</label>
      <small>{enabled?`${counts.total} items`:'Review prompts off. Records stay in the log.'}</small>
    </div>
    <div className="attention-categories" role="group" aria-label="Issue categories">{categories.map(([key,label,Icon])=><button key={key} aria-pressed={key===category} onClick={()=>{setCategory(key);setOffset(0)}}><Icon size={18}/><span>{label}</span><strong>{counts[key]}</strong></button>)}</div>
    {category!=='hours'&&enabled&&<section className="card form-pad review-toolbar">
      <label>Through date (optional)<input type="date" value={before} disabled={busy} onChange={e=>setBefore(e.target.value)}/></label>
      <button className="secondary" disabled={busy||!selected.size} onClick={()=>preview(false)}>Mark selected ({selected.size})</button>
      <button className="primary" disabled={busy||!counts[category]} onClick={()=>preview(true)}>Mark all reviewed</button>
      {batch&&<div className="bulk-review-confirm"><strong>{batch.count} {category==='scans'?'scans':'sessions'} · {base||'All plants'}</strong><p>Times unchanged. Open sessions stay open.</p>
        <label>Reason<input minLength={5} maxLength={500} value={reason} disabled={busy} onChange={e=>{setReason(e.target.value);pending.current=null}}/></label>
        <button className="primary" disabled={busy||!batch.count||reason.trim().length<5} onClick={apply}>Confirm review</button><button className="secondary" disabled={busy} onClick={()=>setBatch(null)}>Cancel</button>
      </div>}
    </section>}
    {error&&<p className="inline-error" role="alert">{error}<button className="text-button" onClick={()=>setRetry(r=>r+1)}>Refresh</button></p>}{message&&<p role="status">{message}</p>}
    <section className="card attention-list">
      {category!=='hours'&&items.length>0&&<label className="review-page-select"><input type="checkbox" checked={items.every(i=>selected.has(i.id))} onChange={e=>setSelected(e.target.checked?new Set(items.map(i=>i.id)):new Set())}/>Select this page</label>}
      {!data?<p className="form-pad" role="status">Loading…</p>:!items.length?<div className="attention-empty"><CheckCircle2 size={24}/><strong>No pending items</strong></div>:<>
        {items.map(item=>{const result=category==='scans'?readJson(item.result,{}):null;const flags=category==='hours'?[{code:'hours',title:'Hours not set'}]:category==='attendance'?sessionIssues(item):issueDetails(result.flags);
          return <article className="attention-issue" key={item.id}><div className="attention-person">
            {category!=='hours'&&<input type="checkbox" aria-label={'Select '+item.id} checked={selected.has(item.id)} onChange={e=>{const checked=e.target.checked;setSelected(s=>{const n=new Set(s);checked?n.add(item.id):n.delete(item.id);return n})}}/>}
            <strong>{item.nickname||item.name}</strong><small>{item.employee_id||item.id} · {item.base||'Unassigned'}</small>
            {category==='attendance'&&<small>{dateTime(item.time_in)} → {item.time_out?dateTime(item.time_out):'Open'}</small>}{category==='scans'&&<small>{dateTime(item.occurred_at)}</small>}
          </div><div className="attention-reasons">{flags.map(f=><span key={f.code}>{f.title}</span>)}{result&&<details><summary>Details</summary>{result.message}</details>}</div>
          <div className="attention-actions"><button className="secondary" onClick={()=>category==='hours'?onEmployee(item):category==='attendance'?onAttendance(item):onScan(item)}>{category==='hours'?'Set hours':'Open'}</button>{category!=='hours'&&<button className="text-button" onClick={()=>onLog(item,category)}>Log</button>}</div></article>})}
        <footer className="attention-pagination"><span>{data.offset+1}–{data.offset+items.length} / {data.total}</span><div><button className="secondary" disabled={!data.offset} onClick={()=>setOffset(Math.max(0,data.offset-limit))}>Previous</button><button className="secondary" disabled={data.offset+items.length>=data.total} onClick={()=>setOffset(data.offset+limit)}>Next</button></div></footer>
      </>}
    </section>
  </section>;
}
