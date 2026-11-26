import {shiftBoardState} from './checksheet-shift.js';
import './checksheet-shift.css';
import './board-admin.css';
import {filterBoardPlant} from './plant-view.js';
import {employeeLocation} from './transfer-utils.js';
import {syncLabel} from './employee-sync.js';
import {paginateBoard,isOfficeGroup,teamColumnWeight,visibleBoardTeams,orderBoardGroups} from './board-layout.js';
import {productionSection,sortEmployees,employeeGroup} from './organisation.js';
import {normalizeLayout,layoutGroups,moveGroup,orderCards,moveCardOrder} from './custom-layout.js';
import {LayoutEditor,LayoutGroup,LayoutCard} from './layout-editor.jsx';
import React,{useState,useMemo,useRef,useLayoutEffect,useEffect} from 'react';
import {Users,Pencil,Clock3,Search,Monitor,Minimize2,Maximize2,ArrowUpDown,ChevronDown,LogIn,LogOut,LockKeyhole,X} from 'lucide-react';
import {Morph} from './ui-kit.jsx';

export function Photo({employee}){
  const [failed,setFailed]=useState(false);
  useEffect(()=>setFailed(false),[employee.photo_url]);
  return <span className="staff-photo">{employee.photo_url&&!failed?<img src={employee.photo_url} alt="" loading="lazy" onError={()=>setFailed(true)}/>:employee.name.split(' ').slice(0,2).map(n=>n[0]).join('')}</span>;
}
export function sortPeople(people,sort,settings={}){
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
  const shift=shiftBoardState(e);
  const role=e.position==='SUPERVISOR'?'SUP':e.position==='LEADER'?'LDR':null;
  return <button className={'tv-employee '+(e.status==='IN'?'in':'out')+(shift.finished?' shift-finished':'')} title={[e.name,e.position,e.office_department].filter(Boolean).join(' · ')+' · '+shift.label+' · '+shift.detail+' · View details'} aria-label={'View details for '+e.name} onClick={()=>onDetails?.(e)}>
    <Photo employee={e}/><div className="tv-card-name"><strong>{e.nickname||e.name}</strong><small>{e.position||'Employee'}{e.department?.trim().toUpperCase()==='OFFICE'&&e.office_department?' · '+e.office_department:''}</small></div><span className="tv-card-meta"><b>{e.status}</b>{shift.label&&<em className="shift-board-label">{shift.label}</em>}{role&&<em>{role}</em>}</span>
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
function BoardRow({name,workers,onDetails,settings,sort='position',cardLayout,editing=false,onCardSize,onCardMove}){
  const office=isOfficeGroup(name,workers);
  const label=productionSection(workers[0])?(workers[0].line?.trim()||'Line unassigned'):(workers[0]?.department||'Department unassigned');
  const teams=office?[['',workers]]:visibleBoardTeams(workers);
  const cards=members=>{
    const sorted=sortPeople(members,sort,settings),arranged=cardLayout?orderCards(sorted,cardLayout.cardOrder):sorted,ids=arranged.map(e=>e.id);
    return arranged.map(e=>cardLayout?<LayoutCard key={e.id} employee={e} layout={cardLayout} editing={editing} teamIds={ids} onSize={onCardSize} onMove={onCardMove}><BoardEmployee employee={e} onDetails={onDetails}/></LayoutCard>:<BoardEmployee key={e.id} employee={e} onDetails={onDetails}/>);
  };
  return <section className={'tv-department board-group '+(office?'office-group':'shift-group')+(teams.length===1?' single-team':'')} aria-label={name}>
    <div className="tv-department-title" title={name}><h3>{label}</h3><small><b>{workers.filter(e=>e.status==='IN').length}</b> / {workers.length}</small>{!office&&teams.length===1&&<span className="board-solo-team">{teams[0][0]==='N'?'Normal hours':teams[0][0]}</span>}</div>
    <div className="board-group-teams" style={office?undefined:{gridTemplateColumns:teams.map(([team])=>`minmax(0, ${(teams.length===1?1:teamColumnWeight(team))}fr)`).join(' ')}}>{teams.map(([team,members])=><section className={'board-team-row '+(office?'office-row':'shift-team-'+team.toLowerCase())+(!members.length?' empty-shift':'')} key={team} aria-label={office?'Office employees':team==='Unassigned'?'Team unassigned':'Team '+team}>
      {!office&&<h4 className={'board-team-strip team-'+team.toLowerCase()} title={team==='N'?'Normal working hours':team==='Unassigned'?'Team unassigned':'Team '+team}><span>{team==='Unassigned'?'Unassigned':'Team '+team}</span><small>{members.length?members.filter(e=>e.status==='IN').length+' / '+members.length:'—'}</small></h4>}
      <div className="tv-department-people">{cards(members)}{!members.length&&<span className="board-empty-team">—</span>}</div>
    </section>)}</div>
  </section>;
}
function BoardSignIn({onSubmit,onClose}){
  const [password,setPassword]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  async function submit(event){event.preventDefault();setBusy(true);setError('');try{await onSubmit(password)}catch(e){setError(e.message);setPassword('')}finally{setBusy(false)}}
  return <div className="modal-backdrop board-admin-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><form className="modal board-admin-modal" role="dialog" aria-modal="true" aria-label="Sign in to adjust attendance" onSubmit={submit}>
    <header><div><h2>Admin sign-in</h2><p>Sign in to clock people in or out from the board. It locks again after 30 minutes.</p></div><button type="button" className="icon-button" aria-label="Close" onClick={onClose}><X size={20}/></button></header>
    <div className="modal-body"><label>Administrator password<input autoFocus autoComplete="current-password" type="password" value={password} onChange={e=>setPassword(e.target.value)} required/></label>{error&&<p className="board-admin-error" role="alert">{error}</p>}</div>
    <footer className="modal-footer"><button type="button" className="secondary" onClick={onClose}>Cancel</button><button className="primary" disabled={busy||!password}>{busy?'Signing in…':'Sign in'}</button></footer>
  </form></div>;
}
function BoardClockAction({employee:e,onClock,onDetails,onClose}){
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const next=e.status==='IN'?'OUT':'IN',shift=shiftBoardState(e);
  async function clock(){setBusy(true);setError('');try{await onClock(e,next);onClose()}catch(err){setError(err.message)}finally{setBusy(false)}}
  return <div className="modal-backdrop board-admin-backdrop" onMouseDown={ev=>{if(ev.target===ev.currentTarget&&!busy)onClose()}}><section className="modal board-admin-modal" role="dialog" aria-modal="true" aria-label={'Adjust attendance for '+e.name}>
    <header><div className="board-admin-person"><Photo employee={e}/><div><h2>{e.nickname||e.name}</h2><p>{[e.id,e.position,e.department].filter(Boolean).join(' · ')}</p></div></div><button className="icon-button" aria-label="Close" disabled={busy} onClick={onClose}><X size={20}/></button></header>
    <div className="modal-body"><p>Currently <b className={'board-admin-status '+(e.status==='IN'?'in':'out')}>{e.status}</b>{shift.label?' · '+shift.label:''}</p>{error&&<p className="board-admin-error" role="alert">{error}</p>}</div>
    <footer className="modal-footer"><button className="secondary" disabled={busy} onClick={()=>{onClose();onDetails?.(e)}}>View details</button><button className={'primary board-admin-clock '+next.toLowerCase()} disabled={busy} onClick={clock}>{next==='IN'?<LogIn size={16}/>:<LogOut size={16}/>} {busy?'Saving…':'Clock '+next}</button></footer>
  </section></div>;
}

// TV mode survives a reload (an app update, a power blip) through sessionStorage, or a ?tv link for a kiosk browser shortcut.
function tvRequested(){try{return new URLSearchParams(window.location.search).has('tv')||sessionStorage.getItem('attendance-tv-mode')==='1'}catch{return false}}

export function LiveBoard({employees,settings={},live,onDetails,soundControl,onAdminControls,detailsOpen=false,plant='',api,onRefresh,layouts={},clockUnlocked=false,onUnlocked,onClock}){
  const canAdjust=!!(onClock&&onUnlocked);
  const [signIn,setSignIn]=useState(false),[selected,setSelected]=useState(null),[unlockedUntil,setUnlockedUntil]=useState(null);
  useEffect(()=>{if(!canAdjust)return;api('/clock-access').then(d=>{onUnlocked(!!d.unlocked);setUnlockedUntil(d.expires_at||null)}).catch(()=>onUnlocked(false))},[]);
  useEffect(()=>{if(!clockUnlocked||!unlockedUntil)return;const timer=setTimeout(()=>{onUnlocked(false);setSelected(null)},Math.max(0,unlockedUntil*1000-Date.now()));return()=>clearTimeout(timer)},[clockUnlocked,unlockedUntil]);
  async function unlockBoard(password){const r=await api('/auth/unlock-attendance','POST',{password});setUnlockedUntil(r.expires_at||null);onUnlocked(true);setSignIn(false)}
  async function lockBoard(){try{await api('/clock-access','DELETE')}catch{}onUnlocked(false);setSelected(null)}
  async function clockFromBoard(employee,action){try{return await onClock(employee,action)}catch(e){if(e.status===403){onUnlocked(false);setSelected(null);setSignIn(true)}throw e}}
  const selectedEmployee=selected&&employees.find(e=>e.id===selected);
  const [query,setQuery]=useState(''),[onlyIn,setOnlyIn]=useState(false),[fit,setFit]=useState(tvRequested),[fullscreen,setFullscreen]=useState(tvRequested),[resume,setResume]=useState(false);
  useEffect(()=>{try{sessionStorage.setItem('attendance-tv-mode',fullscreen?'1':'0')}catch{}},[fullscreen]);
  const [mode,setMode]=useState('large'),[page,setPage]=useState(0),[rotating,setRotating]=useState(true),[dimensions,setDimensions]=useState({width:1200,height:600});
  const [boardPlant,setBoardPlant]=useState(()=>{try{return localStorage.getItem('attendance-board-plant')||'PORT KLANG'}catch{return 'PORT KLANG'}});
  const locations=[...new Set(employees.map(employeeLocation))].sort(),chosen=plant||(boardPlant==='*'||locations.includes(boardPlant)?boardPlant:'*');
  const visibleEmployees=filterBoardPlant(employees,chosen);
  const layoutKey=chosen==='*'?'':chosen,saved=layouts[layoutKey];
  const [draft,setDraft]=useState(null),[editVersion,setEditVersion]=useState(''),[layoutBusy,setLayoutBusy]=useState(false),[layoutError,setLayoutError]=useState('');
  const layout=normalizeLayout(draft||saved?.layout),custom=!!draft||layout.enabled;
  const editing=!!draft;
  useEffect(()=>{setDraft(null);setLayoutError('')},[layoutKey]);
  const updateDraft=value=>setDraft(normalizeLayout(value));
  const resizeCard=(id,size)=>setDraft(previous=>{
    const cards={...previous.cards};if(size)cards[id]=size;else delete cards[id];
    return normalizeLayout({...previous,enabled:true,cards});
  });
  const moveCard=(ids,source,target)=>setDraft(previous=>normalizeLayout({...previous,enabled:true,cardOrder:moveCardOrder(previous.cardOrder,ids,source,target)}));
  async function editLayout(){setLayoutBusy(true);setLayoutError('');try{const latest=await api('/board-layout?base='+encodeURIComponent(layoutKey));setDraft(normalizeLayout(latest.layout));setEditVersion(latest.version);setQuery('');setOnlyIn(false)}catch(e){setLayoutError(e.message)}finally{setLayoutBusy(false)}}
  async function saveLayout(){setLayoutBusy(true);setLayoutError('');try{await api('/board-layout','PUT',{base:layoutKey,layout,version:editVersion});await onRefresh();setDraft(null)}catch(e){setLayoutError(e.message)}finally{setLayoutBusy(false)}}
  function changePlant(value){setBoardPlant(value);setPage(0);try{localStorage.setItem('attendance-board-plant',value)}catch{}}
  const root=useRef(null),stage=useRef(null),windowRef=useRef(null);
  const people=useMemo(()=>visibleEmployees.filter(e=>(!onlyIn||e.status==='IN')&&(!query||[e.name,e.nickname,e.id,e.department,e.line,e.position,e.office_department,productionSection(e)].some(s=>s?.toLowerCase().includes(query.toLowerCase())))),[employees,chosen,onlyIn,query]);
  const groups=useMemo(()=>{
    const collect=rows=>Object.entries(rows.reduce((out,e)=>{(out[boardGroupName(e)]||=[]).push(e);return out},{}));
    const grouped=collect(people).sort(([a],[b])=>boardGroupOrder(a,b));
    return orderBoardGroups(grouped,collect(visibleEmployees)).map(([name,workers])=>[name,sortPeople(workers,'position').sort((a,b)=>isOfficeGroup(name,workers)?0:(a.team||'').localeCompare(b.team||''))]);
  },[people,employees,chosen]);
  const pages=useMemo(()=>paginateBoard(groups,dimensions),[groups,dimensions]);
  const currentPage=Math.min(page,pages.length-1),shown=custom?layoutGroups(groups,layout).filter(([name])=>editing||!layout.groups[name]?.hidden):fit&&mode==='large'?pages[currentPage]:groups;
  const groupNames=layoutGroups(groups,layout).map(([name])=>name);
  const shownCount=shown.reduce((sum,[,workers])=>sum+workers.length,0);
  // Browsers drop full screen on every reload and only allow it back after a click or key press.
  // Until then the board still fills the window, the page behind it cannot scroll, and the next click restores full screen.
  useEffect(()=>{
    const html=document.documentElement;
    if(!fullscreen){setResume(false);return}
    html.classList.add('tv-locked');
    if(document.fullscreenElement||!document.fullscreenEnabled)return()=>html.classList.remove('tv-locked');
    setResume(true);
    const again=event=>{
      if(document.fullscreenElement||event.target?.closest?.('button,a,input,select,textarea,[role="dialog"]'))return;
      root.current?.requestFullscreen?.().then(()=>setResume(false)).catch(()=>{});
    };
    window.addEventListener('pointerdown',again);window.addEventListener('keydown',again);
    return()=>{html.classList.remove('tv-locked');window.removeEventListener('pointerdown',again);window.removeEventListener('keydown',again)};
  },[fullscreen]);
  useEffect(()=>{const listener=()=>{const active=document.fullscreenElement===root.current;setFullscreen(active);if(active){setFit(true);setQuery('');setOnlyIn(false)}};document.addEventListener('fullscreenchange',listener);return()=>document.removeEventListener('fullscreenchange',listener)},[]);
  useLayoutEffect(()=>{
    let frame;const measure=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{
      if(!windowRef.current||document.visibilityState==='hidden')return;const width=Math.floor(windowRef.current.clientWidth),height=Math.max(1,Math.floor(windowRef.current.clientHeight)-6);
      // Skip the in-between sizes a window passes through while entering or leaving full screen.
      if(width<200||height<120)return;
      setDimensions(previous=>previous.width===width&&previous.height===height?previous:{width,height});
      if(!stage.current||custom)return;
      if(mode!=='all'||!fit){stage.current.removeAttribute('style');return;}
      const values={'--board-card-height':'38px','--board-card-width':'146px','--board-photo-size':'26px','--board-name-size':'11px','--board-position-size':'8px'};
      Object.entries(values).forEach(([key,value])=>stage.current.style.setProperty(key,value));
      let low=.05,high=1;
      for(let i=0;i<14;i++){const candidate=(low+high)/2;stage.current.style.width=(width/candidate)+'px';if(stage.current.scrollHeight*candidate<=height)low=candidate;else high=candidate;}
      stage.current.style.width=(width/low)+'px';stage.current.style.setProperty('--compact-transform','scale('+low+')');
    })};
    const observer=new ResizeObserver(measure);observer.observe(root.current);observer.observe(windowRef.current);measure();
    // Re-measure once fonts load and whenever the screen changes size or the tab comes back, so a reload never keeps a stale fit.
    let live=true;document.fonts?.ready.then(()=>{if(live)measure()});
    window.addEventListener('resize',measure);document.addEventListener('fullscreenchange',measure);document.addEventListener('visibilitychange',measure);
    return()=>{live=false;observer.disconnect();cancelAnimationFrame(frame);window.removeEventListener('resize',measure);document.removeEventListener('fullscreenchange',measure);document.removeEventListener('visibilitychange',measure)};
  },[fit,mode,groups,custom]);
  useEffect(()=>{if(custom||!fit||mode!=='large'||pages.length<2||!rotating||detailsOpen||signIn||selected)return;const timer=setInterval(()=>setPage(previous=>(previous+1)%pages.length),15000);return()=>clearInterval(timer);},[fit,mode,pages.length,rotating,detailsOpen,custom,signIn,selected]);
  async function toggleFullscreen(){if(fullscreen){if(document.fullscreenElement)await document.exitFullscreen();else setFullscreen(false);return;}setFit(true);setQuery('');setOnlyIn(false);try{await root.current.requestFullscreen()}catch{setFullscreen(true)}}
  async function admin(){if(document.fullscreenElement)await document.exitFullscreen();setFullscreen(false);onAdminControls?.();}
  return <section ref={root} data-update-blocked={editing} className={'board-page redesigned-board '+(fit?'fit-all ':'')+(fullscreen?'tv-mode ':'')+(custom?'custom-grid-board':mode==='large'?'large-photo-board':'native-overview-board')}>
    {resume&&<p className="tv-resume" role="status">Click anywhere on the board to fill the screen again</p>}<header className="board-header"><div className="board-brand"><img src="/1.png" alt="Sugihara"/><div><h2>Digital Attendance</h2><small>{chosen==='*'?'All plants':chosen}</small></div></div><div className="board-totals">{settings.checksheet_sync&&settings.checksheet_sync.state!=='disabled'&&<span className={settings.checksheet_sync.state==='live'?'checksheet-sync-live':'checksheet-sync-warning'}>{settings.checksheet_sync.state==='live'?'Checksheet shifts linked':'Checksheet shift sync unavailable'}</span>}{!plant&&<label className="board-plant-select">Plant<select disabled={editing||layoutBusy} aria-label="TV board plant" value={chosen} onChange={e=>changePlant(e.target.value)}><option value="*">All plants</option>{locations.map(p=><option key={p}>{p}</option>)}</select></label>}<div><b>{visibleEmployees.length}</b><small>Employees</small></div><div><b>{visibleEmployees.filter(e=>e.status==='IN').length}</b><small>Currently in</small></div><span className={'badge '+(live?'green':'amber')}>{live?'Live':'Reconnecting'}</span>{soundControl}{!custom&&<button className="secondary" onClick={()=>{setMode(mode==='large'?'all':'large');setFit(true);setPage(0)}}>{mode==='large'?'Compact overview':'Large photos'}</button>}{fullscreen&&!editing&&<button className="secondary" disabled={layoutBusy} onClick={editLayout}>Edit layout</button>}<button className="secondary" onClick={toggleFullscreen}>{fullscreen?<Minimize2 size={15}/>:<Monitor size={15}/>} {fullscreen?'Exit TV':'TV fullscreen'}</button>{canAdjust?(clockUnlocked?<><button className="secondary" disabled={editing} onClick={lockBoard}><LockKeyhole size={15}/> Lock board</button>{onAdminControls&&<button className="primary" disabled={editing} onClick={admin}>Full controls</button>}</>:<button className="primary" disabled={editing} onClick={()=>setSignIn(true)}>Admin controls</button>):onAdminControls&&<button className="primary" disabled={editing} onClick={admin}>Admin controls</button>}</div></header>
    {!fullscreen&&<div className="board-toolbar"><div className="search"><Search size={17}/><input aria-label="Search live board" disabled={editing} placeholder="Find a person, department or line…" value={query} onChange={e=>{setQuery(e.target.value);setPage(0)}}/></div><label className="checkbox-label"><input type="checkbox" disabled={editing} checked={onlyIn} onChange={e=>{setOnlyIn(e.target.checked);setPage(0)}}/>Show clocked-in employees only</label>{!custom&&<button className="secondary" onClick={()=>setFit(!fit)}>{fit?'Scrollable view':'Fit screen'}</button>}{!editing&&<button className="secondary" disabled={layoutBusy} onClick={editLayout}>Edit layout</button>}</div>}
    {clockUnlocked&&canAdjust&&!editing&&<div className="board-admin-banner" role="status"><LockKeyhole size={15}/> Admin signed in · Tap any card to clock that person in or out</div>}
    {layoutError&&!editing&&<p role="alert">{layoutError}</p>}
    {editing&&<LayoutEditor layout={layout} fullscreen={fullscreen} onChange={updateDraft} onSave={saveLayout} onCancel={()=>{setDraft(null);setLayoutError('')}} busy={layoutBusy} error={layoutError} conflict={!!saved?.version&&saved.version!==editVersion}/>}
    {custom&&<div className="layout-caption">{editing?'Layout preview': 'Shared layout'} · {shownCount} of {people.length} matching employees{people.length>shownCount?' · Some groups are hidden':''} · Positions shown below names</div>}
    <div className="board-stage-window" ref={windowRef}><div className="board-stage" ref={stage} style={custom?{'--layout-columns':layout.columns,'--layout-gap':layout.gap+'px','--board-card-width':layout.cardWidth+'px','--board-card-height':layout.cardHeight+'px','--board-photo-size':layout.photoSize+'px','--board-name-size':layout.fontSize+'px','--board-position-size':Math.max(9,layout.fontSize-2)+'px','--board-card-gap':'6px','--board-grid-padding':'6px'}:undefined}>{shown.map(([name,workers])=>{
      const row=<BoardRow name={name} workers={workers} settings={settings} sort={custom?layout.sort:'position'} onDetails={editing?undefined:clockUnlocked&&canAdjust?(e=>setSelected(e.id)):onDetails} cardLayout={custom?layout:undefined} editing={editing} onCardSize={resizeCard} onCardMove={moveCard}/>;
      return custom?<LayoutGroup key={name} name={name} config={layout.groups[name]} layout={layout} editing={editing} names={groupNames} onMove={(source,target)=>updateDraft({...layout,order:moveGroup(groupNames,source,target)})} onChange={config=>setDraft(previous=>normalizeLayout({...previous,groups:{...previous.groups,[name]:config}}))}>{row}</LayoutGroup>:<React.Fragment key={name}>{row}</React.Fragment>;
    })}{!shown.length&&<div className="empty">No visible groups. Use Edit layout to show hidden groups, or clear your filters.</div>}</div></div>
    {!custom&&fit&&mode==='large'&&<div className="tv-fit-footer"><strong>{shownCount+' of '+people.length+' employees · Larger photos'}</strong><div className="board-page-controls"><button disabled={pages.length<2} onClick={()=>setPage((currentPage+pages.length-1)%pages.length)} aria-label="Previous TV page">Previous</button><span>Page {currentPage+1} / {pages.length}</span><button disabled={pages.length<2} onClick={()=>setPage((currentPage+1)%pages.length)} aria-label="Next TV page">Next</button><button onClick={()=>setRotating(!rotating)}>{rotating?'Pause rotation':'Resume rotation'}</button></div><span>{clockUnlocked&&canAdjust?'Editing attendance · Tap a card to clock in or out':'View only · Click a card for details'}</span></div>}
    {signIn&&<BoardSignIn onSubmit={unlockBoard} onClose={()=>setSignIn(false)}/>}
    {selectedEmployee&&clockUnlocked&&<BoardClockAction employee={selectedEmployee} onClock={clockFromBoard} onDetails={onDetails} onClose={()=>setSelected(null)}/>}
  </section>;
}
