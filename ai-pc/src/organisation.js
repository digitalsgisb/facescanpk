export const POSITIONS=['DIRECTOR','GENERAL MANAGER','ASSISTANT MANAGER','SENIOR EXECUTIVE','EXECUTIVE','SUPERVISOR','LEADER','TECHNICAL OFFICER','OPERATOR','TECHNICIAN'];
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
export function positionRank(position){
  const aliases={'ASISTANT MANAGER':'ASSISTANT MANAGER','TECHNICAL OFFICIER':'TECHNICAL OFFICER','WORKER':'OPERATOR'};
  const name=clean(position),index=POSITIONS.indexOf(aliases[name]||name);
  return index<0?POSITIONS.length:index;
}
export function sortEmployees(people,mode='position',order=[]){
  const ranks=new Map(order.map((id,index)=>[id,index]));
  return [...people].sort((a,b)=>(mode==='manual'?(ranks.get(a.id)??Infinity)-(ranks.get(b.id)??Infinity):mode==='position'||mode==='role'?positionRank(a.position)-positionRank(b.position):0)||(a.nickname||a.name).localeCompare(b.nickname||b.name)||a.id.localeCompare(b.id));
}
export function employeeGroup(employee){
  const section=productionSection(employee),line=employee.line?.trim();
  return section?(clean(line)===section?section:section+' · '+(line||'Line unassigned')):employee.department||'Unassigned';
}
