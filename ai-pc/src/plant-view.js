import {employeeLocation} from './transfer-utils.js';
export const plantTeams=base=>base==='SENDAYAN'?['C','D','N']:base==='PORT KLANG'?['A','B','N']:['A','B','C','D','N'];
export const filterBoardPlant=(employees,plant='*')=>plant==='*'?employees:employees.filter(e=>employeeLocation(e)===plant);
