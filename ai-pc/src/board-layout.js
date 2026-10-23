export const isOfficeGroup=(name,people)=>people[0]?.department?.trim().toUpperCase()==='OFFICE'||name==='OFFICE';
// Give larger teams more room without squeezing a smaller team into a sliver.
export const teamColumnWeight=count=>Math.sqrt(Math.max(1,count));

// Match the parallel team columns, including their heading and native card rows.
export function boardHeight(groups,{width,cardWidth=204,cardHeight=72,gap=8,padding=8,labelWidth=108,minLabel=76,teamHeader=24}){
  return groups.reduce((total,[name,people])=>{
    const office=isOfficeGroup(name,people);
    const teams=office?[people.length]:Object.values(people.reduce((counts,e)=>{counts[e.team||'Unassigned']=(counts[e.team||'Unassigned']||0)+1;return counts;},{}));
    const weights=teams.reduce((sum,count)=>sum+teamColumnWeight(count),0);
    const heights=teams.map(count=>{
      const teamWidth=(width-labelWidth-2)*(office||width<=620?1:teamColumnWeight(count)/weights);
      const columns=Math.max(1,Math.floor((teamWidth-(office?0:1)-padding*2+gap)/(cardWidth+gap)));
      return Math.ceil(count/columns)*(cardHeight+gap)-gap+padding*2+(office?1:teamHeader);
    });
    const height=!office&&width<=620?heights.reduce((sum,height)=>sum+height+1,0):Math.max(0,...heights);
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
