import React,{useEffect,useRef,useState} from 'react';
import {ChevronRight,ChevronDown,Home} from 'lucide-react';

// Where each page lives. The header shows "plant › section › page", and the page crumb opens its siblings.
export const SECTIONS=[['Dashboard',['overview','attention','board']],['Attendance',['clock','attendance','audit']],['People',['employees']],['Setup',['control','roster','settings']]];

export function Directory({root,page,nav,onNavigate}){
  const [open,setOpen]=useState(false),box=useRef(null);
  const section=SECTIONS.find(([,ids])=>ids.includes(page)),current=nav.find(n=>n[0]===page);
  const siblings=nav.filter(n=>section?.[1].includes(n[0]));
  useEffect(()=>setOpen(false),[page]);
  useEffect(()=>{
    if(!open)return;
    const away=e=>{if(!box.current?.contains(e.target))setOpen(false)};
    const key=e=>{if(e.key==='Escape')setOpen(false)};
    document.addEventListener('pointerdown',away);document.addEventListener('keydown',key);
    return()=>{document.removeEventListener('pointerdown',away);document.removeEventListener('keydown',key)};
  },[open]);
  if(!current)return null;
  return <nav className="directory" aria-label="You are here"><ol>
    <li className="directory-root"><button onClick={()=>onNavigate(nav[0][0])}><Home size={14}/><span>{root}</span></button></li>
    {section&&<><li className="directory-sep" aria-hidden="true"><ChevronRight size={13}/></li><li className="directory-section"><span>{section[0]}</span></li></>}
    <li className="directory-sep" aria-hidden="true"><ChevronRight size={13}/></li>
    <li className="directory-current" ref={box}>
      <button aria-haspopup="menu" aria-expanded={open} aria-current="page" disabled={siblings.length<2} onClick={()=>setOpen(!open)}>{current[1]}{siblings.length>1&&<ChevronDown size={14} className={open?'flipped':''}/>}</button>
      {open&&<ul className="directory-menu glass" role="menu">{siblings.map(([id,label,Icon],i)=><li key={id} role="none" style={{'--i':i}}><button role="menuitem" className={id===page?'selected':''} onClick={()=>onNavigate(id)}><Icon size={16}/>{label}</button></li>)}</ul>}
    </li>
  </ol></nav>;
}
