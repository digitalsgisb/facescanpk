import React,{useState,useMemo,useRef,useLayoutEffect,useEffect} from 'react';
import {Users,Pencil,Clock3,Search,Monitor,Minimize2,Maximize2,ArrowUpDown,ChevronDown} from 'lucide-react';

function Photo({employee}){
  const [failed,setFailed]=useState(false);
  useEffect(()=>setFailed(false),[employee.photo_url]);
  return <span className="staff-photo">{employee.photo_url&&!failed?<img src={employee.photo_url} alt="" loading="lazy" onError={()=>setFailed(true)}/>:employee.name.split(' ').slice(0,2).map(n=>n[0]).join('')}</span>;
}
function sortPeople(people,sort){
  const role=e=>e.position==='SUPERVISOR'?0:e.position==='LEADER'?1:2;
  const group=(a,b)=>(!a.team)-(!b.team)||(a.team||'').localeCompare(b.team||'')||(!a.line)-(!b.line)||(a.line||'').localeCompare(b.line||'');
  return [...people].sort((a,b)=>(sort==='status'?(a.status==='IN'?0:1)-(b.status==='IN'?0:1):sort==='team'?group(a,b):sort==='role'?role(a)-role(b):0)||(a.nickname||a.name).localeCompare(b.nickname||b.name));
}
export function departmentOrder(a,b){
  const priority=name=>name==='OFFICE'?0:name==='PRODUCTION'?1:2;
  return priority(a)-priority(b)||a.localeCompare(b);
}
function BoardEmployee({employee:e,onAttendance,busy}){
  return <button className={'tv-employee '+(e.status==='IN'?'in':'out')} disabled={busy} title={`${e.status==='IN'?'Clock out':'Clock in'} ${e.name}`} aria-label={(e.status==='IN'?'Clock out ':'Clock in ')+e.name} onClick={()=>onAttendance?.(e)}>
    <Photo employee={e}/><div><strong>{e.nickname||e.name}</strong><small>{e.position||'Position not set'}</small></div><span>{e.status}</span>
    {(e.position==='SUPERVISOR'||e.position==='LEADER')&&<i>{e.position==='SUPERVISOR'?'SUP':'LDR'}</i>}
  </button>;
}
function boardGroupName(employee){
  return employee.department==='PRODUCTION' ? employee.line?.trim()||'Production · line unassigned' : employee.department||'Department unassigned';
}
function boardGroupOrder(a,b){
  const order=['OFFICE','FC','LM & SA','MAINTENANCE & FACILITIES','MF','QUALITY MANAGEMENT','R&D','ROLL MAKING','SAFETY & HEALTH','STORE'];
  const rank=name=>order.includes(name)?order.indexOf(name):order.length;
  return rank(a)-rank(b)||a.localeCompare(b);
}
function BoardRow({name,workers,onAttendance,busy}){
  const office=name==='OFFICE';
  const teams=office ? [['',workers]] : Object.entries(workers.reduce((out,e)=>{(out[e.team||'Unassigned']||=[]).push(e);return out},{})).sort(([a],[b])=>a==='Unassigned'?1:b==='Unassigned'?-1:a.localeCompare(b));
  return <section className="tv-department board-group" aria-label={name}>
    <div className="tv-department-title"><h3>{name}</h3><small><b>{workers.filter(e=>e.status==='IN').length}</b> / {workers.length}</small></div>
    <div className="board-group-teams">{teams.map(([team,members])=><section className={'board-team-row '+(office?'office-row':'')} key={team} aria-label={office?'Office employees':team==='Unassigned'?'Team unassigned':'Team '+team}>
      {!office&&<h4 className={'board-team-strip team-'+team.toLowerCase()} title={team==='N'?'Normal working hours':team==='Unassigned'?'Team unassigned':'Team '+team}>{team==='Unassigned'?'—':team}</h4>}
      <div className="tv-department-people">{sortPeople(members,office?'name':'role').map(e=><BoardEmployee key={e.id} employee={e} onAttendance={onAttendance} busy={busy}/>)}</div>
    </section>)}</div>
  </section>;
}
export function EmployeeGroups({employees,onEdit,onAttendance,onClock,busy}){
  const [sort,setSort]=useState('team'),[selected,setSelected]=useState('OFFICE'),[pages,setPages]=useState({});
  const directory=useRef(null),navigator=useRef(null);
  const groups=useMemo(()=>Object.entries(employees.reduce((out,e)=>{(out[e.department||'Unassigned']||=[]).push(e);return out},{})).sort(([a],[b])=>departmentOrder(a,b)),[employees]);
  const signature=employees.map(e=>e.id).join('|');
  useEffect(()=>setPages({}),[signature,sort]);
  const active=groups.some(([name])=>name===selected)||selected===null?selected:groups[0]?.[0];
  const displayedGroups=[...groups].sort(([a],[b])=>(a===active?0:1)-(b===active?0:1)||departmentOrder(a,b));
  function choose(dept){
    setSelected(dept);
    requestAnimationFrame(()=>{
      if(!directory.current)return;
      const offset=(document.querySelector('.topbar')?.offsetHeight||0)+(navigator.current?.offsetHeight||0)+24;
      window.scrollTo({top:Math.max(0,window.scrollY+directory.current.getBoundingClientRect().top-offset),behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
    });
  }
  const pageSize=8;
  return <>
    <div className="group-view-toolbar"><span><Users size={16}/>{groups.length} departments · {employees.length} employees</span><label><ArrowUpDown size={15}/>Sort people<select aria-label="Sort employee cards" value={sort} onChange={e=>setSort(e.target.value)}><option value="name">Name A–Z</option><option value="team">Team & production line</option><option value="role">Role seniority</option><option value="status">Clocked in first</option></select></label></div>
    <nav ref={navigator} className="department-navigator" aria-label="Department shortcuts">{groups.map(([dept,people])=><button key={dept} className={active===dept?'current':''} onClick={()=>choose(dept)} aria-pressed={active===dept}>{dept}<span>{people.length}</span></button>)}</nav>
    <div ref={directory} className="employee-departments compact-directory">{displayedGroups.map(([department,people],i)=>{
      const open=active===department, page=Math.min(pages[department]||0,Math.max(0,Math.ceil(people.length/pageSize)-1));
      return <section className={'department-card '+(open?'department-open':'')} key={department}>
        <button className="department-card-heading" onClick={()=>open?setSelected(null):choose(department)} aria-expanded={open}><span className="department-symbol"><Users size={20}/></span><div><h2>{department}</h2><small>{people.length} people · {people.filter(e=>e.status==='IN').length} currently in</small></div><ChevronDown size={18} className={!open?'collapsed':''}/></button>
        <div className={'department-collapse '+(open?'is-open':'')} aria-hidden={!open} inert={!open?true:undefined}><div className="department-collapse-inner"><div className="department-staff">{sortPeople(people,sort).slice(page*pageSize,(page+1)*pageSize).map(e=><article className="staff-card" key={e.id}><div className="staff-card-top"><Photo employee={e}/><div className="staff-identity"><strong title={e.name}>{e.nickname||e.name}</strong><small>{e.id}</small></div><span className={'staff-status '+(e.status==='IN'?'in':'out')}><i/>{e.status}</span></div><div className="staff-details"><span>{e.position||'Employee'}{e.line?' · '+e.line:''}</span><span>{e.team?'Team '+e.team:'No team'} · {e.effective_schedule?`${e.effective_schedule.start}–${e.effective_schedule.end}`:'Hours unassigned'}</span></div><div className="staff-actions"><button aria-label={'Edit '+e.name} onClick={()=>onEdit(e)}><Pencil size={13}/>Profile</button><button aria-label={'Update attendance for '+e.name} onClick={()=>onAttendance(e)}><Clock3 size={13}/>History</button>{e.active&&<button className={"quick-clock "+(e.status==='IN'?'clock-out':'clock-in')} disabled={busy} aria-label={(e.status==='IN'?'Clock out ':'Clock in ')+e.name} onClick={()=>onClock(e)}><Clock3 size={13}/>{e.status==='IN'?'Clock out':'Clock in'}</button>}</div></article>)}</div><footer className="department-pagination"><span>Showing {page*pageSize+1}–{Math.min((page+1)*pageSize,people.length)} of {people.length} employees</span><div><button disabled={page===0} onClick={()=>setPages({...pages,[department]:page-1})} aria-label={'Previous '+department+' employees'}>Previous</button><span>{page+1} / {Math.ceil(people.length/pageSize)}</span><button disabled={(page+1)*pageSize>=people.length} onClick={()=>setPages({...pages,[department]:page+1})} aria-label={'Next '+department+' employees'}>Next</button></div></footer></div></div>
      </section>;
    })}</div>{!employees.length&&<div className="empty"><Search size={30}/><h3>No matching employees</h3><p>Try a different search or filter.</p></div>}
  </>;
}

export function LiveBoard({employees,live,onAttendance,soundControl,busy,clockError}){
  const [query,setQuery]=useState(''),[onlyIn,setOnlyIn]=useState(false),[fit,setFit]=useState(false),[fullscreen,setFullscreen]=useState(false),[scale,setScale]=useState(1);
  const root=useRef(null),stage=useRef(null),header=useRef(null),toolbar=useRef(null);
  const people=employees.filter(e=>(!onlyIn||e.status==='IN')&&(!query||[e.name,e.nickname,e.id,e.department,e.line,e.position].some(s=>s?.toLowerCase().includes(query.toLowerCase()))));
  const groups=useMemo(()=>Object.entries(people.reduce((out,e)=>{(out[boardGroupName(e)]||=[]).push(e);return out},{})).sort(([a],[b])=>boardGroupOrder(a,b)),[employees,query,onlyIn]);
  useEffect(()=>{const listener=()=>{const active=document.fullscreenElement===root.current;setFullscreen(active);if(active){setFit(true);setQuery('');setOnlyIn(false)}};document.addEventListener('fullscreenchange',listener);return()=>document.removeEventListener('fullscreenchange',listener)},[]);
  useLayoutEffect(()=>{
    let frame;const measure=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{
      if(!stage.current||!root.current)return;
      if(!fit){stage.current.style.width='100%';setScale(1);return;}
      const available=stage.current.parentElement.clientHeight-8;
      const width=stage.current.parentElement.clientWidth;
      // Find the largest readable scale while also using the entire screen width.
      let low=.05,high=1;
      for(let i=0;i<12;i++){const candidate=(low+high)/2;stage.current.style.width=`${width/candidate}px`;if(stage.current.scrollHeight*candidate<=available)low=candidate;else high=candidate;}
      stage.current.style.width=`${width/low}px`;setScale(low);
    })};
    const observer=new ResizeObserver(measure);observer.observe(root.current);observer.observe(stage.current.parentElement);measure();return()=>{observer.disconnect();cancelAnimationFrame(frame)};
  },[fit,fullscreen,groups]);
  async function toggleFullscreen(){
    if(fullscreen){if(document.fullscreenElement)await document.exitFullscreen();else setFullscreen(false);return;}
    setFit(true);setQuery('');setOnlyIn(false);
    try{await root.current.requestFullscreen()}catch{setFullscreen(true)}
  }
  return <section ref={root} className={'board-page redesigned-board '+(fit?'fit-all ':'')+(fullscreen?'tv-mode':'')}><header className="board-header" ref={header}><div className="board-brand"><img src="/1.png" alt="Sugihara"/><div><h2>Digital Attendance</h2><small>Port Klang · attendance workspace</small></div></div><div className="board-totals">{soundControl}<div><b>{people.length}</b><small>{fit?'Employees on screen':'Employees shown'}</small></div><div><b>{employees.filter(e=>e.status==='IN').length}</b><small>Currently in</small></div><div><b>{employees.filter(e=>e.status!=='IN').length}</b><small>Currently out</small></div><span className={'badge '+(live?'green':'amber')}>{live?'Live':'Reconnecting'}</span><button className="secondary" onClick={()=>{setFit(!fit);if(!fit){setQuery('');setOnlyIn(false)}}}>{fit?<Minimize2 size={15}/>:<Maximize2 size={15}/>} {fit?'Comfort view':'Fit all'}</button><button className="secondary" onClick={toggleFullscreen}>{fullscreen?<Minimize2 size={15}/>:<Monitor size={15}/>} {fullscreen?'Exit TV':'TV fullscreen'}</button></div></header>{!fullscreen&&<div className="board-toolbar" ref={toolbar}><div className="search"><Search size={17}/><input aria-label="Search live board" placeholder="Find a person, department or line…" value={query} onChange={e=>{setQuery(e.target.value);setFit(false)}}/></div><label className="checkbox-label"><input type="checkbox" checked={onlyIn} onChange={e=>{setOnlyIn(e.target.checked);setFit(false)}}/>Show clocked-in employees only</label></div>}{clockError&&<div className="inline-error" role="alert">{clockError}</div>}<div className="board-stage-window"><div className="board-stage" ref={stage} style={{transform:fit?`scale(${scale})`:undefined}}>{groups.map(([name,workers])=><BoardRow key={name} name={name} workers={workers} onAttendance={onAttendance} busy={busy}/>)}</div></div>{fit&&<div className="tv-fit-footer">{people.length} employees · {groups.length} groups · Auto-fit {Math.round(scale*100)}%<span>IN / OUT stays visible · Select a person to clock in or out</span></div>}</section>;
}
