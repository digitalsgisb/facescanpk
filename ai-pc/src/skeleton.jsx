import React from 'react';

// Placeholder blocks shaped like the content they stand in for, so the layout does not jump when data arrives.
export function Sk({w='100%',h=12,circle=false,dark=false,style}){
  return <span aria-hidden="true" className={'sk'+(circle?' sk-circle':'')+(dark?' sk-on-dark':'')} style={{width:w,height:h,...style}}/>;
}
export function SkRows({rows=6,avatar=false,label='Loading…'}){
  return <div role="status" aria-busy="true"><span className="sk-status">{label}</span>{Array.from({length:rows},(_,i)=><div className="sk-row" key={i}>{avatar&&<Sk circle w={36} h={36}/>}<div><Sk w={`${42+(i*17)%35}%`} h={13}/><Sk w={`${24+(i*11)%25}%`} h={10}/></div><Sk w={64} h={13}/></div>)}</div>;
}
export function SkTableRows({cols=5,rows=8}){
  return Array.from({length:rows},(_,r)=><tr key={'sk'+r} aria-hidden="true">{Array.from({length:cols},(_,c)=><td key={c}><Sk w={`${45+((r+c)*23)%45}%`} h={13}/></td>)}</tr>);
}
export function ShellSkeleton({error}){
  return <div className="app-shell sk-shell" role="status" aria-busy="true"><span className="sk-status">Loading your workspace…</span>
    <aside className="sidebar"><div className="brand"><Sk dark circle w={34} h={34}/><Sk dark w={120} h={14}/></div><div className="sk-nav">{Array.from({length:8},(_,i)=><Sk dark key={i} w={`${55+(i*13)%35}%`} h={16} style={{margin:'6px 12px'}}/>)}</div></aside>
    <main><header className="topbar"><Sk dark w={140} h={16}/><Sk dark w={90} h={12}/></header>
      <div className="page">{error&&<div className="error-banner sk-error" role="alert">{error}</div>}
        <div className="page-heading"><div style={{display:'grid',gap:10,flex:1}}><Sk w={260} h={26}/><Sk w={340} h={13} style={{maxWidth:'80%'}}/></div></div>
        <div className="stats-grid">{Array.from({length:4},(_,i)=><section className="stat" key={i}><Sk w="60%" h={13}/><Sk w={70} h={34} style={{margin:'14px 0 10px'}}/><Sk w="80%" h={11}/></section>)}</div>
        <div className="overview-grid"><section className="card"><div className="section-heading"><Sk w={180} h={16}/></div><SkRows rows={5}/></section><section className="card"><div className="section-heading"><Sk w={150} h={16}/></div><SkRows rows={5} avatar/></section></div>
      </div></main>
  </div>;
}
// A figure that ticks into place whenever its value changes.
export function Tick({value}){return <span className="tick" key={value}>{value}</span>}
