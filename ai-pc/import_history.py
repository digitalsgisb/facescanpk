"""Validate/import an existing MySQL CSV or TSV export; dry-run by default."""
import argparse
import csv
import json
import uuid
from datetime import datetime,timedelta
from pathlib import Path
from server import Store,KL,Problem


def import_history(store,source,apply=False):
    raw=Path(source).read_text(encoding='utf-8-sig')
    delimiter='\t' if '\t' in raw.splitlines()[0] else ','
    rows=list(csv.DictReader(raw.splitlines(),delimiter=delimiter))
    prepared=[]
    errors=[]
    for index,row in enumerate(rows,2):
        try:
            eid=str(row['worker_id']).strip()
            wd=datetime.strptime(row['date'],'%Y-%m-%d').date()
            tin=datetime.fromisoformat(f'{wd}T{row["time_in"]}').replace(tzinfo=KL)
            time_out=(row.get('time_out') or '').strip()
            tout=None
            if time_out and time_out.upper()!='NULL':
                tout=datetime.fromisoformat(f'{wd}T{time_out}').replace(tzinfo=KL)
                if tout<tin:
                    tout+=timedelta(days=1)
            sid=str(uuid.uuid5(uuid.NAMESPACE_URL,f'sugihara-legacy:{eid}:{wd}:{tin.isoformat()}'))
            prepared.append((sid,eid,str(wd),tin,tout,row))
        except (KeyError,ValueError) as exc:
            errors.append({'row':index,'error':str(exc)})
    report={'source':str(Path(source).resolve()),'rows':len(rows),'validated':len(prepared),
            'imported':0,'already_imported':0,'errors':errors,'dry_run':not apply}
    if errors or not apply:
        return report
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        for sid,eid,wd,tin,tout,row in prepared:
            if db.execute('SELECT 1 FROM sessions WHERE id=?',(sid,)).fetchone():
                report['already_imported']+=1
                continue
            e=db.execute('SELECT * FROM employees WHERE id=?',(eid,)).fetchone()
            if not e:
                new={'id':eid,'name':row.get('name') or 'Historical employee '+eid,'department':row.get('department',''),
                     'team':'','active':False,'schedule_id':None}
                store.validate_employee(db,new)
                store.insert_employee(db,new)
                e=db.execute('SELECT * FROM employees WHERE id=?',(eid,)).fetchone()
            if db.execute('SELECT 1 FROM sessions WHERE employee_id=? AND time_in<=? AND (time_out IS NULL OR time_out>=?)',
                    (eid,(tout or datetime.max.replace(tzinfo=KL)).isoformat(),tin.isoformat())).fetchone():
                raise Problem(f'Overlapping legacy attendance for {eid} on {wd}. No rows were committed.')
            db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (sid,eid,wd,tin.isoformat(),tout.isoformat() if tout else None,None,row.get('shift') or 'Legacy schedule',
                 None,None,json.dumps(['legacy_import','verify_imported_times']),'legacy'))
            store.snapshot(db,sid,e)
            store.audit(db,'migration','legacy_attendance_imported',sid,None,{'employee_id':eid,'work_date':wd})
            report['imported']+=1
    store.emit()
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('export',type=Path)
    parser.add_argument('--db',default=str(Path(__file__).parent/'runtime/attendance.sqlite3'))
    parser.add_argument('--apply',action='store_true',help='Commit after parsing validation; default is dry-run')
    args=parser.parse_args()
    report=import_history(Store(args.db),args.export,args.apply)
    report_path=Path(args.db).parent/'history-import-report.json'
    report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='source'},indent=2))
