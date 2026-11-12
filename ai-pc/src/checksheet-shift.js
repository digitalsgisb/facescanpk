export function shiftBoardState(employee) {
  const shift = employee.checksheet_shift;
  if (!shift) return { finished: false, label: '', detail: '' };
  const end = new Date(shift.greyAt).toLocaleTimeString('en-MY', { timeZone: 'Asia/Kuala_Lumpur', hour: '2-digit', minute: '2-digit' });
  return { finished: shift.state === 'finished', label: shift.state === 'finished' ? 'Shift finished' : shift.state === 'grace' ? 'Shift ending' : 'On shift',
    detail: `${shift.line} · ${shift.overtime ? 'WITH OT' : 'NO OT'} · grey at ${end}` };
}
