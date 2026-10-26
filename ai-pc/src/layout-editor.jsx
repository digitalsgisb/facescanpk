import React from 'react';
import {defaultLayout} from './custom-layout.js';

export function LayoutEditor({layout,onChange,onSave,onCancel,busy,error,conflict,fullscreen=false}){
  const update=(key,value)=>onChange({...layout,[key]:value});
  return <section className="layout-editor" aria-label="Board layout editor">
    <div className="layout-editor-heading"><div><strong>Edit shared layout</strong><p>Drag group handles to reorder. Drag a bottom-right corner to resize, or use the group controls. Save to apply to every display showing this plant.</p></div><div className="layout-actions"><button className="secondary" disabled={busy} onClick={()=>onChange({...defaultLayout(),enabled:true})}>Reset draft</button><button className="secondary" disabled={busy} onClick={onCancel}>Cancel</button><button className="primary" disabled={busy} onClick={onSave}>{busy?'Saving…':'Save for all displays'}</button></div></div>
    <details className="layout-settings" open={!fullscreen}><summary>Layout settings · Grid, card sizes & sorting</summary><div className="layout-options">
      <label><input type="checkbox" checked={layout.enabled} onChange={e=>update('enabled',e.target.checked)}/>Use custom grid on all displays</label>
      {[["columns","Grid columns",1,12],["gap","Gap",0,32],["cardWidth","Card width",120,360],["cardHeight","Card height",52,160],["photoSize","Photo size",24,100],["fontSize","Name size",10,24]].map(([key,label,min,max])=><label key={key}>{label}<input type="number" min={min} max={max} value={layout[key]} onChange={e=>update(key,Number(e.target.value))}/></label>)}
      <label>Sort employees<select value={layout.sort} onChange={e=>update('sort',e.target.value)}><option value="position">Position hierarchy</option><option value="name">Name A–Z</option><option value="status">Clocked in first</option><option value="team">Team</option><option value="saved">Saved display order</option><option value="manual">Manual employee order from Shifts</option></select></label>
    </div></details>
    {conflict&&<p role="alert">Another display saved a layout while you were editing. Cancel to load it before making further changes.</p>}
    {error&&<p role="alert">{error}</p>}
  </section>;
}

export function LayoutGroup({name,config,layout,editing,names,onChange,onMove,children}){
  const span=config?.span||layout.columns,height=config?.height||0;
  const update=patch=>onChange({...config,...patch});
  function resize(event){
    event.preventDefault();const handle=event.currentTarget,box=handle.parentElement,grid=box.parentElement;
    const startX=event.clientX,startY=event.clientY,startHeight=box.getBoundingClientRect().height;
    const unit=(grid.clientWidth+layout.gap)/layout.columns;
    handle.setPointerCapture(event.pointerId);
    const move=e=>update({span:Math.max(1,Math.min(layout.columns,Math.round(span+(e.clientX-startX)/unit))),height:Math.max(80,Math.min(1600,Math.round(startHeight+e.clientY-startY)))});
    const stop=()=>{handle.removeEventListener('pointermove',move);handle.removeEventListener('pointerup',stop);handle.removeEventListener('pointercancel',stop);};
    handle.addEventListener('pointermove',move);handle.addEventListener('pointerup',stop);handle.addEventListener('pointercancel',stop);
  }
  return <div className={'layout-group'+(config?.hidden?' layout-hidden':'')} style={{gridColumn:`span ${span}`,minHeight:height||undefined}} onDragOver={editing?e=>e.preventDefault():undefined} onDrop={editing?e=>{e.preventDefault();const source=e.dataTransfer.getData('text/plain');if(names.includes(source))onMove(source,name)}:undefined}>
    {editing&&<div className="layout-group-controls"><button className="layout-drag" draggable onDragStart={e=>e.dataTransfer.setData('text/plain',name)} title="Drag to move group">⠿ {name.split(' / ').slice(1).join(' / ')}</button><button aria-label={'Move '+name+' earlier'} disabled={names.indexOf(name)===0} onClick={()=>onMove(name,names[names.indexOf(name)-1])}>↑</button><button aria-label={'Move '+name+' later'} disabled={names.indexOf(name)===names.length-1} onClick={()=>onMove(names[names.indexOf(name)+1],name)}>↓</button><label>Width<input aria-label={'Grid width for '+name} type="number" min="1" max={layout.columns} value={span} onChange={e=>update({span:Number(e.target.value)})}/></label><label>Min height<input aria-label={'Minimum height for '+name} type="number" min="0" max="1600" value={height} onChange={e=>update({height:Number(e.target.value)})}/></label><label><input type="checkbox" checked={!config?.hidden} onChange={e=>update({hidden:!e.target.checked})}/>Show</label></div>}
    {children}
    {editing&&<button className="layout-resize" onPointerDown={resize} aria-label={'Resize '+name} title="Drag to resize">◢</button>}
  </div>;
}
