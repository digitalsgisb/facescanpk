export const requestId=()=>Array.from(crypto.getRandomValues(new Uint8Array(16)),byte=>byte.toString(16).padStart(2,'0')).join('');
export function parseEmployeeFile(text){
  const payload=JSON.parse(text);
  if(!payload||!['sgi-employees-v1','sgi-employee-roster-v1','sgi-team-assignments-v1'].includes(payload.format)||!Array.isArray(payload.employees)||!payload.employees.length)throw new Error('Choose a prepared SGI employee update JSON file.');
  return payload;
}
export const employeeLocation=e=>e.base||'Location unassigned';
