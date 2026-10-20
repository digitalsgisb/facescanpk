export function syncLabel(status) {
  return ({synced:'Confirmed on all connected kiosks',pending:'Waiting for kiosk confirmation',offline:'Kiosk offline; confirmation pending',no_kiosk:'No active kiosk connected'})[status] || 'Confirmation unavailable';
}
