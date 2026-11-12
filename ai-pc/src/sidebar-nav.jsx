import React,{useEffect,useState} from 'react';
import {ChevronDown,LayoutDashboard,Clock3,Users,Settings2} from 'lucide-react';
import {SECTIONS} from './directory.jsx';
import {Tick} from './skeleton.jsx';

const ICONS={Today:LayoutDashboard,Attendance:Clock3,People:Users,Setup:Settings2};
const KEY='attendance-nav-open';

// Sidebar menu: each section is a parent row that folds open to its pages, drawn under a thin guide line.
// A section with a single page stays a plain row.
export function SidebarNav({nav,page,onNavigate,alerts=0}){
  const groups=SECTIONS.map(([name,ids])=>[name,nav.filter(item=>ids.includes(item[0]))]).filter(([,items])=>items.length);
  const current=groups.find(([,items])=>items.some(item=>item[0]===page))?.[0];
  const [open,setOpen]=useState(()=>{try{return JSON.parse(sessionStorage.getItem(KEY)||'{}')}catch{return {}}});
  useEffect(()=>{if(current)setOpen(previous=>previous[current]===undefined?{...previous,[current]:true}:previous)},[current]);
  const expanded=name=>open[name]??name===current;
  function toggle(name){
    setOpen(previous=>{const next={...previous,[name]:!(previous[name]??name===current)};try{sessionStorage.setItem(KEY,JSON.stringify(next))}catch{/* optional */}return next});
  }
  const count=id=>id==='attention'&&alerts>0?<span className="nav-count alert"><Tick value={alerts}/></span>:null;
  return <>{groups.map(([name,items])=>{
    if(items.length===1){
      const [id,label,Icon]=items[0];
      return <button key={name} className={'nav-leaf-flat'+(page===id?' selected':'')} aria-current={page===id?'page':undefined} onClick={()=>onNavigate(id)}>{page===id&&<span className="nav-pill"/>}<Icon size={19}/>{label}{count(id)}</button>;
    }
    const Icon=ICONS[name],isOpen=expanded(name),active=name===current;
    return <div key={name} className={'nav-group'+(isOpen?' is-open':'')+(active?' has-active':'')}>
      <button className="nav-parent" aria-expanded={isOpen} onClick={()=>toggle(name)}>
        <Icon size={19}/><span>{name}</span>
        {!isOpen&&items.some(item=>item[0]==='attention')&&alerts>0&&<span className="nav-count alert">{alerts}</span>}
        <span className="nav-chevron"><ChevronDown size={15}/></span>
      </button>
      <div className="nav-sub" inert={!isOpen?true:undefined}><ul>{items.map(([id,label])=><li key={id}>
        <button className={'nav-leaf'+(page===id?' selected':'')} aria-current={page===id?'page':undefined} onClick={()=>onNavigate(id)}>{page===id&&<span className="nav-pill"/>}<span>{label}</span>{count(id)}</button>
      </li>)}</ul></div>
    </div>;
  })}</>;
}
