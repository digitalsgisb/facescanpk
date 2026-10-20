"""Audited test clock reset and previewed ordinary employee imports."""
import hashlib
import json
import re
import uuid
from datetime import datetime

IMPORT_FIELDS = ('id','name','company','base','employment_department','job_type')


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)


def migrate(db):
    db.execute('''CREATE TABLE IF NOT EXISTS administration_operations (
        request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT NOT NULL)''')


def validate_payload(payload, Problem):
    if not isinstance(payload,dict) or payload.get('format') != 'sgi-employees-v1':
        raise Problem('Choose an SGI employee update JSON file.')
    rows=payload.get('employees')
    if not isinstance(rows,list) or not 1<=len(rows)<=5000:
        raise Problem('Import must contain between 1 and 5000 employees.')
    seen=set()
    for row in rows:
        if not isinstance(row,dict) or set(row)!=set(IMPORT_FIELDS):
            raise Problem('Each row must contain exactly ID, name, company, base, employment department and job type.')
        if any(not isinstance(row[k],str) or not row[k].strip() or len(row[k])>500 for k in IMPORT_FIELDS):
            raise Problem('Imported employee fields must be nonempty text of at most 500 characters.')
        if not re.fullmatch(r'[A-Za-z0-9-]{1,40}',row['id']) or row['id'] in seen:
            raise Problem('Employee IDs must be valid and unique. No records were changed.')
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9 &_.-]{0,79}',row['base']):
            raise Problem('Use an uppercase plant location of 1–80 characters.')
        seen.add(row['id'])
    return rows



def preview(store,db,payload,FIELDS,Problem,base=''):
    rows=validate_payload(payload,Problem)
    if base and any(r['base']!=base for r in rows):
        raise Problem('This account can import only its own plant location.',403)
    existing={r['id']:dict(r) for r in db.execute('SELECT * FROM employees ORDER BY id')}
    changes=[]
    for source in rows:
        old=existing.get(source['id'])
        if base and old and old.get('base','')!=base:
            raise Problem('An employee ID belongs to another location. Ask the full administrator to review it.',403)
        department='R&D' if source['employment_department']=='RESEARCH & DEVELOPMENT' else source['employment_department']
        # Preserve Office board placement, while refreshing its represented department.
        updates={**source,'position':source['job_type']}
        if old and old.get('department')=='OFFICE':
            updates.update(department='OFFICE',office_department=department)
        else:
            updates['department']=department
        after={**(old or {'active':True,'schedule_id':None}),**updates}
        if after.get('department')!='PRODUCTION' or (after.get('line') or '').upper()!='FC':
            after['checksheet_group']=''
        store.validate_employee(db,after)
        fields={k:{'before':old.get(k,'') if old else None,'after':v} for k,v in updates.items() if k!='id' and (not old or old.get(k,'')!=v)}
        changes.append({'id':source['id'],'base':source['base'],'action':'create' if not old else 'update' if fields else 'unchanged',
                        'changes':fields,'after':after})
    state=[{k:row.get(k) for k in (*FIELDS,'updated_at')} for row in existing.values()]
    token=hashlib.sha256(canonical({'rows':rows,'state':state}).encode()).hexdigest()
    summary={action:sum(c['action']==action for c in changes) for action in ('create','update','unchanged')}
    summary['preserved_not_in_file']=len({eid for eid,e in existing.items() if not base or e.get('base')==base}-{r['id'] for r in rows})
    return {'preview_token':token,'summary':summary,'changes':[{k:v for k,v in c.items() if k!='after'} for c in changes]},changes


def operation(store,db,kind,data,actor,FIELDS,Problem,now,base=''):
    request_id=data.get('request_id','')
    if not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9-]{8,80}',request_id):
        raise Problem('A stable request ID is required for safe retries.')
    fingerprint=hashlib.sha256(canonical({'kind':kind,'data':data,'actor':actor,'base':base}).encode()).hexdigest()
    old=db.execute('SELECT * FROM administration_operations WHERE request_id=?',(request_id,)).fetchone()
    if old:
        if old['fingerprint']!=fingerprint:
            raise Problem('This request ID was already used for a different operation.',409)
        return json.loads(old['result'])
    if kind=='reset':
        reason=data.get('reason','')
        if data.get('confirmation')!='CLOCK OUT EVERYONE' or not isinstance(reason,str) or not 5<=len(reason.strip())<=500:
            raise Problem('Type CLOCK OUT EVERYONE and give a testing reset reason (5–500 characters).')
        opened=list(db.execute("SELECT s.* FROM sessions s JOIN employees e ON e.id=s.employee_id WHERE s.time_out IS NULL AND (?='' OR e.base=?) ORDER BY s.id",(base,base)))
        if any(datetime.fromisoformat(r['time_in'])>datetime.fromisoformat(now) for r in opened):
            raise Problem('A clock-in is in the future. Correct that session before resetting.',409)
    else:
        report,changes=preview(store,db,data.get('payload'),FIELDS,Problem,base)
        if data.get('preview_token')!=report['preview_token']:
            raise Problem('Employee records changed. Preview the file again before applying it.',409)
    backup=store.path.parent/'backups'/('before-'+kind+'-'+str(uuid.uuid4())+'.zip')
    # Snapshot succeeds before the first update; a backup failure aborts everything.
    store.backup(backup)
    if kind=='reset':
        for row in opened:
            before=dict(row)
            flags=list(dict.fromkeys(json.loads(row['flags'])+['testing_reset']))
            db.execute('UPDATE sessions SET time_out=?,flags=? WHERE id=?',(now,json.dumps(flags),row['id']))
            result={'employee_id':row['employee_id'],'action':'OUT','accepted':True,'session_id':row['id'],
                    'timestamp':now,'work_date':row['work_date'],'flags':['testing_reset'],
                    'source':'testing_reset','message':'Closed by administrator testing reset.'}
            eid=str(uuid.uuid5(uuid.NAMESPACE_URL,'testing-reset:'+request_id+':'+row['id']))
            result['event_id']=eid
            db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?)',(eid,row['employee_id'],actor,now,now,fingerprint,json.dumps(result)))
            store.audit(db,actor,'testing_reset_clock_out',row['id'],before,{'time_out':now,'reason':reason.strip(),'flags':flags})
        response={'ok':True,'closed':len(opened),'backup':backup.name,'timestamp':now,'base':base}
    else:
        for change in changes:
            if change['action']=='unchanged': continue
            after=change['after']
            if change['action']=='create':
                store.insert_employee(db,after)
            else:
                db.execute('UPDATE employees SET '+','.join(f'{f}=?' for f in FIELDS[1:])+',updated_at=? WHERE id=?',
                           [after.get(f,'') for f in FIELDS[1:]]+[now,after['id']])
            store.audit(db,actor,'employee_import_'+change['action'],change['id'],None,change['changes'])
        response={'ok':True,'summary':report['summary'],'backup':backup.name,'base':base}
    store.audit(db,actor,'testing_reset_completed' if kind=='reset' else 'employee_import_completed',request_id,None,response)
    db.execute('INSERT INTO administration_operations VALUES(?,?,?)',(request_id,fingerprint,json.dumps(response)))
    return response
