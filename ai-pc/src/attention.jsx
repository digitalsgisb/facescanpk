import React,{useEffect,useState} from 'react';
import {AlertTriangle,CalendarDays,Clock3,Search,CheckCircle2,ArrowUpRight,RefreshCw} from 'lucide-react';
import {readJson,issueDetails,sessionIssues} from './attention.js';
import './attention.css';

const categories=[['hours','Missing working hours',CalendarDays],['attendance','Attendance to check',Clock3],['scans','Scans awaiting review',AlertTriangle]];
const dateTime=value=>new Intl.DateTimeFormat('en-MY',{timeZone:'Asia/Kuala_Lumpur',day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value));
export function AttentionCentre({summary,revision,api,onEmployee,onAttendance,onScan,onLog}){
  const [category,setCategory]=useState(()=>categories.find(([key])=>summary[key]>0)?.[0]||'hours'),[offset,setOffset]=useState(0),[data,setData]=useState(null),[loading,setLoading]=useState(true),[error,setError]=useState(''),[retry,setRetry]=useState(0);
  const limit=50;
  useEffect(()=>{let current=true;setLoading(true);setError('');api(`/attention?category=${category}&offset=${offset}&limit=${limit}`).then(result=>{if(current)setData(result)}).catch(e=>{if(current)setError(e.message)}).finally(()=>{if(current)setLoading(false)});return()=>{current=false}},[category,offset,revision,summary.hours,summary.attendance,summary.scans,retry]);
  function choose(key){setCategory(key);setOffset(0);setData(null)}
  const counts=data?.summary||summary;
  return <section className="attention-centre">
    <div className="attention-intro"><AlertTriangle size={24}/><div><strong>{summary.total} unresolved {summary.total===1?'issue':'issues'}</strong><p>Across all dates. Open an issue below to fix it. An attendance record with several flags counts once.</p></div></div>
    <div className="attention-categories" role="group" aria-label="Issue categories">{categories.map(([key,label,Icon])=><button key={key} aria-pressed={category===key} onClick={()=>choose(key)}><Icon size={21}/><span>{label}</span><strong>{counts[key]}</strong></button>)}</div>
    <section className="card attention-list" aria-busy={loading}><div className="section-heading"><div><h2>{categories.find(([key])=>key===category)[1]}</h2><p>{category==='hours'?'Choose an employee to assign their working hours.':category==='attendance'?'Review the exact attendance record, check the times and mark its flags reviewed.':'These scans were saved for review without changing attendance.'}</p></div><span className="attention-refresh" role="status">{loading&&data?'Updating…':''}</span></div>
      {error&&data&&<div className="attention-refresh-error" role="alert">Couldn’t refresh issues. Showing the previous list. <button className="text-button" onClick={()=>setRetry(value=>value+1)}>Try again</button></div>}
      {loading&&!data?<div className="attention-empty" role="status"><RefreshCw size={24} className="spin"/><p>Loading issues…</p></div>:error&&!data?<div className="attention-empty" role="alert"><AlertTriangle size={26}/><p>{error}</p><button className="secondary" onClick={()=>setRetry(value=>value+1)}>Try again</button></div>:!data?.items.length?<div className="attention-empty"><CheckCircle2 size={30}/><h3>All clear here</h3><p>No unresolved issues in this category.</p></div>:<>
      <div className="attention-rows">{data.items.map(item=>{
        const result=category==='scans'?readJson(item.result,{}):null;
        const flags=category==='hours'?[{code:'hours',title:'Working hours not assigned',detail:'Set this person’s individual hours, or configure their team in Control centre.'}]:category==='attendance'?sessionIssues(item):issueDetails(result.flags);
        return <article className="attention-issue" key={item.id}><div className="attention-person"><strong>{item.nickname||item.name}</strong><small>{category==='hours'?item.id:item.employee_id} · {[item.department,item.line,item.team&&'Team '+item.team].filter(Boolean).join(' · ')}</small>{category==='attendance'&&<small>Work date {item.work_date} · In: {dateTime(item.time_in)} · Out: {item.time_out?dateTime(item.time_out):'Still open'}</small>}{category==='scans'&&<small>{dateTime(item.occurred_at)}</small>}</div><div className="attention-reasons">{flags.map(flag=><div key={flag.code}><strong>{flag.title}</strong><p>{flag.detail}</p></div>)}{result&&<p>{result.message}</p>}</div><div className="attention-actions"><button className="primary" onClick={()=>category==='hours'?onEmployee(item):category==='attendance'?onAttendance(item):onScan(item)}>{category==='hours'?'Set working hours':category==='attendance'?'Review attendance':'Review scan'}<ArrowUpRight size={15}/></button>{category!=='hours'&&<button className="secondary" onClick={()=>onLog(item,category)}><Search size={14}/>View in attendance log</button>}</div></article>;
      })}</div><footer className="attention-pagination"><span>Showing {data.offset+1}–{data.offset+data.items.length} of {data.total}</span><div><button className="secondary" disabled={!data.offset} onClick={()=>setOffset(Math.max(0,data.offset-limit))}>Previous</button><button className="secondary" disabled={data.offset+data.items.length>=data.total} onClick={()=>setOffset(data.offset+limit)}>Next</button></div></footer></>}
    </section>
  </section>;
}
