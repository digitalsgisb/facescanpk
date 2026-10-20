import React from 'react';
import {syncLabel} from './employee-sync.js';
import './employee-privacy.css';

export function EmployeePrivacy({form, update, existing, disabled, removePhoto}) {
  const consent = form.consent_record;
  return <section className="employee-privacy" aria-label="Privacy and synchronization">
    <h3>Profile photo and consent</h3>
    <p>Profile photos are for employee administration. Photos are not sent to the Raspberry Pi.</p>
    {form.photo_url && <button type="button" className="secondary" disabled={disabled} onClick={removePhoto}>
      {existing?.photo_url === form.photo_url ? 'Delete saved profile photo now' : 'Clear selected photo'}
    </button>}
    {existing && <p role="status"><strong>Employee details: {syncLabel(existing.metadata_sync?.status)}</strong>
      {existing.metadata_sync?.devices?.map(d => <small key={d.id}>{d.name}: {syncLabel(d.status)}{d.acknowledged_at ? ` · last confirmed ${new Date(d.acknowledged_at).toLocaleString()}` : ''}</small>)}
    </p>}
    <p>Current consent: {['employee_data','profile_photo'].map(p => `${p === 'employee_data' ? 'Employee data' : 'Profile photo'}: ${form.consents?.[p] ? form.consents[p].granted ? 'granted' : 'withdrawn' : 'not recorded'}`).join(' · ')}</p>
    <label className="checkbox-label"><input type="checkbox" checked={!!consent} disabled={disabled} onChange={e => update('consent_record',e.target.checked ? {purpose:'employee_data',granted:true,notice:'',evidence:''} : null)}/>Record a consent decision with this save</label>
    {consent && <div className="form-grid">
      <label>Purpose<select value={consent.purpose} disabled={disabled} onChange={e=>update('consent_record',{...consent,purpose:e.target.value})}><option value="employee_data">Employee data administration</option><option value="profile_photo">Profile photo</option></select></label>
      <label>Decision<select value={String(consent.granted)} disabled={disabled} onChange={e=>update('consent_record',{...consent,granted:e.target.value==='true'})}><option value="true">Granted</option><option value="false">Withdrawn</option></select></label>
      <label>Notice version<input required minLength={3} maxLength={500} disabled={disabled} value={consent.notice} onChange={e=>update('consent_record',{...consent,notice:e.target.value})}/></label>
      <label>Evidence reference<input required minLength={3} maxLength={500} disabled={disabled} placeholder="e.g. signed form reference" value={consent.evidence} onChange={e=>update('consent_record',{...consent,evidence:e.target.value})}/></label>
    </div>}
    <small>Only record a decision the employee has made. Existing consent is not assumed. Photo deletion takes effect immediately; other changes take effect on Save. Consent history is retained separately. Biometric consent is outside this form.</small>
  </section>;
}
