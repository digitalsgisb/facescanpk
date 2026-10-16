// Count real card rows. Large TV pages use native pixel sizes, never a scaled canvas.
export function boardHeight(groups,{width,cardWidth=190,cardHeight=68,gap=8,padding=8,labelWidth=132,minLabel=76}){
  return groups.reduce((total,[name,people])=>{
    const office=name==='OFFICE';
    const columns=Math.max(1,Math.floor((width-labelWidth-(office?0:24)-padding*2-2+gap)/(cardWidth+gap)));
    const teams=office?[people.length]:Object.values(people.reduce((counts,e)=>{counts[e.team||'Unassigned']=(counts[e.team||'Unassigned']||0)+1;return counts;},{}));
    const height=teams.reduce((sum,count)=>sum+Math.ceil(count/columns)*(cardHeight+gap)-gap+padding*2+1,0);
    return total+Math.max(minLabel,height)+1;
  },0);
}
export function paginateBoard(groups,dimensions){
  const pages=[];let current=[];
  for(const [name,people] of groups){
    for(const person of people){
      const candidate=current.map(([group,workers])=>[group,[...workers]]);
      if(candidate.at(-1)?.[0]===name)candidate.at(-1)[1].push(person);else candidate.push([name,[person]]);
      if(current.length&&boardHeight(candidate,dimensions)>Math.max(1,dimensions.height)){
        pages.push(current);current=[[name,[person]]];
      }else current=candidate;
    }
  }
  if(current.length)pages.push(current);
  return pages.length?pages:[[]];
}
