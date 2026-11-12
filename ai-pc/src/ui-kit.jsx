import React,{useEffect,useId,useLayoutEffect,useRef,useState} from 'react';
import {flushSync} from 'react-dom';
import {ChevronDown} from 'lucide-react';

// Run a state change inside a View Transition so the browser morphs old -> new (shared elements keep their identity).
// Falls back to an instant update where the API is missing or the user prefers reduced motion.
export function transition(update){
  const reduced=window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  if(!document.startViewTransition||reduced){update();return}
  try{document.startViewTransition(()=>{flushSync(update)})}catch{update()}
}

// Cross-fades the previous and the new content on top of each other (blur + scale), so a state change reads as one thing turning into another.
export function Morph({k,children,className=''}){
  const latest=useRef({k,children}),timer=useRef(0),[out,setOut]=useState(null);
  useLayoutEffect(()=>{
    const previous=latest.current;
    if(previous.k!==k){setOut(previous);clearTimeout(timer.current);timer.current=setTimeout(()=>setOut(null),320)}
    latest.current={k,children};
  });
  useEffect(()=>()=>clearTimeout(timer.current),[]);
  return <span className={'morph '+className}>
    {out&&<span className="morph-layer morph-out" aria-hidden="true">{out.children}</span>}
    <span key={k} className={'morph-layer'+(out?' morph-in':'')}>{children}</span>
  </span>;
}

// A section that folds away: the main feature stays open on the page, everything secondary lives in one of these.
export function Disclosure({id,title,hint,badge,defaultOpen=false,children}){
  const key='attendance-section-'+id,panel=useId();
  const [open,setOpen]=useState(()=>{try{const saved=sessionStorage.getItem(key);return saved===null?defaultOpen:saved==='1'}catch{return defaultOpen}});
  const [mounted,setMounted]=useState(open);
  function toggle(){
    const next=!open;
    if(next)setMounted(true);
    setOpen(next);
    try{sessionStorage.setItem(key,next?'1':'0')}catch{/* optional */}
  }
  return <section className={'disclosure'+(open?' is-open':'')}>
    <h2 className="disclosure-head"><button type="button" aria-expanded={open} aria-controls={panel} onClick={toggle}>
      <span className="disclosure-title"><strong>{title}</strong>{hint&&<small>{hint}</small>}</span>
      {badge!=null&&badge!==''&&<span className="disclosure-badge">{badge}</span>}
      <ChevronDown size={18} className="disclosure-chevron"/>
    </button></h2>
    <div id={panel} className="disclosure-panel" inert={!open?true:undefined}><div className="disclosure-body">{mounted&&children}</div></div>
  </section>;
}
