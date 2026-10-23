export const isOfficeGroup=(name,people)=>people[0]?.department?.trim().toUpperCase()==='OFFICE'||name==='OFFICE';
export const teamColumnWeight=team=>team==='N'?.7:1;
export function boardGroupTier(name,people){
  if(isOfficeGroup(name,people))return 0;
  const teams=new Set(people.map(person=>person.team));
  const shifts=['A','B','C','D'].some(team=>teams.has(team));
  return shifts?(teams.has('N')?1:2):teams.has('N')?3:4;
}
// Rank the actual roster, so searching or showing only IN staff does not move groups.
export function orderBoardGroups(groups,roster=groups){
  const members=new Map(roster);
  const plant=name=>name.includes(' / ')?name.split(' / ')[0]:'';
  return [...groups].sort(([a,peopleA],[b,peopleB])=>plant(a).localeCompare(plant(b))||
    boardGroupTier(a,members.get(a)||peopleA)-boardGroupTier(b,members.get(b)||peopleB));
}
// Keep the same A/B/N (or C/D/N) boundaries across shift groups.
export function boardTeams(people){
  const members=new Map();
  for(const person of people){const team=person.team||'Unassigned';if(!members.has(team))members.set(team,[]);members.get(team).push(person);}
  const hasAB=members.has('A')||members.has('B'),hasCD=members.has('C')||members.has('D');
  const names=[...(hasAB?['A','B']:[]),...(hasCD?['C','D']:[]),...(hasAB||hasCD||members.has('N')?['N']:[])];
  for(const name of members.keys())if(!names.includes(name))names.push(name);
  return names.map(name=>[name,members.get(name)||[]]);
}

export function boardHeight(groups,{width,cardWidth=204,cardHeight=72,gap=8,padding=8,labelWidth=148,officeLabelWidth=108,minLabel=76,teamHeader=24}){
  return groups.reduce((total,[name,people])=>{
    const office=isOfficeGroup(name,people),teams=office?[['',people]]:boardTeams(people);
    const weight=teams.reduce((sum,[team])=>sum+teamColumnWeight(team),0);
    const emptyNormal=!office&&teams.length>1&&!teams.find(([team])=>team==='N')?.[1].length;
    const beforeNormal=teams.findIndex(([team])=>team==='N')-1;
    const heights=teams.map(([team,members],index)=>{
      if(emptyNormal&&team==='N')return 0;
      const teamWidth=(width-(office?officeLabelWidth:labelWidth)-2)*(office||width<=620?1:(teamColumnWeight(team)+(emptyNormal&&index===beforeNormal&&width>620?teamColumnWeight('N'):0))/weight);
      const columns=Math.max(1,Math.floor((teamWidth-(office?0:1)-padding*2+gap)/(cardWidth+gap)));
      const cards=members.length?Math.ceil(members.length/columns)*(cardHeight+gap)-gap:16;
      return cards+padding*2+(office?1:teams.length>1?teamHeader:0);
    });
    const height=!office&&width<=620?heights.reduce((sum,height)=>sum+height+1,0):Math.max(0,...heights);
    return total+Math.max(minLabel,height)+(office?1:6);
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
