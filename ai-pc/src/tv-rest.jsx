import React,{useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {productionSection} from './organisation.js';

// Screen-burn protection for the TV board.
// 1. Every few minutes the whole board drifts by a few pixels, so no edge sits on the same pixels for hours.
// 2. On a schedule, the board steps aside for "Smart screen burn avoidance": dark, drifting, rotating attendance charts.

const KEY='attendance-tv-rest';
export const REST_CHOICES=[[15,'Every 15 min'],[30,'Every 30 min'],[60,'Every hour'],[0,'Off']];
const REST_SECONDS=40;
const SHIFTS=[[0,0],[2,1],[-1,3],[-3,-1],[1,-2],[3,2],[-2,0]];
// Panel centres in % of the screen; the panel glides between them so no edge rests on the same pixels.
const SPOTS=[[50,50],[44,45],[56,47],[53,56],[45,55],[57,52],[47,44]];

export function readRestMinutes(){try{const raw=localStorage.getItem(KEY),v=Number(raw);return raw!==null&&REST_CHOICES.some(([m])=>m===v)?v:30}catch{return 30}}
export function saveRestMinutes(value){try{localStorage.setItem(KEY,String(value))}catch{/* optional */}}

// Moves the board a few pixels every two minutes while TV mode is on.
export function usePixelShift(target,on){
  useEffect(()=>{
    const el=target.current;if(!on||!el)return;
    let i=0;const apply=()=>{const [x,y]=SHIFTS[i%SHIFTS.length];el.style.setProperty('--tvx',x+'px');el.style.setProperty('--tvy',y+'px');i++};
    apply();const timer=setInterval(apply,120000);
    return()=>{clearInterval(timer);el.style.removeProperty('--tvx');el.style.removeProperty('--tvy')};
  },[on]);
}

// Shows the rest screen every `minutes`, for REST_SECONDS. Waits while `paused` (a dialog or the layout editor is open).
export function useScreenRest({on,minutes,paused}){
  const [resting,setResting]=useState(false);
  useEffect(()=>{
    if(!on||!minutes||paused){setResting(false);return}
    let timer;
    const wait=()=>{timer=setTimeout(rest,minutes*60000)};
    const rest=()=>{setResting(true);timer=setTimeout(()=>{setResting(false);wait()},REST_SECONDS*1000)};
    wait();
    return()=>clearTimeout(timer);
  },[on,minutes,paused]);
  // A preview shows the same screen once, on demand, for whoever is setting up the TV.
  const [preview,setPreview]=useState(false);
  useEffect(()=>{if(!preview)return;const timer=setTimeout(()=>setPreview(false),REST_SECONDS*1000);return()=>clearTimeout(timer)},[preview]);
  return [resting||preview,()=>{setResting(false);setPreview(false)},()=>setPreview(true)];
}

const clock=new Intl.DateTimeFormat('en-MY',{timeZone:'Asia/Kuala_Lumpur',hour:'2-digit',minute:'2-digit',hour12:false});
const day=new Intl.DateTimeFormat('en-MY',{timeZone:'Asia/Kuala_Lumpur',weekday:'long',day:'numeric',month:'long'});
const titleCase=text=>text.toLowerCase().replace(/\b\w/g,c=>c.toUpperCase());
const groupOf=e=>productionSection(e)?(e.line?.trim()||'No line'):(e.department?.trim()||'No department');

function tally(employees,keyOf,limit=8){
  const map=new Map();
  for(const e of employees){const key=keyOf(e),row=map.get(key)||{name:key,total:0,in:0};row.total++;if(e.status==='IN')row.in++;map.set(key,row)}
  const rows=[...map.values()].sort((a,b)=>b.total-a.total||a.name.localeCompare(b.name));
  if(rows.length<=limit)return rows;
  const rest=rows.slice(limit-1).reduce((o,r)=>({name:'Other groups',total:o.total+r.total,in:o.in+r.in}),{name:'Other groups',total:0,in:0});
  return [...rows.slice(0,limit-1),rest];
}

// One horizontal bar per row: the track is the headcount, the green fill is who is clocked in.
function Bars({rows}){
  const max=Math.max(1,...rows.map(r=>r.total));
  return <span className="tv-rest-bars">{rows.map(r=><span className="tv-rest-bar" key={r.name}>
    <span className="tv-rest-bar-name" title={r.name}>{r.name}</span>
    <span className="tv-rest-bar-lane"><span className="tv-rest-bar-track" style={{width:(r.total/max*100)+'%'}}><i style={{width:(r.in/r.total*100)+'%'}}/></span></span>
    <span className="tv-rest-bar-value"><b>{r.in}</b> / {r.total}</span>
  </span>)}</span>;
}

// "Smart screen burn avoidance": a dark screen of live attendance charts that rotates and drifts, so no pixel holds one image.
export function ScreenRest({plant,employees,onWake}){
  const [now,setNow]=useState(()=>new Date()),[tick,setTick]=useState(0),[left,setLeft]=useState(REST_SECONDS);
  const button=useRef(null);
  useEffect(()=>{
    const second=setInterval(()=>{setNow(new Date());setLeft(s=>Math.max(0,s-1));setTick(t=>t+1)},1000);
    button.current?.focus({preventScroll:true});
    return()=>clearInterval(second);
  },[]);
  const inside=employees.filter(e=>e.status==='IN').length,total=employees.length;
  const place=plant&&plant!=='*'?titleCase(plant):'All plants';
  const scenes=[
    ['Who is here now',<span className="tv-rest-hero"><strong>{inside}</strong><span>of {total} people clocked in {plant&&plant!=='*'?'at '+place:'across all plants'}</span><span className="tv-rest-meter"><i style={{width:(total?inside/total*100:0)+'%'}}/></span><small>{total-inside} not clocked in</small></span>],
    ['Clocked in by group',<Bars rows={tally(employees,groupOf)}/>],
    ['Clocked in by team',<Bars rows={tally(employees,e=>e.team?(e.team==='N'?'Normal hours':'Team '+e.team):'No team',6)}/>],
  ];
  const scene=Math.floor(tick/(REST_SECONDS/scenes.length))%scenes.length;
  const [x,y]=SPOTS[Math.floor(tick/6)%SPOTS.length];
  // In real full screen only the board is drawn, so the screen stays inside it; otherwise it covers the whole window.
  const inBoard=!!document.fullscreenElement;
  const view=<button ref={button} type="button" className={'tv-rest'+(inBoard?'':' is-window')} onClick={onWake} aria-label="Smart screen burn avoidance. Select to return to the live board.">
    <span className="tv-rest-panel" style={{left:x+'%',top:y+'%'}}>
      <span className="tv-rest-head"><span className="tv-rest-time">{clock.format(now)}</span><span className="tv-rest-date">{day.format(now)}<br/>{place}</span></span>
      <span className="tv-rest-scene" key={scene}><span className="tv-rest-title">{scenes[scene][0]}</span>{scenes[scene][1]}</span>
      <span className="tv-rest-foot"><span className="tv-rest-steps" aria-hidden="true">{scenes.map((_,i)=><i key={i} className={i===scene?'is-on':''}/>)}</span>Smart screen burn avoidance · Live board back in {left} s</span>
    </span>
  </button>;
  return inBoard?view:createPortal(view,document.body);
}
