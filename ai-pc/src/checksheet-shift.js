const LABELS = { finished: 'Shift finished', off: 'Off shift', grace: 'Shift ending', active: 'On shift' };
export function shiftBoardState(employee) {
  const shift = employee.checksheet_shift;
  if (!shift) return { finished: false, label: '', detail: '' };
  const time = value => new Date(value).toLocaleTimeString('en-MY', { timeZone: 'Asia/Kuala_Lumpur', hour: '2-digit', minute: '2-digit' });
  // 'off' comes from the Checksheet team rotation: this person's team is outside its working hours.
  const finished = shift.state === 'finished' || shift.state === 'off';
  const ot = shift.shift === 'Normal' ? 'Normal hours' : shift.overtime ? 'WITH OT' : 'NO OT';
  const when = shift.state === 'off' ? `hours ${time(shift.startAt)}–${time(shift.endAt)}` : `grey at ${time(shift.greyAt)}`;
  return { finished, label: LABELS[shift.state] || '', detail: `${shift.line} · ${ot} · ${when}` };
}
