import React, {useEffect,useState} from 'react';

export function StaffAdministration({api}) {
  const [staff,setStaff]=useState([]),[username,setUsername]=useState(''),[password,setPassword]=useState('');
  const [role,setRole]=useState('employee_admin'),[base,setBase]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[days,setDays]=useState(30);
  const refresh=()=>api('/staff').then(r=>setStaff(r.staff));
  useEffect(()=>{refresh().catch(e=>setMessage(e.message))},[]);
  async function run(action){setBusy(true);setMessage('');try{await action()}catch(e){setMessage(e.message)}finally{setBusy(false)}}
  return <section className="card staff-administration">
    <header className="staff-heading"><div><h2>Staff access</h2><p>Manage accounts and plant permissions.</p></div><span className="staff-count">{staff.filter(s=>s.active).length} active</span></header>
    <div className="staff-accounts">{staff.map(s=><article className="staff-account" key={s.username}>
      <div className="staff-account-info"><strong>{s.username}</strong><small>{s.role==='admin'?'Administrator':'Employee administrator'} · {s.base||'All plants'}</small></div>
      <span className={'staff-status'+(s.active?'':' disabled')}>{s.active?'Active':'Disabled'}</span>
      {s.active&&<button type="button" className="secondary" aria-label={'Disable '+s.username} disabled={busy} onClick={()=>run(async()=>{await api('/staff/'+encodeURIComponent(s.username),'PUT',{role:s.role,active:false});await refresh();setMessage('Staff access revoked')})}>Disable</button>}
    </article>)}{!staff.length&&<p className="staff-empty">No staff accounts added.</p>}</div>
    <details className="staff-editor"><summary>Add or update account</summary><div className="staff-editor-body">
    <div className="staff-presets"><span>Quick setup</span>{[['pk-admin','PORT KLANG','Port Klang'],['sendayan-admin','SENDAYAN','Sendayan'],['developer','','Developer · All plants']].map(([name,plant,label])=><button key={name} type="button" className="secondary" disabled={busy} onClick={()=>{setUsername(name);setBase(plant);setRole('admin');setPassword('');setMessage('Choose a private password, then save this account.')}}>{label}</button>)}</div>
    <form className="form-grid staff-form" onSubmit={e=>{e.preventDefault();run(async()=>{await api('/staff/'+encodeURIComponent(username),'PUT',{password,role,base,active:true});setPassword('');setUsername('');await refresh();setMessage('Staff account saved. Previous staff sessions revoked.')})}}>
      <label>Username<input required pattern="[A-Za-z0-9_.-]{1,80}" autoComplete="off" value={username} onChange={e=>setUsername(e.target.value)}/></label>
      <label>New password<input required type="password" minLength={12} maxLength={256} autoComplete="new-password" value={password} onChange={e=>setPassword(e.target.value)}/><small>At least 12 characters.</small></label>
      <label>Role<select value={role} onChange={e=>setRole(e.target.value)}><option value="employee_admin">Employee administrator</option><option value="admin">Full administrator</option></select></label>
      <label>Plant access<input list="staff-plants" placeholder="All plants" maxLength={80} value={base} onChange={e=>setBase(e.target.value.toUpperCase())}/><datalist id="staff-plants"><option>PORT KLANG</option><option>SENDAYAN</option></datalist><small>Leave blank for all plants, or enter a new plant.</small></label>
      <p className="staff-role-help">Employee admins manage profiles, photos and consent. Full admins also manage attendance and shifts. All-plants admins manage system settings.</p>
      <div className="staff-form-actions"><button className="primary" disabled={busy}>Save account</button></div>
    </form>
    </div></details>
    <details className="staff-retention"><summary>Unused photo cleanup</summary><div className="staff-retention-body">
      <p>Delete uploads no longer linked to any employee. Employee records and attendance stay saved.</p>
      <div className="staff-retention-controls"><label>Minimum age (days)<input type="number" min="1" max="3650" value={days} onChange={e=>setDays(Number(e.target.value))}/></label>
      <button className="secondary" disabled={busy||!Number.isInteger(days)||days<1||days>3650} onClick={()=>run(async()=>{const r=await api('/retention','POST',{unreferenced_photo_days:days});setMessage(`${r.deleted_photos} unused profile photos deleted`)})}>Delete unused photos</button></div>
    </div></details>
    {message&&<p className="staff-message" role="status">{message}</p>}
  </section>;
}

export function PlantConnections({devices,api,onRefresh}) {
  const [busy,setBusy]=useState(false),[message,setMessage]=useState('');
  return <section className="card form-pad"><h2>Connection plant access</h2><p>Assign each kiosk or integration to its plant. A blank location keeps legacy access to all plants. Existing tokens continue working.</p>
    {devices.filter(d=>d.active).map(d=><form key={d.id} className="form-grid" onSubmit={async e=>{e.preventDefault();const base=new FormData(e.currentTarget).get('base').trim().toUpperCase();setBusy(true);try{await api('/devices/'+d.id,'PUT',{base});await onRefresh();setMessage('Connection plant updated. Wait for the kiosk to refresh its cache.')}catch(error){setMessage(error.message)}finally{setBusy(false)}}}>
      <label>{d.name}<input key={d.base} name="base" list="staff-plants" defaultValue={d.base||''} maxLength={80}/></label><button className="secondary" disabled={busy}>Save connection plant</button>
    </form>)}{message&&<p role="status">{message}</p>}
  </section>;
}
