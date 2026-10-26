export const defaultLayout=()=>({enabled:false,columns:12,gap:10,cardWidth:190,cardHeight:72,photoSize:44,fontSize:13,sort:'position',groups:{},order:[]});
export function normalizeLayout(value){
  const out=defaultLayout();
  if(!value||typeof value!=='object')return out;
  out.enabled=value.enabled===true;
  for(const [key,min,max] of [['columns',1,12],['gap',0,32],['cardWidth',120,360],['cardHeight',52,160],['photoSize',24,100],['fontSize',10,24]]){
    if(Number.isFinite(value[key]))out[key]=Math.max(min,Math.min(max,Math.round(value[key])));
  }
  out.photoSize=Math.min(out.photoSize,out.cardHeight-12);
  out.fontSize=Math.min(out.fontSize,Math.floor((out.cardHeight-12)/3));
  if(['saved','position','name','status','manual','team'].includes(value.sort))out.sort=value.sort;
  out.order=Array.isArray(value.order)?[...new Set(value.order.filter(x=>typeof x==='string'&&x.length<=240))].slice(0,300):[];
  out.groups=Object.fromEntries(Object.entries(value.groups||{}).slice(0,300).filter(([key,v])=>key.length<=240&&v&&typeof v==='object').map(([key,v])=>[key,{span:Math.max(1,Math.min(out.columns,Math.round(Number(v.span)||out.columns))),height:Math.max(0,Math.min(1600,Math.round(Number(v.height)||0))),hidden:v.hidden===true}]));
  return out;
}
export function layoutGroups(groups,layout){
  const ranks=new Map(layout.order.map((name,index)=>[name,index]));
  return [...groups].sort(([a],[b])=>(ranks.get(a)??Infinity)-(ranks.get(b)??Infinity));
}
export function moveGroup(names,name,target){
  const next=names.filter(x=>x!==name),index=next.indexOf(target);
  next.splice(index<0?next.length:index,0,name);return next;
}
