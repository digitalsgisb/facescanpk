export const POSITIONS=['DIRECTOR','GENERAL MANAGER','ASSISTANT MANAGER','SENIOR EXECUTIVE','EXECUTIVE','SUPERVISOR','LEADER','TECHNICAL OFFICER','TECHNICIAN','OPERATOR'];
const clean=value=>(value||'').trim().toUpperCase();
export function productionSection(employee){
  if(clean(employee.department)!=='PRODUCTION')return '';
  return employee.production_section|| (clean(employee.line)==='ROLL MAKING'?'ROLL MAKING':'CONVERSION');
}
export function scheduleScopes(employee){
  const department=clean(employee.department),section=productionSection(employee);
  return [...(section?[...(employee.line?.trim()?['line:'+employee.line.trim()]:[]),'section:'+section]:[]),...(department?['department:'+department]:[])];
}
export function scopeOptions(employees){
  const options=new Map([['','Company defaults'],['section:CONVERSION','Production · Conversion'],['section:ROLL MAKING','Production · Roll Making'],['department:OFFICE','Office']]);
  for(const employee of employees){
    if(clean(employee.department)==='PRODUCTION'&&employee.line?.trim())options.set('line:'+employee.line.trim(),'Production line · '+employee.line.trim());
    else if(employee.department&&clean(employee.department)!=='OFFICE')options.set('department:'+clean(employee.department),employee.department);
  }
  return [...options];
}
export const POSITION_HIERARCHY=['DIRECTOR','GENERAL MANAGER','SENIOR MANAGER','MANAGER','ASSISTANT MANAGER','SENIOR EXECUTIVE','EXECUTIVE','JUNIOR EXECUTIVE','SENIOR SUPERVISOR','SUPERVISOR','ACTING SUPERVISOR','SENIOR LEADER','TEAM LEADER','LEADER','TECHNICAL OFFICER','TECHNICAL ASSISTANT','SENIOR TECHNICIAN','TECHNICIAN','SENIOR OPERATOR','OPERATOR','SENIOR QC INSPECTOR','QC INSPECTOR','MOULD MAKER','SENIOR ASSISTANT','ASSISTANT','TRAINEE'];
export function positionRank(position){
  const aliases={'TECHNICAL DIRECTOR':'DIRECTOR','GM':'GENERAL MANAGER','SR MANAGER':'SENIOR MANAGER','MGR':'MANAGER','AM':'ASSISTANT MANAGER','ASISTANT MANAGER':'ASSISTANT MANAGER','SR EXEC':'SENIOR EXECUTIVE','EXEC':'EXECUTIVE','JR EXE':'JUNIOR EXECUTIVE','JR EXEC':'JUNIOR EXECUTIVE','SR SPR':'SENIOR SUPERVISOR','SPR':'SUPERVISOR','SR LEADER':'SENIOR LEADER','TL':'TEAM LEADER','TECHNICAL OFFICIER':'TECHNICAL OFFICER','SR TECHNICIAN':'SENIOR TECHNICIAN','TECH':'TECHNICIAN','SR OPERATOR':'SENIOR OPERATOR','OPR':'OPERATOR','OPR - TECHNICAL':'OPERATOR','WORKER':'OPERATOR','SR QC INSPECTOR':'SENIOR QC INSPECTOR','SR ASST':'SENIOR ASSISTANT','ASSIST':'ASSISTANT'};
  const name=clean(position).split(',')[0].replaceAll('.','').replace(/\s+/g,' ').trim();
  const index=POSITION_HIERARCHY.indexOf(aliases[name]||name);
  return index<0?POSITION_HIERARCHY.length:index;
}
export function sortEmployees(people,mode='position',order=[]){
  const ranks=new Map(order.map((id,index)=>[id,index]));
  return [...people].sort((a,b)=>(mode==='manual'?(ranks.get(a.id)??Infinity)-(ranks.get(b.id)??Infinity):mode==='position'||mode==='role'?positionRank(a.position)-positionRank(b.position):0)||(a.nickname||a.name).localeCompare(b.nickname||b.name)||a.id.localeCompare(b.id));
}
export function employeeGroup(employee){
  const section=productionSection(employee),line=employee.line?.trim();
  return section?(clean(line)===section?section:section+' · '+(line||'Line unassigned')):employee.department||'Unassigned';
}
