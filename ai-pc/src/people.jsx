import React,{useEffect,useMemo,useRef,useState} from 'react';
import {Search,X,ArrowUpDown,Pencil,LogIn,LogOut,Users,ArrowLeft} from 'lucide-react';
import {Photo,sortPeople,departmentOrder} from './workforce.jsx';
import {shiftBoardState} from './checksheet-shift.js';
import {employeeLocation} from './transfer-utils.js';
import {productionSection} from './organisation.js';
import {Morph} from './ui-kit.jsx';

const GROUP_KEY='attendance-people-group';
const PREVIEW=12;

const groupOf=e=>productionSection(e)?'PRODUCTION · '+productionSection(e):(e.department||'Unassigned');

// Filters sit in one always-visible bar. Only the filters that can narrow the list are shown.
export function PeopleFilters({employees,filters,setFilters,departments,teams,matches,showArchived}){
  const {search,location,department,team,section,officeDepartment,status}=filters;
  const locations=[...new Set(employees.map(employeeLocation))].sort();
  const offices=[...new Set(employees.filter(e=>e.department?.trim().toUpperCase()==='OFFICE').map(e=>e.office_department).filter(Boolean))].sort();
  const narrowed=search||[location,department,team,section,officeDepartment,status].some(v=>v!=='all');
  const set=(key,value)=>setFilters({[key]:value});
  return <div className="people-filters" role="search">
    <label className="people-search">
      <Search size={17} aria-hidden="true"/>
      <input aria-label="Search employees" placeholder="Search name, ID, line or position" value={search} onChange={e=>set('search',e.target.value)}/>
      {search&&<button type="button" className="people-search-clear" aria-label="Clear search" onClick={()=>set('search','')}><X size={15}/></button>}
    </label>
    <div className="people-selects">
      {locations.length>1&&<select aria-label="Plant" className={location!=='all'?'is-set':''} value={location} onChange={e=>set('location',e.target.value)}><option value="all">All plants</option>{locations.map(base=><option key={base}>{base}</option>)}</select>}
      <select aria-label="Department" className={department!=='all'?'is-set':''} value={department} onChange={e=>setFilters({department:e.target.value,officeDepartment:'all'})}><option value="all">All departments</option>{departments.map(d=><option key={d}>{d}</option>)}</select>
      {department.trim().toUpperCase()==='OFFICE'&&offices.length>0&&<select aria-label="Office department" className={officeDepartment!=='all'?'is-set':''} value={officeDepartment} onChange={e=>set('officeDepartment',e.target.value)}><option value="all">All office teams</option>{offices.map(name=><option key={name}>{name}</option>)}</select>}
      <select aria-label="Production section" className={section!=='all'?'is-set':''} value={section} onChange={e=>set('section',e.target.value)}><option value="all">All sections</option><option value="CONVERSION">Conversion</option><option value="ROLL MAKING">Roll making</option></select>
      <select aria-label="Team" className={team!=='all'?'is-set':''} value={team} onChange={e=>set('team',e.target.value)}><option value="all">All teams</option>{teams.map(t=><option key={t} value={t}>{t==='Unassigned'?'No team':'Team '+t}</option>)}</select>
      {!showArchived&&<select aria-label="Attendance status" className={status!=='all'?'is-set':''} value={status} onChange={e=>set('status',e.target.value)}><option value="all">In or out</option><option value="IN">Clocked in</option><option value="OUT">Clocked out</option></select>}
    </div>
    <p className="people-match" role="status">
      {narrowed?<>{matches} {matches===1?'person matches':'people match'}<button type="button" className="people-reset" onClick={()=>setFilters({search:'',location:'all',department:'all',team:'all',section:'all',officeDepartment:'all',status:'all'})}>Clear filters</button></>:<>{matches} {showArchived?'archived':'active'} {matches===1?'person':'people'}</>}
    </p>
  </div>;
}

function PersonCard({employee:e,onEdit,onAttendance,onClock,busy}){
  const shift=shiftBoardState(e);
  const section=productionSection(e);
  const role=[e.position||'Employee',e.line,e.office_department,section&&section!==e.line?.trim().toUpperCase()?section:null].filter(Boolean).join(' · ');
  return <article className={'person'+(shift.finished?' shift-finished':'')+(e.status==='IN'?' is-in':'')}>
    <button type="button" className="person-main" onClick={()=>onEdit(e)} aria-label={'Open profile for '+e.name}>
      <Photo employee={e}/>
      <span className="person-id"><strong title={e.name}>{e.nickname||e.name}</strong><small>{e.id}</small></span>
      <span className={'person-status '+(e.status==='IN'?'in':'out')}><Morph k={e.status}>{e.status==='IN'?'In':'Out'}</Morph></span>
    </button>
    <dl className="person-facts">
      <div><dt>Role</dt><dd>{role}</dd></div>
      <div><dt>Hours</dt><dd>{e.team?'Team '+e.team:'No team'} · {e.effective_schedule?`${e.effective_schedule.start}–${e.effective_schedule.end}`:'Not assigned'}</dd></div>
      {shift.label&&<div><dt>Today</dt><dd>{[shift.label,shift.detail].filter(Boolean).join(' ')}</dd></div>}
    </dl>
    {['pending','offline'].includes(e.metadata_sync?.status)&&<p className="person-sync">{e.metadata_sync.status==='pending'?'Profile change not on kiosks yet':'Kiosk offline, change waiting'}</p>}
    <div className="person-actions">
      <button type="button" onClick={()=>onEdit(e)}><Pencil size={13}/>Profile</button>
      {onAttendance&&<button type="button" onClick={()=>onAttendance(e)} aria-label={'Edit attendance for '+e.name}>Attendance</button>}
      {e.active&&onClock&&<button type="button" className={'person-clock '+(e.status==='IN'?'out':'in')} disabled={busy} aria-label={(e.status==='IN'?'Clock out ':'Clock in ')+e.name} onClick={()=>onClock(e)}><Morph k={e.status}>{e.status==='IN'?<><LogOut size={14}/>Clock out</>:<><LogIn size={14}/>Clock in</>}</Morph></button>}
    </div>
  </article>;
}

// Groups live in one index on the left (chips on phones). "Everyone" lists every group in turn.
export function PeopleDirectory({employees,settings={},onEdit,onAttendance,onClock,busy,filterKey=''}){
  const [sort,setSort]=useState('saved');
  const [selected,setSelected]=useState(()=>{try{return sessionStorage.getItem(GROUP_KEY)||'all'}catch{return 'all'}});
  const [expanded,setExpanded]=useState({});
  // A new search or filter looks across everyone, so results in other groups are never hidden.
  const lastFilter=useRef(filterKey);
  useEffect(()=>{if(lastFilter.current!==filterKey){lastFilter.current=filterKey;setSelected('all');setExpanded({})}},[filterKey]);
  const groups=useMemo(()=>{
    const map={};
    for(const e of employees)((map[employeeLocation(e)]||={})[groupOf(e)]||=[]).push(e);
    return Object.entries(map).sort(([a],[b])=>a.localeCompare(b)).map(([plant,byGroup])=>[plant,Object.entries(byGroup).sort(([a],[b])=>departmentOrder(a,b)).map(([name,people])=>({key:plant+' / '+name,plant,name,people}))]);
  },[employees]);
  const flat=groups.flatMap(([,list])=>list);
  const current=flat.some(g=>g.key===selected)?selected:'all';
  useEffect(()=>{try{sessionStorage.setItem(GROUP_KEY,current)}catch{/* optional */}},[current]);
  const choose=key=>{setSelected(key);setExpanded({})};
  const shown=current==='all'?flat:flat.filter(g=>g.key===current);
  const inCount=list=>list.filter(e=>e.status==='IN').length;
  const multiPlant=groups.length>1;
  const item=(id,label,people,plant)=>{
    const here=inCount(people);
    return <button key={id} type="button" className={'people-index-item'+(current===id?' is-current':'')} aria-current={current===id?'true':undefined} onClick={()=>choose(id)}>
      <span className="people-index-name">{plant&&<small>{plant}</small>}{label}</span>
      <span className="people-index-count">{people.length}</span>
      <span className="people-index-bar" aria-hidden="true"><i style={{width:people.length?(here/people.length*100)+'%':0}}/></span>
      <span className="visually-hidden">{here} clocked in</span>
    </button>;
  };
  if(!employees.length)return <div className="people-empty"><Search size={28}/><h3>No one matches these filters</h3><p>Change the search or clear the filters to see everyone again.</p></div>;
  return <div className="people-layout">
    <nav className="people-index" aria-label="Employee groups">
      {item('all','Everyone',employees)}
      {groups.map(([plant,list])=><div className="people-index-plant" key={plant}>
        {multiPlant&&<h3>{plant}</h3>}
        {list.map(g=>item(g.key,g.name,g.people,multiPlant?g.plant:null))}
      </div>)}
    </nav>
    <div className="people-results">
      <div className="people-results-bar">
        {current==='all'?<p><Users size={15}/>{flat.length} {flat.length===1?'group':'groups'}</p>:<button type="button" className="people-back" onClick={()=>choose('all')}><ArrowLeft size={15}/>Everyone</button>}
        <label><ArrowUpDown size={14}/><span>Sort</span><select aria-label="Sort people" value={sort} onChange={e=>setSort(e.target.value)}><option value="saved">Saved display order</option><option value="manual">Manual order</option><option value="name">Name A–Z</option><option value="team">Team & line</option><option value="role">Role seniority</option><option value="status">Clocked in first</option></select></label>
      </div>
      {shown.map(g=>{
        const people=sortPeople(g.people,sort,settings),limit=current==='all'&&!expanded[g.key]?PREVIEW:people.length;
        return <section className="people-group" key={g.key} aria-label={g.key}>
          <header>
            <h2>{g.name}</h2>
            <p>{multiPlant&&<span className="people-group-plant">{g.plant}</span>}<b>{inCount(g.people)}</b> in of {g.people.length}</p>
          </header>
          <div className="people-grid">{people.slice(0,limit).map(e=><PersonCard key={e.id} employee={e} onEdit={onEdit} onAttendance={onAttendance} onClock={onClock} busy={busy}/>)}</div>
          {people.length>limit&&<button type="button" className="people-more" onClick={()=>setExpanded({...expanded,[g.key]:true})}>Show all {people.length} in {g.name.toLowerCase()}</button>}
        </section>;
      })}
    </div>
  </div>;
}
