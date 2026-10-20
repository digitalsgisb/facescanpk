import React, {useEffect,useState} from 'react';

export function StaffAdministration({api}) {
  const [staff,setStaff]=useState([]),[username,setUsername]=useState(''),[password,setPassword]=useState('');
  const [role,setRole]=useState('employee_admin'),[base,setBase]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[days,setDays]=useState(30);
  const refresh=()=>api('/staff').then(r=>setStaff(r.staff));
  useEffect(()=>{refresh().catch(e=>setMessage(e.message))},[]);
  async function run(action){setBusy(true);setMessage('');try{await action()}catch(e){setMessage(e.message)}finally{setBusy(false)}}
  return <section className="card form-pad"><h2>Staff permissions and photo retention</h2>
    <p>Employee administrators can manage profiles, photos and consent. Full administrators can also manage attendance and settings.</p>
    <div className="photo-choices">{[['pk-admin','PORT KLANG','Set up Port Klang account'],['sendayan-admin','SENDAYAN','Set up Sendayan account'],['developer','','Set up developer account (all plants)']].map(([name,plant,label])=><button key={name} type="button" className="secondary" disabled={busy} onClick={()=>{setUsername(name);setBase(plant);setRole('admin');setPassword('');setMessage('Choose a private password, then save this account.')}}>{label}</button>)}</div>
    <form className="form-grid" onSubmit={e=>{e.preventDefault();run(async()=>{await api('/staff/'+encodeURIComponent(username),'PUT',{password,role,base,active:true});setPassword('');setUsername('');await refresh();setMessage('Staff account saved. Previous staff sessions revoked.')})}}>
      <label>Staff username<input required pattern="[A-Za-z0-9_.-]{1,80}" autoComplete="off" value={username} onChange={e=>setUsername(e.target.value)}/></label>
      <label>New password<input required type="password" minLength={12} maxLength={256} autoComplete="new-password" value={password} onChange={e=>setPassword(e.target.value)}/></label>
      <label>Role<select value={role} onChange={e=>setRole(e.target.value)}><option value="employee_admin">Employee administrator</option><option value="admin">Full administrator</option></select></label>
      <label>Plant access (blank means all plants)<input list="staff-plants" maxLength={80} value={base} onChange={e=>setBase(e.target.value.toUpperCase())}/><datalist id="staff-plants"><option>PORT KLANG</option><option>SENDAYAN</option></datalist></label>
      <small>Choose Administrator with a plant to manage that plant's employee records, imports and attendance. Global staff, device and system settings stay with the all-plants administrator. Use a new location name to roll out another plant.</small>
      <button className="primary" disabled={busy}>Create or update staff</button>
    </form>
    {staff.map(s=><p key={s.username}>{s.username} · {s.role} · {s.base||'All plants'} · {s.active?'Active':'Disabled'} {s.active&&<button type="button" className="secondary" disabled={busy} onClick={()=>run(async()=>{await api('/staff/'+encodeURIComponent(s.username),'PUT',{role:s.role,active:false});await refresh();setMessage('Staff access revoked')})}>Disable account</button>}</p>)}
    <p>Clean up tracked uploads that are no longer used by any employee, including archived employees. Employee and attendance records are retained.</p>
    <label>Minimum upload age for unreferenced photos (days)<input type="number" min="1" max="3650" value={days} onChange={e=>setDays(Number(e.target.value))}/></label>
    <button className="secondary" disabled={busy||!Number.isInteger(days)||days<1||days>3650} onClick={()=>run(async()=>{const r=await api('/retention','POST',{unreferenced_photo_days:days});setMessage(`${r.deleted_photos} unused profile photos deleted`)})}>Delete eligible unused photos</button>
    {message&&<p role="status">{message}</p>}
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
