import {employeeLocation} from './transfer-utils.js';
import {syncLabel} from './employee-sync.js';
import {paginateBoard} from './board-layout.js';
import {productionSection,sortEmployees,employeeGroup} from './organisation.js';
import React,{useState,useMemo,useRef,useLayoutEffect,useEffect} from 'react';
import {Users,Pencil,Clock3,Search,Monitor,Minimize2,Maximize2,ArrowUpDown,ChevronDown} from 'lucide-react';

function Photo({employee}){
  const [failed,setFailed]=useState(false);
  useEffect(()=>setFailed(false),[employee.photo_url]);
  return <span className="staff-photo">{employee.photo_url&&!failed?<img src={employee.photo_url} alt="" loading="lazy" onError={()=>setFailed(true)}/>:employee.name.split(' ').slice(0,2).map(n=>n[0]).join('')}</span>;
}
function sortPeople(people,sort,settings={}){
  const mode=sort==='saved'?(settings.employee_sort||'position'):sort;
  const sorted=sortEmployees(people,mode,settings.employee_order||[]);
  if(mode==='status')return sorted.sort((a,b)=>(a.status==='IN'?0:1)-(b.status==='IN'?0:1));
  if(mode==='team')return sorted.sort((a,b)=>(!a.team)-(!b.team)||(a.team||'').localeCompare(b.team||'')||(a.line||'').localeCompare(b.line||''));
  return sorted;
}
export function departmentOrder(a,b){
  const priority=name=>name==='OFFICE'?0:name.startsWith('PRODUCTION')?1:2;
  return priority(a)-priority(b)||a.localeCompare(b);
}
function BoardEmployee({employee:e,onDetails}){
  const role=e.position==='SUPERVISOR'?'SUP':e.position==='LEADER'?'LDR':null;
  return <button className={'tv-employee '+(e.status==='IN'?'in':'out')} title={[e.name,e.position,e.office_department].filter(Boolean).join(' · ')+' · View details'} aria-label={'View details for '+e.name} onClick={()=>onDetails?.(e)}>
    <Photo employee={e}/><div className="tv-card-name"><strong>{e.nickname||e.name}</strong><small>{e.position||'Employee'}{e.department?.trim().toUpperCase()==='OFFICE'&&e.office_department?' · '+e.office_department:''}</small></div><span className="tv-card-meta"><b>{e.status}</b>{role&&<em>{role}</em>}</span>
  </button>;
}
function boardGroupName(employee){
  return employeeLocation(employee)+' / '+(productionSection(employee)?employeeGroup(employee):employee.department||'Department unassigned');
}
function boardGroupOrder(a,b){
  const [plantA,...groupA]=a.split(' / '),[plantB,...groupB]=b.split(' / ');
  if(plantA!==plantB)return plantA.localeCompare(plantB);
  a=groupA.join(' / ');b=groupB.join(' / ');
  const order=['OFFICE','FC','LM & SA','MAINTENANCE & FACILITIES','MF','QUALITY MANAGEMENT','R&D','ROLL MAKING','SAFETY & HEALTH','STORE'];
  const rank=name=>order.includes(name)?order.indexOf(name):order.length;
  const section=name=>name==='OFFICE'?0:name==='CONVERSION'||name.startsWith('CONVERSION · ')?1:name==='ROLL MAKING'||name.startsWith('ROLL MAKING · ')?2:3;
  return section(a)-section(b)||rank(a.split(' · ').at(-1))-rank(b.split(' · ').at(-1))||a.localeCompare(b);
}
function BoardRow({name,workers,onDetails,settings}){
  const office=workers[0]?.department==='OFFICE';
  const teams=office ? [['',workers]] : Object.entries(workers.reduce((out,e)=>{(out[e.team||'Unassigned']||=[]).push(e);return out},{})).sort(([a],[b])=>a==='Unassigned'?1:b==='Unassigned'?-1:a.localeCompare(b));
  return <section className="tv-department board-group" aria-label={name}>
    <div className="tv-department-title"><h3>{name}</h3><small><b>{workers.filter(e=>e.status==='IN').length}</b> / {workers.length}</small></div>
    <div className="board-group-teams">{teams.map(([team,members])=><section className={'board-team-row '+(office?'office-row':'')} key={team} aria-label={office?'Office employees':team==='Unassigned'?'Team unassigned':'Team '+team}>
      {!office&&<h4 className={'board-team-strip team-'+team.toLowerCase()} title={team==='N'?'Normal working hours':team==='Unassigned'?'Team unassigned':'Team '+team}>{team==='Unassigned'?'—':team}</h4>}
      <div className="tv-department-people">{sortPeople(members,'saved',settings).map(e=><BoardEmployee key={e.id} employee={e} onDetails={onDetails}/>)}</div>
    </section>)}</div>
  </section>;
}
export function EmployeeGroups({employees,onEdit,onAttendance,onClock,busy,settings={}}){
  const [sort,setSort]=useState('saved'),[selected,setSelected]=useState('OFFICE'),[pages,setPages]=useState({});
  const directory=useRef(null),navigator=useRef(null);
  const groups=useMemo(()=>Object.entries(employees.reduce((out,e)=>{(out[employeeLocation(e)+' / '+(productionSection(e)?'PRODUCTION · '+productionSection(e):e.department||'Unassigned')]||=[]).push(e);return out},{})).sort(([a],[b])=>departmentOrder(a,b)),[employees]);
  const signature=employees.map(e=>e.id).join('|');
  useEffect(()=>setPages({}),[signature,sort,settings.employee_sort,settings.employee_order?.join('|')]);
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
    <div className="group-view-toolbar"><span><Users size={16}/>{groups.length} groups · {employees.length} employees</span><label><ArrowUpDown size={15}/>Sort people<select aria-label="Sort employee cards" value={sort} onChange={e=>setSort(e.target.value)}><option value="saved">Saved display order</option><option value="manual">Manual order</option><option value="name">Name A–Z</option><option value="team">Team & production line</option><option value="role">Role seniority</option><option value="status">Clocked in first</option></select></label></div>
    <nav ref={navigator} className="department-navigator" aria-label="Department shortcuts">{groups.map(([dept,people])=><button key={dept} className={active===dept?'current':''} onClick={()=>choose(dept)} aria-pressed={active===dept}>{dept}<span>{people.length}</span></button>)}</nav>
    <div ref={directory} className="employee-departments compact-directory">{displayedGroups.map(([department,people],i)=>{
      const open=active===department, page=Math.min(pages[department]||0,Math.max(0,Math.ceil(people.length/pageSize)-1));
      return <section className={'department-card '+(open?'department-open':'')} key={department}>
        <button className="department-card-heading" onClick={()=>open?setSelected(null):choose(department)} aria-expanded={open}><span className="department-symbol"><Users size={20}/></span><div><h2>{department}</h2><small>{people.length} people · {people.filter(e=>e.status==='IN').length} currently in</small></div><ChevronDown size={18} className={!open?'collapsed':''}/></button>
        <div className={'department-collapse '+(open?'is-open':'')} aria-hidden={!open} inert={!open?true:undefined}><div className="department-collapse-inner"><div className="department-staff">{sortPeople(people,sort,settings).slice(page*pageSize,(page+1)*pageSize).map(e=><article className="staff-card" key={e.id}><div className="staff-card-top"><Photo employee={e}/><div className="staff-identity"><strong title={e.name}>{e.nickname||e.name}</strong><small>{e.id}</small></div><span className={'staff-status '+(e.status==='IN'?'in':'out')}><i/>{e.status}</span></div><div className="staff-details"><span>{e.position||'Employee'}{e.line?' · '+e.line:''}{e.office_department?' · '+e.office_department:''}{productionSection(e)&&productionSection(e)!==e.line?.trim().toUpperCase()?' · '+productionSection(e):''}</span><span>{e.team?'Team '+e.team:'No team'} · {e.effective_schedule?`${e.effective_schedule.start}–${e.effective_schedule.end}`:'Hours unassigned'}</span></div><small className="staff-sync" role="status">Details: {syncLabel(e.metadata_sync?.status)}</small><div className="staff-actions"><button aria-label={'Edit '+e.name} onClick={()=>onEdit(e)}><Pencil size={13}/>Profile</button>{onAttendance&&<button aria-label={'Update attendance for '+e.name} onClick={()=>onAttendance(e)}><Pencil size={13}/>Edit attendance</button>}{e.active&&onClock&&<button className={"quick-clock "+(e.status==='IN'?'clock-out':'clock-in')} disabled={busy} aria-label={(e.status==='IN'?'Clock out ':'Clock in ')+e.name} onClick={()=>onClock(e)}><Clock3 size={13}/>{e.status==='IN'?'Clock out':'Clock in'}</button>}</div></article>)}</div><footer className="department-pagination"><span>Showing {page*pageSize+1}–{Math.min((page+1)*pageSize,people.length)} of {people.length} employees</span><div><button disabled={page===0} onClick={()=>setPages({...pages,[department]:page-1})} aria-label={'Previous '+department+' employees'}>Previous</button><span>{page+1} / {Math.ceil(people.length/pageSize)}</span><button disabled={(page+1)*pageSize>=people.length} onClick={()=>setPages({...pages,[department]:page+1})} aria-label={'Next '+department+' employees'}>Next</button></div></footer></div></div>
      </section>;
    })}</div>{!employees.length&&<div className="empty"><Search size={30}/><h3>No matching employees</h3><p>Try a different search or filter.</p></div>}
  </>;
}

export function LiveBoard({employees,settings={},live,onDetails,soundControl,onAdminControls,detailsOpen=false}){
  const [query,setQuery]=useState(''),[onlyIn,setOnlyIn]=useState(false),[fit,setFit]=useState(false),[fullscreen,setFullscreen]=useState(false);
  const [mode,setMode]=useState('large'),[page,setPage]=useState(0),[rotating,setRotating]=useState(true),[dimensions,setDimensions]=useState({width:1200,height:600});
  const root=useRef(null),stage=useRef(null),windowRef=useRef(null);
  const people=useMemo(()=>employees.filter(e=>(!onlyIn||e.status==='IN')&&(!query||[e.name,e.nickname,e.id,e.department,e.line,e.position,e.office_department,productionSection(e)].some(s=>s?.toLowerCase().includes(query.toLowerCase())))),[employees,onlyIn,query]);
  const groups=useMemo(()=>Object.entries(people.reduce((out,e)=>{(out[boardGroupName(e)]||=[]).push(e);return out},{})).sort(([a],[b])=>boardGroupOrder(a,b)).map(([name,workers])=>[name,sortPeople(workers,'saved',settings).sort((a,b)=>name==='OFFICE'?0:(a.team||'').localeCompare(b.team||''))]),[people,settings.employee_sort,settings.employee_order]);
  const pages=useMemo(()=>paginateBoard(groups,dimensions),[groups,dimensions]);
  const currentPage=Math.min(page,pages.length-1),shown=fit&&mode==='large'?pages[currentPage]:groups;
  const shownCount=shown.reduce((sum,[,workers])=>sum+workers.length,0);
  useEffect(()=>{const listener=()=>{const active=document.fullscreenElement===root.current;setFullscreen(active);if(active){setFit(true);setQuery('');setOnlyIn(false)}};document.addEventListener('fullscreenchange',listener);return()=>document.removeEventListener('fullscreenchange',listener)},[]);
  useLayoutEffect(()=>{
    let frame;const measure=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{
      if(!windowRef.current)return;const width=Math.floor(windowRef.current.clientWidth),height=Math.max(1,Math.floor(windowRef.current.clientHeight)-6);
      setDimensions(previous=>previous.width===width&&previous.height===height?previous:{width,height});
      if(!stage.current)return;
      if(mode!=='all'||!fit){stage.current.removeAttribute('style');return;}
      const values={'--board-card-height':'34px','--board-card-width':'112px','--board-photo-size':'21px','--board-name-size':'9px','--board-position-size':'7px'};
      Object.entries(values).forEach(([key,value])=>stage.current.style.setProperty(key,value));
      let low=.05,high=1;
      for(let i=0;i<14;i++){const candidate=(low+high)/2;stage.current.style.width=(width/candidate)+'px';if(stage.current.scrollHeight*candidate<=height)low=candidate;else high=candidate;}
      stage.current.style.width=(width/low)+'px';stage.current.style.setProperty('--compact-transform','scale('+low+')');
    })};
    const observer=new ResizeObserver(measure);observer.observe(root.current);observer.observe(windowRef.current);measure();return()=>{observer.disconnect();cancelAnimationFrame(frame)};
  },[fit,mode,groups]);
  useEffect(()=>{if(!fit||mode!=='large'||pages.length<2||!rotating||detailsOpen)return;const timer=setInterval(()=>setPage(previous=>(previous+1)%pages.length),15000);return()=>clearInterval(timer);},[fit,mode,pages.length,rotating,detailsOpen]);
  async function toggleFullscreen(){if(fullscreen){if(document.fullscreenElement)await document.exitFullscreen();else setFullscreen(false);return;}setFit(true);setQuery('');setOnlyIn(false);try{await root.current.requestFullscreen()}catch{setFullscreen(true)}}
  async function admin(){if(document.fullscreenElement)await document.exitFullscreen();setFullscreen(false);onAdminControls?.();}
  return <section ref={root} className={'board-page redesigned-board '+(fit?'fit-all ':'')+(fullscreen?'tv-mode ':'')+(mode==='large'?'large-photo-board':'native-overview-board')}>
    <header className="board-header"><div className="board-brand"><img src="/1.png" alt="Sugihara"/><div><h2>Digital Attendance</h2><small>Port Klang · attendance workspace</small></div></div><div className="board-totals"><div><b>{employees.length}</b><small>Employees</small></div><div><b>{employees.filter(e=>e.status==='IN').length}</b><small>Currently in</small></div><span className={'badge '+(live?'green':'amber')}>{live?'Live':'Reconnecting'}</span>{soundControl}<button className="secondary" onClick={()=>{setMode(mode==='large'?'all':'large');setFit(true);setPage(0)}}>{mode==='large'?'Compact overview':'Large photos'}</button><button className="secondary" onClick={toggleFullscreen}>{fullscreen?<Minimize2 size={15}/>:<Monitor size={15}/>} {fullscreen?'Exit TV':'TV fullscreen'}</button>{onAdminControls&&<button className="primary" onClick={admin}>Admin controls</button>}</div></header>
    {!fullscreen&&<div className="board-toolbar"><div className="search"><Search size={17}/><input aria-label="Search live board" placeholder="Find a person, department or line…" value={query} onChange={e=>{setQuery(e.target.value);setPage(0)}}/></div><label className="checkbox-label"><input type="checkbox" checked={onlyIn} onChange={e=>{setOnlyIn(e.target.checked);setPage(0)}}/>Show clocked-in employees only</label><button className="secondary" onClick={()=>setFit(!fit)}>{fit?'Scrollable view':'Fit screen'}</button></div>}
    <div className="board-stage-window" ref={windowRef}><div className="board-stage" ref={stage}>{shown.map(([name,workers])=><BoardRow key={name} name={name} workers={workers} settings={settings} onDetails={onDetails}/>)}</div></div>
    {fit&&mode==='large'&&<div className="tv-fit-footer"><strong>{mode==='large'?shownCount+' of '+people.length+' employees · Larger photos':people.length+' employees · Compact overview'}</strong>{mode==='large'&&<div className="board-page-controls"><button disabled={pages.length<2} onClick={()=>setPage((currentPage+pages.length-1)%pages.length)} aria-label="Previous TV page">Previous</button><span>Page {currentPage+1} / {pages.length}</span><button disabled={pages.length<2} onClick={()=>setPage((currentPage+1)%pages.length)} aria-label="Next TV page">Next</button><button onClick={()=>setRotating(!rotating)}>{rotating?'Pause rotation':'Resume rotation'}</button></div>}<span>View only · Click a card for details</span></div>}
  </section>;
}
