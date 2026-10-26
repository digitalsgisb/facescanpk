import React from 'react';
import {defaultLayout,cardSize} from './custom-layout.js';

const CARD_DRAG='application/x-attendance-card';
export function LayoutCard({employee,layout,editing,teamIds,onSize,onMove,children}){
  const {width,height}=cardSize(layout.cards[employee.id],layout),name=employee.nickname||employee.name;
  function resize(event,axis){
    event.preventDefault();event.stopPropagation();
    const handle=event.currentTarget,box=handle.parentElement.getBoundingClientRect();
    const startX=event.clientX,startY=event.clientY;
    handle.setPointerCapture(event.pointerId);
    const move=e=>onSize(employee.id,cardSize({width:axis==='height'?width:box.width+e.clientX-startX,height:axis==='width'?height:box.height+e.clientY-startY},layout));
    const stop=()=>{handle.removeEventListener('pointermove',move);handle.removeEventListener('pointerup',stop);handle.removeEventListener('pointercancel',stop);};
    handle.addEventListener('pointermove',move);handle.addEventListener('pointerup',stop);handle.addEventListener('pointercancel',stop);
  }
  function keyboardResize(event,axis){
    if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;
    event.preventDefault();event.stopPropagation();const delta=event.shiftKey?1:10;
    onSize(employee.id,cardSize({width:width+(axis!=='height'?(event.key==='ArrowLeft'?-delta:event.key==='ArrowRight'?delta:0):0),height:height+(axis!=='width'?(event.key==='ArrowUp'?-delta:event.key==='ArrowDown'?delta:0):0)},layout));
  }
  const index=teamIds.indexOf(employee.id);
  return <div className={'layout-card'+(editing?' card-editing':'')} data-employee-id={employee.id} style={{'--employee-card-width':width+'px','--employee-card-height':height+'px','--board-photo-size':Math.min(layout.photoSize,height-12)+'px','--board-name-size':Math.min(layout.fontSize,Math.floor((height-12)/3))+'px','--board-position-size':Math.max(9,Math.min(layout.fontSize-2,Math.floor((height-12)/3)-2))+'px'}} onDragOver={editing?e=>{if(e.dataTransfer.types.includes(CARD_DRAG)){e.preventDefault();e.stopPropagation()}}:undefined} onDrop={editing?e=>{const source=e.dataTransfer.getData(CARD_DRAG);if(source){e.preventDefault();e.stopPropagation();onMove(teamIds,source,employee.id)}}:undefined}>
    {children}
    {editing&&<><div className="card-edit-tools"><button draggable className="card-move" aria-label={'Move card for '+name} title="Drag onto another card in this team" onDragStart={e=>{e.stopPropagation();e.dataTransfer.effectAllowed='move';e.dataTransfer.setData(CARD_DRAG,employee.id)}}>⠿</button><button disabled={index===0} aria-label={'Move '+name+' card earlier'} onClick={()=>onMove(teamIds,employee.id,teamIds[index-1])}>←</button><button disabled={index===teamIds.length-1} aria-label={'Move '+name+' card later'} onClick={()=>onMove(teamIds,teamIds[index+1],employee.id)}>→</button><button aria-label={'Reset card size for '+name} title="Use default card size" onClick={()=>onSize(employee.id,null)}>↺</button></div><span className="card-size-label">{width} × {height}</span>{[['width','Resize width for ','↔'],['height','Resize height for ','↕'],['both','Resize card for ','◢']].map(([axis,label,symbol])=><button key={axis} className={'card-resize card-resize-'+axis} aria-label={label+name} title={axis==='both'?'Drag corner to resize. Arrow keys resize by 10px; Shift for 1px.':'Drag to change '+axis+'. Arrow keys resize by 10px; Shift for 1px.'} onPointerDown={e=>resize(e,axis)} onKeyDown={e=>keyboardResize(e,axis)}>{symbol}</button>)}</>}
  </div>;
}

export function LayoutEditor({layout,onChange,onSave,onCancel,busy,error,conflict,fullscreen=false}){
  const update=(key,value)=>onChange({...layout,[key]:value});
  return <section className="layout-editor" aria-label="Board layout editor">
    <div className="layout-editor-heading"><div><strong>Edit shared layout</strong><p>Hover over an employee card and drag its right edge, bottom edge or corner to resize. Drag its move handle onto another card in the same team to reorder. Save to apply to every display showing this plant.</p></div><div className="layout-actions"><button className="secondary" disabled={busy} onClick={()=>onChange({...defaultLayout(),enabled:true})}>Reset draft</button><button className="secondary" disabled={busy} onClick={onCancel}>Cancel</button><button className="primary" disabled={busy} onClick={onSave}>{busy?'Saving…':'Save for all displays'}</button></div></div>
    <details className="layout-settings" open={!fullscreen}><summary>Layout settings · Grid, card sizes & sorting</summary><div className="layout-options">
      <label><input type="checkbox" checked={layout.enabled} onChange={e=>update('enabled',e.target.checked)}/>Use custom grid on all displays</label>
      {[["columns","Grid columns",1,12],["gap","Gap",0,32],["cardWidth","Card width",120,360],["cardHeight","Card height",52,160],["photoSize","Photo size",24,100],["fontSize","Name size",10,24]].map(([key,label,min,max])=><label key={key}>{label}<input type="number" min={min} max={max} value={layout[key]} onChange={e=>update(key,Number(e.target.value))}/></label>)}
      <label>Sort employees<select value={layout.sort} onChange={e=>update('sort',e.target.value)}><option value="position">Position hierarchy</option><option value="name">Name A–Z</option><option value="status">Clocked in first</option><option value="team">Team</option><option value="saved">Saved display order</option><option value="manual">Manual employee order from Shifts</option></select></label>
      <button className="secondary" disabled={busy} onClick={()=>onChange({...layout,cards:{},cardOrder:[]})}>Reset individual card sizes & order</button>
    </div></details>
    {fullscreen&&<p className="card-edit-hint">Hover over a card: drag its right/bottom edge to resize, or its ⠿ handle to move within the team.</p>}
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
