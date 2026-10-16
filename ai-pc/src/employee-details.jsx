import React, {useEffect, useState} from 'react';
import {createPortal} from 'react-dom';
import {X} from 'lucide-react';

const clockTime = value => value ? new Intl.DateTimeFormat('en-MY', {timeZone:'Asia/Kuala_Lumpur',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value)) + ' MYT' : 'No open session';

export function EmployeeDetails({employee, onClose}) {
  const [target, setTarget] = useState(() => document.fullscreenElement || document.body);
  const [broken, setBroken] = useState(false);
  useEffect(() => {
    const update = () => setTarget(document.fullscreenElement || document.body);
    const escape = event => {if(event.key === 'Escape') onClose();};
    document.addEventListener('fullscreenchange', update);
    document.addEventListener('keydown', escape);
    return () => {document.removeEventListener('fullscreenchange', update);document.removeEventListener('keydown', escape);};
  }, [onClose]);
  useEffect(() => setBroken(false), [employee?.photo_url]);
  if (!employee) return null;
  const details = [
    ['Employee ID', employee.id], ['Department', employee.department || 'Unassigned'],
    ['Production line', employee.line || 'Unassigned'], ['Position', employee.position || 'Unassigned'],
    ['Team', employee.team || 'Unassigned'], ['Working hours', employee.effective_schedule ? `${employee.effective_schedule.start} – ${employee.effective_schedule.end}` : 'Unassigned'],
    ['Current clock-in', clockTime(employee.session?.time_in)],
  ];
  return createPortal(<div className="modal-backdrop" onMouseDown={event => {if(event.target === event.currentTarget) onClose();}}>
    <section className="modal" role="dialog" aria-modal="true" aria-label="Employee details">
      <header><div><h2>Employee details</h2><p>Live board · View only</p></div><button className="icon-button" autoFocus aria-label="Close employee details" onClick={onClose}><X size={20}/></button></header>
      <div className="employee-details-body"><div className="employee-profile"><div className="avatar large">{employee.photo_url && !broken ? <img src={employee.photo_url} alt="" onError={() => setBroken(true)}/> : (employee.nickname || employee.name).split(' ').filter(Boolean).slice(0,2).map(part => part[0]).join('')}</div><div><strong>{employee.nickname || employee.name}</strong><small>{employee.name}</small><span className={'badge ' + (employee.status === 'IN' ? 'green' : 'red')}>{employee.status === 'IN' ? 'Clocked in' : 'Clocked out'}</span></div></div>
      <dl className="employee-readonly-details">{details.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></div>
      <footer className="modal-footer"><div className="spacer"/><button className="secondary" onClick={onClose}>Close</button></footer>
    </section>
  </div>, target);
}
