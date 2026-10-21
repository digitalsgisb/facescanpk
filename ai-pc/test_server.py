import json
import tempfile
import threading
import unittest
import uuid
import urllib.request
import urllib.error
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from server import Store, Problem, make_server, digest

TEST_ROOT = Path(__file__).resolve().parent / "runtime" / "tests"
TEST_ROOT.mkdir(parents=True, exist_ok=True)


class AttendanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=TEST_ROOT)
        self.store=Store(Path(self.temp.name)/'test.sqlite3',seed=False)
        with self.store.connect() as db:
            for eid,schedule in [('A','day'),('N','night-ot'),('U',None)]:
                self.store.insert_employee(db,{'id':eid,'name':'Test '+eid,'nickname':eid,'team':'A','schedule_id':schedule})

    def tearDown(self):
        assert Path(self.temp.name).resolve().is_relative_to(TEST_ROOT.resolve())
        self.temp.cleanup()

    def test_checksheet_assignment_keeps_fc_tv_group_and_survives_restart(self):
        employee={'id':'FC1','name':'FC One','department':'PRODUCTION','line':'FC','checksheet_group':'fc1'}
        with self.store.connect() as db:
            self.store.validate_employee(db,employee)
            self.store.insert_employee(db,employee)
        restarted=Store(self.store.path,seed=False)
        with restarted.connect() as db:
            saved=next(e for e in restarted.employees(db) if e['id']=='FC1')
            self.assertEqual(saved['checksheet_group'],'fc1')
            self.assertEqual(saved['line'],'FC')
            with self.assertRaises(Problem):
                restarted.validate_employee(db,{**employee,'checksheet_group':'invalid'})
            with self.assertRaises(Problem):
                restarted.validate_employee(db,{**employee,'line':'MF'})

    def scan(self,eid,stamp,event=None,device='pi-one'):
        return self.store.scan({'event_id':event or str(uuid.uuid4()),'employee_id':eid,'timestamp':stamp},device)

    def test_confirmed_retry_is_idempotent_across_restart(self):
        event=str(uuid.uuid4())
        first=self.scan('A','2026-10-10T08:00:00+08:00',event)
        self.store=Store(self.store.path,seed=False)
        retry=self.scan('A','2026-10-10T08:00:00+08:00',event)
        self.assertEqual(first,retry)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0],1)

    def test_event_id_collision_is_rejected(self):
        event=str(uuid.uuid4())
        self.scan('A','2026-10-10T08:00:00+08:00',event)
        with self.assertRaises(Problem):
            self.scan('A','2026-10-10T16:15:00+08:00',event)

    def test_concurrent_kiosks_create_one_session(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda n:self.scan('A','2026-10-10T08:00:00+08:00',device=f'pi-{n}'),range(8)))
        self.assertEqual([r['action'] for r in results].count('IN'),1)
        self.assertEqual([r['action'] for r in results].count('DUPLICATE'),7)

    def test_night_session_survives_midnight(self):
        first=self.scan('N','2026-10-10T20:00:00+08:00')
        last=self.scan('N','2026-10-11T08:00:00+08:00')
        self.assertEqual(first['work_date'],'2026-10-10')
        self.assertEqual(last['work_date'],'2026-10-10')
        self.assertEqual(last['action'],'OUT')
        self.assertEqual(last['flags'],[])

    def test_after_midnight_arrival_uses_previous_shift_date(self):
        result=self.scan('N','2026-10-11T00:10:00+08:00')
        self.assertEqual(result['work_date'],'2026-10-10')
        self.assertIn('outside_scheduled_hours',result['flags'])

    def test_out_of_hours_scan_saved_and_flagged(self):
        result=self.scan('A','2026-10-10T12:00:00+08:00')
        self.assertTrue(result['accepted'])
        self.assertIn('outside_scheduled_hours',result['flags'])

    def test_unassigned_schedule_is_explicit(self):
        result=self.scan('U','2026-10-10T08:00:00+08:00')
        self.assertIn('schedule_unassigned',result['flags'])

    def test_out_of_order_offline_scan_does_not_toggle(self):
        self.scan('A','2026-10-10T08:00:00+08:00')
        result=self.scan('A','2026-10-09T08:00:00+08:00')
        self.assertEqual(result['action'],'REVIEW')
        with self.store.connect() as db:
            self.assertIsNone(db.execute('SELECT time_out FROM sessions').fetchone()[0])

    def test_stale_session_is_not_silently_closed(self):
        self.scan('A','2026-10-10T08:00:00+08:00')
        result=self.scan('A','2026-10-11T08:00:00+08:00')
        self.assertEqual(result['action'],'REVIEW')
        self.assertIn('stale_open_session',result['flags'])

    def test_rotation_and_individual_override(self):
        with self.store.connect() as db:
            db.execute('UPDATE settings SET value=? WHERE key=?',(json.dumps({'anchor_date':'2026-10-01','interval_days':7,'schedule_ids':['day','night']}),'rotation'))
            e=db.execute("SELECT * FROM employees WHERE id='A'").fetchone()
            from datetime import date
            self.assertEqual(self.store.resolve_schedule(db,e,date(2026,10,2))['id'],'day')
            self.assertEqual(self.store.resolve_schedule(db,e,date(2026,10,9))['id'],'night')
            db.execute('INSERT INTO assignments (id,employee_id,team,start_date,end_date,schedule_id) VALUES(?,?,?,?,?,?)',('override','A',None,'2026-10-09','2026-10-09','normal'))
            self.assertEqual(self.store.resolve_schedule(db,e,date(2026,10,9))['id'],'normal')

    def test_section_line_rotation_and_scoped_overrides(self):
        from datetime import date
        with self.store.connect() as db:
            groups={'section:CONVERSION':{'team_schedules':{'A':'day','B':'night'},'team_overtime':{'A':True},
                    'rotation':{'anchor_date':'2026-10-01','interval_days':7,'schedule_ids':['day','night']}},
                    'section:ROLL MAKING':{'team_schedules':{'A':'night'},'team_overtime':{'A':False},'rotation':None},
                    'line:MF':{'team_schedules':{'A':'day'},'rotation':None}}
            db.execute("UPDATE settings SET value=? WHERE key='schedule_groups'",(json.dumps(groups),))
            e=dict(db.execute("SELECT * FROM employees WHERE id='A'").fetchone())
            e.update(department='PRODUCTION',line='FC')
            resolve=lambda employee:self.store.resolve_schedule(db,employee,date(2026,10,9))['id']
            self.assertEqual(resolve(e),'night-ot')
            self.assertEqual(resolve({**e,'line':'ROLL MAKING'}),'night')
            self.assertEqual(resolve({**e,'line':'MF'}),'day')
            db.execute('INSERT INTO assignments VALUES(?,?,?,?,?,?,?)',('section-date',None,'A','2026-10-09','2026-10-09','normal','section:CONVERSION'))
            self.assertEqual(resolve(e),'normal')
            self.assertEqual(resolve({**e,'line':'ROLL MAKING'}),'night')
            db.execute('INSERT INTO assignments VALUES(?,?,?,?,?,?,?)',('line-date',None,'A','2026-10-09','2026-10-09','day','line:FC'))
            self.assertEqual(resolve(e),'day')
            db.execute('INSERT INTO assignments VALUES(?,?,?,?,?,?,?)',('personal','A',None,'2026-10-09','2026-10-09','night-ot',''))
            self.assertEqual(resolve(e),'night-ot')
            self.assertEqual(resolve({**e,'id':'U','department':'OFFICE','office_department':'PRODUCTION'}),'day')

    def test_existing_database_migrates_without_losing_employees_assignments_or_sessions(self):
        import sqlite3
        from contextlib import closing
        legacy=Path(self.temp.name)/'legacy.sqlite3'
        with closing(sqlite3.connect(legacy)) as db:
            db.executescript("""
                CREATE TABLE employees (id TEXT PRIMARY KEY,name TEXT NOT NULL,nickname TEXT,department TEXT,position TEXT,line TEXT,team TEXT,photo_url TEXT,schedule_id TEXT,active INTEGER NOT NULL,updated_at TEXT NOT NULL);
                INSERT INTO employees VALUES ('old','Legacy employee','','PRODUCTION','SUPERVISOR','FC','A','','day',1,'2026-10-01');
                CREATE TABLE assignments (id TEXT PRIMARY KEY,employee_id TEXT,team TEXT,start_date TEXT NOT NULL,end_date TEXT NOT NULL,schedule_id TEXT NOT NULL);
                INSERT INTO assignments VALUES ('old-roster',NULL,'A','2026-10-01','2026-10-31','normal');
            """)
            db.commit()
        migrated=Store(legacy,seed=False)
        migrated.scan({'event_id':str(uuid.uuid4()),'employee_id':'old','timestamp':'2026-10-10T08:00:00+08:00'},'test')
        migrated=Store(legacy,seed=False)
        with migrated.connect() as db:
            employee=dict(db.execute("SELECT * FROM employees WHERE id='old'").fetchone())
            self.assertEqual(employee['production_section'],'')
            self.assertEqual(employee['name'],'Legacy employee')
            self.assertEqual(db.execute('SELECT scope FROM assignments').fetchone()[0],'')
            self.assertEqual(db.execute('SELECT schedule_id FROM sessions').fetchone()[0],'normal')
            migrated.insert_employee(db,{'id':'new','name':'New','office_department':'HR','department':'OFFICE'})
            self.assertEqual(db.execute("SELECT office_department FROM employees WHERE id='new'").fetchone()[0],'HR')

    def test_archived_employee_cannot_scan(self):
        with self.store.connect() as db:
            db.execute("UPDATE employees SET active=0 WHERE id='A'")
        with self.assertRaises(Problem):
            self.scan('A','2026-10-10T08:00:00+08:00')

    def test_team_hours_and_overtime_follow_team_after_rotation(self):
        from datetime import date
        with self.store.connect() as db:
            settings={'team_schedules':{'A':'day','B':'night'},'team_overtime':{'A':True,'B':False},
                      'rotation':{'anchor_date':'2026-10-01','interval_days':7,'schedule_ids':['day','night']}}
            for key,value in settings.items():
                db.execute('UPDATE settings SET value=? WHERE key=?',(json.dumps(value),key))
            employee=dict(db.execute("SELECT * FROM employees WHERE id='A'").fetchone())
            self.assertEqual(self.store.resolve_schedule(db,employee,date(2026,10,2))['id'],'day-ot')
            self.assertEqual(self.store.resolve_schedule(db,employee,date(2026,10,9))['id'],'night-ot')
            employee['team']='B'
            self.assertEqual(self.store.resolve_schedule(db,employee,date(2026,10,2))['id'],'night')
            self.assertEqual(self.store.resolve_schedule(db,employee,date(2026,10,9))['id'],'day')
            db.execute('INSERT INTO assignments (id,employee_id,team,start_date,end_date,schedule_id) VALUES(?,?,?,?,?,?)',('team-date',None,'B','2026-10-09','2026-10-09','night-ot'))
            self.assertEqual(self.store.resolve_schedule(db,employee,date(2026,10,9))['id'],'night-ot')
            db.execute('INSERT INTO assignments (id,employee_id,team,start_date,end_date,schedule_id) VALUES(?,?,?,?,?,?)',('person-date','A',None,'2026-10-09','2026-10-09','normal'))
            self.assertEqual(self.store.resolve_schedule(db,employee,date(2026,10,9))['id'],'normal')

    def test_fixed_team_changes_do_not_rewrite_saved_attendance(self):
        result=self.scan('A','2026-10-10T08:00:00+08:00')
        with self.store.connect() as db:
            original=dict(db.execute('SELECT * FROM sessions WHERE id=?',(result['session_id'],)).fetchone())
            db.execute('UPDATE settings SET value=? WHERE key=?',(json.dumps({'A':'night'}),'team_schedules'))
            employee=db.execute("SELECT * FROM employees WHERE id='A'").fetchone()
            from datetime import date
            self.assertEqual(self.store.resolve_schedule(db,employee,date(2026,10,10))['id'],'night')
            self.assertEqual(dict(db.execute('SELECT * FROM sessions WHERE id=?',(result['session_id'],)).fetchone()),original)

    def test_timezone_required(self):
        with self.assertRaises(Problem):
            self.scan('A','2026-10-10T08:00:00')

    def test_history_keeps_scheduled_hours_after_template_edit(self):
        self.scan('A','2026-10-10T08:00:00+08:00')
        with self.store.connect() as db:
            db.execute("UPDATE schedules SET end='20:00' WHERE id='day'")
            self.assertIn('16:15',db.execute('SELECT planned_out FROM sessions').fetchone()[0])

    def test_employee_details_are_snapshotted_for_history(self):
        result=self.scan('A','2026-10-10T08:00:00+08:00')
        with self.store.connect() as db:
            db.execute("UPDATE employees SET name='Changed Name' WHERE id='A'")
            original=db.execute('SELECT name FROM employee_snapshots WHERE session_id=?',(result['session_id'],)).fetchone()[0]
            self.assertEqual(original,'Test A')

    def test_zip_backup_restores_a_complete_database(self):
        import zipfile,sqlite3
        self.scan('A','2026-10-10T08:00:00+08:00')
        target=Path(self.temp.name)/'backups/full.zip'
        self.store.backup(target)
        with zipfile.ZipFile(target) as archive:
            restored=Path(self.temp.name)/'restored.sqlite3'
            restored.write_bytes(archive.read('attendance.sqlite3'))
        db=sqlite3.connect(restored)
        try:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],1)
        finally:
            db.close()

    def test_legacy_import_is_idempotent_and_handles_midnight(self):
        from import_history import import_history
        export=Path(self.temp.name)/'legacy.csv'
        export.write_text('worker_id,date,time_in,time_out,name,department,shift\nA,2026-10-01,20:00:00,08:00:00,Test A,PRODUCTION,SHIFT B\n')
        report=import_history(self.store,export)
        self.assertTrue(report['dry_run'])
        first=import_history(self.store,export,True)
        second=import_history(self.store,export,True)
        self.assertEqual(first['imported'],1)
        self.assertEqual(second['already_imported'],1)
        with self.store.connect() as db:
            self.assertIn('2026-10-02',db.execute('SELECT time_out FROM sessions').fetchone()[0])


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=TEST_ROOT)
        self.server=make_server(Path(self.temp.name)/'http.sqlite3',port=0,seed=False)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'
        self.cookie=''

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        assert Path(self.temp.name).resolve().is_relative_to(TEST_ROOT.resolve())
        self.temp.cleanup()

    def request(self,path,method='GET',data=None,headers=None):
        req=urllib.request.Request(self.base+path,method=method,data=json.dumps(data).encode() if data is not None else None,
                    headers={'Content-Type':'application/json','Cookie':self.cookie,**(headers or {})})
        try:
            with urllib.request.urlopen(req) as r:
                if r.headers.get('Set-Cookie'):
                    self.last_set_cookie=r.headers['Set-Cookie']
                    self.cookie=r.headers['Set-Cookie'].split(';')[0]
                raw=r.read()
                return r.status,json.loads(raw) if r.headers.get_content_type()=='application/json' else raw
        except urllib.error.HTTPError as e:
            return e.code,json.loads(e.read())

    def login(self):
        self.assertEqual(self.request('/api/auth/setup','POST',{'password':'test-password-long-enough'})[0],200)

    def test_login_persists_across_time_and_restart_until_logout(self):
        self.login()
        original=self.cookie
        self.assertIn('Max-Age=34560000',self.last_set_cookie)
        self.assertIn('HttpOnly',self.last_set_cookie)
        self.assertIn('SameSite=Strict',self.last_set_cookie)
        self.server.store=Store(self.server.store.path,seed=False)
        with patch('server.time.time',return_value=4_102_444_800):
            self.assertTrue(self.request('/api/auth/status')[1]['signed_in'])
            self.assertEqual(self.request('/api/state')[0],200)
        self.assertEqual(self.cookie,original)
        self.assertIn('Max-Age=34560000',self.last_set_cookie)
        self.assertEqual(self.request('/api/auth/logout','POST')[0],200)
        self.assertIn('Max-Age=0',self.last_set_cookie)
        self.cookie=original
        self.assertFalse(self.request('/api/auth/status')[1]['signed_in'])
        self.assertEqual(self.request('/api/state')[0],401)

    def test_upgrade_keeps_valid_sessions_without_reviving_expired_ones(self):
        import time
        self.login()
        with self.server.store.connect() as db:
            db.execute('UPDATE auth_sessions SET expires=?',(time.time()+3600,))
            db.execute('INSERT INTO auth_sessions VALUES(?,?)',(digest('expired-session'),time.time()-1))
        self.server.store=Store(self.server.store.path,seed=False)
        self.assertTrue(self.request('/api/auth/status')[1]['signed_in'])
        with self.server.store.connect() as db:
            self.assertEqual(db.execute('SELECT expires FROM auth_sessions WHERE token_hash=?',(digest(self.cookie.split('=',1)[1]),)).fetchone()[0],0)
        self.cookie='attendance_session=expired-session'
        self.assertFalse(self.request('/api/auth/status')[1]['signed_in'])

    def test_dashboard_clock_in_out_are_saved_audited_and_retry_safe(self):
        self.login()
        self.assertEqual(self.request('/api/auth/unlock-attendance','POST',{'password':'test-password-long-enough'})[0],200)
        self.request('/api/employees','POST',{'id':'123','name':'Test','team':'N','schedule_id':'normal'})
        body={'event_id':str(uuid.uuid4()),'employee_id':'123','action':'IN','timestamp':'2000-01-01T00:00:00+08:00'}
        status,first=self.request('/api/clock','POST',body)
        self.assertEqual(status,200)
        self.assertEqual(first['action'],'IN')
        self.assertEqual(first['source'],'dashboard')
        self.assertNotEqual(first['timestamp'],body['timestamp'])
        self.assertEqual(self.request('/api/clock','POST',body)[1],first)
        self.assertEqual(self.request('/api/state')[1]['employees'][0]['status'],'IN')
        # Deliberate administrator actions work within the kiosk repeat-scan cooldown.
        status,last=self.request('/api/clock','POST',{**body,'event_id':str(uuid.uuid4()),'action':'OUT'})
        self.assertEqual(status,200)
        self.assertEqual(last['action'],'OUT')
        state=self.request('/api/state')[1]
        self.assertEqual(state['employees'][0]['status'],'OUT')
        self.assertEqual(len(state['recent_events']),2)
        audit=self.request('/api/audit')[1]['audit']
        self.assertEqual(sum(row['actor']=='admin' and row['action'].startswith('scan_') for row in audit),2)

    def test_dashboard_clock_rejects_stale_action_and_archived_employee(self):
        self.login()
        self.assertEqual(self.request('/api/auth/unlock-attendance','POST',{'password':'test-password-long-enough'})[0],200)
        self.request('/api/employees','POST',{'id':'123','name':'Test','team':'N','schedule_id':'normal'})
        body={'event_id':str(uuid.uuid4()),'employee_id':'123','action':'OUT'}
        self.assertEqual(self.request('/api/clock','POST',body)[0],409)
        self.assertEqual(self.request('/api/clock','POST',{**body,'action':'IN'})[0],200)
        self.assertEqual(self.request('/api/clock','POST',{**body,'event_id':str(uuid.uuid4()),'action':'IN'})[0],409)
        self.request('/api/clock','POST',{**body,'event_id':str(uuid.uuid4()),'action':'OUT'})
        self.request('/api/employees/123','DELETE')
        self.assertEqual(self.request('/api/clock','POST',{**body,'event_id':str(uuid.uuid4()),'action':'IN'})[0],422)

    def test_dashboard_clock_is_admin_only(self):
        body={'event_id':str(uuid.uuid4()),'employee_id':'123','action':'IN'}
        self.assertEqual(self.request('/api/clock','POST',body)[0],401)
        self.login()
        token=self.request('/api/devices','POST',{'name':'Kiosk','scope':'kiosk'})[1]['token']
        self.cookie=''
        self.assertEqual(self.request('/api/clock','POST',body,{'Authorization':'Bearer '+token})[0],403)

    def test_clock_controls_require_password_and_can_be_locked(self):
        self.login()
        body={'employee_id':'123','action':'IN','event_id':str(uuid.uuid4())}
        self.assertFalse(self.request('/api/clock-access')[1]['unlocked'])
        self.assertEqual(self.request('/api/clock','POST',body)[0],403)
        self.assertEqual(self.request('/api/clock/batch','POST',{})[0],403)
        self.assertEqual(self.request('/api/auth/unlock-attendance','POST',{'password':'wrong'})[0],401)
        self.assertEqual(self.request('/api/auth/unlock-attendance','POST',{'password':'test-password-long-enough'})[0],200)
        self.assertTrue(self.request('/api/clock-access')[1]['unlocked'])
        self.request('/api/clock-access','DELETE')
        self.assertFalse(self.request('/api/clock-access')[1]['unlocked'])
        self.assertEqual(self.request('/api/clock','POST',body)[0],403)

    def test_batch_clock_results_retry_and_fixed_action(self):
        self.login()
        self.request('/api/auth/unlock-attendance','POST',{'password':'test-password-long-enough'})
        for eid in ('111','222','333'):
            self.request('/api/employees','POST',{'id':eid,'name':'Test '+eid,'team':'N','schedule_id':'normal'})
        self.request('/api/clock','POST',{'employee_id':'222','action':'IN','event_id':str(uuid.uuid4())})
        self.request('/api/employees/333','DELETE')
        body={'batch_id':str(uuid.uuid4()),'action':'IN','employee_ids':['111','222','333']}
        status,response=self.request('/api/clock/batch','POST',body)
        self.assertEqual(status,200)
        self.assertEqual([r['status'] for r in response['results']],['saved','skipped','error'])
        self.assertEqual(self.request('/api/clock/batch','POST',body)[1],response)
        state=self.request('/api/state')[1]
        self.assertEqual(len(state['recent_events']),3)
        self.assertEqual(self.request('/api/clock/batch','POST',{**body,'employee_ids':['111','111']})[0],400)
        self.assertEqual(self.request('/api/clock/batch','POST',{**body,'employee_ids':[]})[0],400)
        self.assertEqual(self.request('/api/clock/batch','POST',{**body,'action':'TOGGLE'})[0],400)
        status,response=self.request('/api/clock/batch','POST',{**body,'batch_id':str(uuid.uuid4()),'action':'OUT','employee_ids':['111','222']})
        self.assertEqual(status,200)
        self.assertTrue(all(r['status']=='saved' for r in response['results']))
        self.assertTrue(all(e['status']=='OUT' for e in self.request('/api/state')[1]['employees']))

    def test_batch_retry_preserves_originally_skipped_result(self):
        self.login()
        self.request('/api/auth/unlock-attendance','POST',{'password':'test-password-long-enough'})
        self.request('/api/employees','POST',{'id':'111','name':'Test','team':'N','schedule_id':'normal'})
        body={'batch_id':str(uuid.uuid4()),'action':'OUT','employee_ids':['111']}
        original=self.request('/api/clock/batch','POST',body)[1]
        self.assertEqual(original['results'][0]['status'],'skipped')
        # A skipped batch action must not trigger kiosk cooldown or block a real arrival.
        result=self.server.store.scan({'employee_id':'111','timestamp':original['results'][0]['timestamp'],'event_id':str(uuid.uuid4())},'test-kiosk')
        self.assertEqual(result['action'],'IN')
        self.assertEqual(self.request('/api/clock/batch','POST',body)[1],original)
        self.assertEqual(self.request('/api/state')[1]['employees'][0]['status'],'IN')

    def test_attendance_unlock_expires_without_expiring_login(self):
        import time
        self.login()
        self.request('/api/auth/unlock-attendance','POST',{'password':'test-password-long-enough'})
        with patch('server.time.time',return_value=time.time()+1801):
            self.assertFalse(self.request('/api/clock-access')[1]['unlocked'])
            self.assertEqual(self.request('/api/clock/batch','POST',{})[0],403)
            self.assertTrue(self.request('/api/auth/status')[1]['signed_in'])

    def test_concurrent_dashboard_clicks_only_clock_in_once(self):
        self.login()
        self.assertEqual(self.request('/api/auth/unlock-attendance','POST',{'password':'test-password-long-enough'})[0],200)
        self.request('/api/employees','POST',{'id':'123','name':'Test','team':'N','schedule_id':'normal'})
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.request('/api/clock','POST',{
                'event_id':str(uuid.uuid4()),'employee_id':'123','action':'IN'}),range(2)))
        self.assertEqual(sorted(status for status,_ in results),[200,409])
        state=self.request('/api/state')[1]
        self.assertEqual(state['employees'][0]['status'],'IN')
        self.assertEqual(len(state['recent_events']),1)

    def test_auth_and_employee_archive_audit(self):
        self.assertEqual(self.request('/api/employees')[0],401)
        self.login()
        e={'id':'123','name':"O'Neil Test",'team':'N','schedule_id':'normal'}
        self.assertEqual(self.request('/api/employees','POST',e)[0],200)
        self.assertEqual(self.request('/api/employees/123','PUT',{'nickname':'Neil'})[0],200)
        self.assertEqual(self.request('/api/employees/123','DELETE')[0],200)
        self.assertEqual(self.request('/api/employees')[1]['employees'][0]['active'],0)
        self.assertEqual(len(self.request('/api/audit')[1]['audit']),3)

    def test_read_only_integration_cannot_modify(self):
        self.login()
        r=self.request('/api/devices','POST',{'name':'Production','scope':'integration'})[1]
        self.cookie=''
        h={'Authorization':'Bearer '+r['token']}
        self.assertEqual(self.request('/api/employees',headers=h)[0],200)
        self.assertEqual(self.request('/api/employees','POST',{'id':'1','name':'test'},h)[0],403)

    def test_failed_write_does_not_report_success(self):
        self.login()
        self.assertEqual(self.request('/api/employees','POST',{'id':'bad_id','name':'Test'})[0],400)
        self.assertEqual(self.request('/api/employees')[1]['employees'],[])

    def test_team_control_settings_validate_and_apply_automatically(self):
        self.login()
        self.request('/api/employees','POST',{'id':'123','name':'Test','team':'A','schedule_id':'normal'})
        body={'team_schedules':{'A':'day','B':'night','N':'normal'},'team_overtime':{'A':True,'B':False,'N':False},'rotation':None}
        self.assertEqual(self.request('/api/settings','PUT',body)[0],200)
        self.assertEqual(self.request('/api/state')[1]['employees'][0]['effective_schedule']['id'],'day-ot')
        self.request('/api/employees/123','PUT',{'team':'B'})
        self.assertEqual(self.request('/api/state')[1]['employees'][0]['effective_schedule']['id'],'night')
        for invalid in ({'team_schedules':{'Z':'day'}},{'team_schedules':{'A':'missing'}},{'team_schedules':[]},{'team_overtime':{'A':'yes'}}):
            self.assertEqual(self.request('/api/settings','PUT',invalid)[0],400)
        self.assertEqual(self.request('/api/state')[1]['settings']['team_schedules'],body['team_schedules'])

    def test_group_settings_profile_fields_and_order_persist_with_validation(self):
        self.login()
        person={'id':'123','name':'Manager','department':'OFFICE','office_department':'HR','position':'GENERAL MANAGER','team':'N','schedule_id':'normal'}
        self.assertEqual(self.request('/api/employees','POST',person)[0],200)
        config={'team_schedules':{'A':'day','B':'night','N':'normal'},'team_overtime':{'A':True},'rotation':None}
        body={'schedule_groups':{'section:CONVERSION':config,'section:ROLL MAKING':{**config,'team_overtime':{'A':False}}},'employee_order':['123'],'employee_sort':'manual'}
        self.assertEqual(self.request('/api/settings','PUT',body)[0],200)
        state=self.request('/api/state')[1]
        self.assertEqual(state['employees'][0]['office_department'],'HR')
        self.assertEqual(state['settings']['employee_order'],['123'])
        invalid=[{'schedule_groups':[]},{'schedule_groups':{'section:WRONG':config}},
                 {'schedule_groups':{'section:CONVERSION':{**config,'team_overtime':{'A':'yes'}}}},
                 {'schedule_groups':{'section:CONVERSION':{**config,'rotation':[]}}},
                 {'employee_order':['123','123']},{'employee_order':['unknown']},{'employee_sort':'wrong'}]
        for value in invalid:
            self.assertEqual(self.request('/api/settings','PUT',value)[0],400,value)
        self.assertEqual(self.request('/api/state')[1]['settings']['schedule_groups'],body['schedule_groups'])
        self.assertEqual(self.request('/api/employees/123','PUT',{'department':'PRODUCTION','production_section':'ROLL MAKING'})[0],200)
        self.assertEqual(self.request('/api/employees/123','PUT',{'production_section':'wrong'})[0],400)
        self.assertEqual(self.request('/api/settings','PUT',{'schedule_groups':{}})[0],200)

    def test_team_date_assignments_can_differ_between_sections_but_not_overlap_in_one_scope(self):
        self.login()
        body={'team':'A','start_date':'2026-10-01','end_date':'2026-10-07','schedule_id':'day','scope':'section:CONVERSION'}
        self.assertEqual(self.request('/api/assignments','POST',body)[0],200)
        self.assertEqual(self.request('/api/assignments','POST',{**body,'scope':'section:ROLL MAKING','schedule_id':'night'})[0],200)
        self.assertEqual(self.request('/api/assignments','POST',body)[0],409)
        self.assertEqual(self.request('/api/assignments','POST',{**body,'scope':'line:FC'})[0],200)
        self.assertEqual(self.request('/api/assignments','POST',{**body,'scope':'bad'})[0],400)

    def test_attention_covers_all_dates_and_resolves_only_after_the_actual_fix(self):
        self.login()
        for eid,schedule in [('issue-one',None),('issue-two','normal')]:
            self.request('/api/employees','POST',{'id':eid,'name':eid,'team':'N','schedule_id':schedule})
        def scan(eid,when):
            return self.server.store.scan({'employee_id':eid,'timestamp':when,'event_id':str(uuid.uuid4())},'test')
        first=scan('issue-one','2025-01-01T08:00:00+08:00')
        scan('issue-one','2025-01-01T18:00:00+08:00')
        second=scan('issue-two','2025-01-02T07:45:00+08:00')
        review=scan('issue-two','2025-01-01T07:45:00+08:00')
        expected={'hours':1,'attendance':2,'scans':1,'total':4}
        self.assertEqual(self.request('/api/state')[1]['attention_summary'],expected)
        self.assertEqual(self.request('/api/attendance?from=2026-10-10&to=2026-10-10')[1]['sessions'],[])
        first_page=self.request('/api/attention?category=attendance&limit=1')[1]
        self.assertEqual(first_page['summary'],expected)
        self.assertEqual(first_page['items'][0]['id'],first['session_id'])
        second_page=self.request('/api/attention?category=attendance&limit=1&offset=1')[1]
        self.assertTrue(second_page['items'][0]['stale_session'])
        with self.server.store.connect() as db:
            db.execute('UPDATE sessions SET flags=? WHERE id=?',('["late_arrival","outside_scheduled_hours"]',second['session_id']))
        self.assertEqual(self.request('/api/state')[1]['attention_summary'],expected)  # flags + stale = one attendance issue
        self.assertEqual(self.request('/api/attention?category=hours')[1]['items'][0]['id'],'issue-one')
        self.request('/api/employees/issue-one','PUT',{'schedule_id':'normal'})
        self.assertEqual(self.request('/api/state')[1]['attention_summary']['total'],3)  # past flags remain
        for session in [*first_page['items'],*second_page['items']]:
            body={'time_in':session['time_in'],'time_out':session['time_out'] or '2025-01-02T17:40:00+08:00','work_date':session['work_date'],'resolve_flags':True,'reason':'Checked original attendance record'}
            self.assertEqual(self.request('/api/attendance/'+session['id'],'PUT',body)[0],200)
        self.assertEqual(self.request('/api/state')[1]['attention_summary']['total'],1)
        pending=self.request('/api/attention?category=scans')[1]['items']
        self.assertEqual(len(pending),1)
        self.assertEqual(json.loads(pending[0]['result'])['action'],'REVIEW')
        self.assertEqual(self.request('/api/review/'+pending[0]['id'],'POST',{'reason':'Checked older scan against saved attendance'})[0],200)
        self.assertEqual(self.request('/api/state')[1]['attention_summary']['total'],0)
        self.assertEqual(self.request('/api/attention?category=attendance')[1]['items'],[])

    def test_attention_pagination_reaches_every_issue_and_validates_parameters(self):
        self.login()
        with self.server.store.connect() as db:
            for index in range(105):
                self.server.store.insert_employee(db,{'id':'missing-'+str(index),'name':f'Employee {index:03d}','schedule_id':None})
        pages=[self.request('/api/attention?category=hours&limit=50&offset='+str(offset))[1] for offset in (0,50,100)]
        self.assertEqual([len(page['items']) for page in pages],[50,50,5])
        self.assertEqual(len({item['id'] for page in pages for item in page['items']}),105)
        for query in ('category=wrong','limit=101','limit=0','offset=-1','offset=abc'):
            self.assertEqual(self.request('/api/attention?'+query)[0],400)
        last=self.request('/api/attention?category=hours&offset=99999')[1]
        self.assertEqual(last['offset'],100)
        self.assertEqual(last['summary']['total'],105)

    def test_attention_is_only_available_to_administrators(self):
        self.assertEqual(self.request('/api/attention')[0],401)
        self.login()
        for scope in ('kiosk','integration'):
            token=self.request('/api/devices','POST',{'name':'Test '+scope,'scope':scope})[1]['token']
            self.assertEqual(self.request('/api/attention',headers={'Authorization':'Bearer '+token})[0],403)

    def test_pwa_assets_are_public_installable_and_updated_with_the_react_build(self):
        import hashlib,shutil
        from server import BASE
        static_base=Path(self.temp.name)/'static'
        shutil.copytree(BASE/'public',static_base/'dist')
        index=static_base/'dist/index.html'
        index.write_text('<html>New React build</html>',encoding='utf-8')
        with patch('server.BASE',static_base):
            for path,content_type in [('/manifest.webmanifest','application/manifest+json'),('/sw.js','application/javascript')]:
                with urllib.request.urlopen(self.base+path) as response:
                    self.assertEqual(response.headers.get_content_type(),content_type)
                    self.assertEqual(response.headers['Cache-Control'],'no-cache')
                    content=response.read()
                if path.endswith('webmanifest'):
                    manifest=json.loads(content)
                    self.assertEqual(manifest['display'],'standalone')
                    self.assertEqual(manifest['scope'],'/')
                    self.assertTrue({'192x192','512x512'}.issubset({icon['sizes'] for icon in manifest['icons']}))
                else:
                    version=hashlib.sha256(index.read_bytes()).hexdigest()[:12]
                    self.assertIn(('attendance-public-v1-'+version).encode(),content)
        self.assertEqual(self.request('/api/attention')[0],401)

    def test_phone_photo_upload_remains_admin_only_and_photos_are_not_cached(self):
        import base64,io
        from PIL import Image
        data=io.BytesIO()
        Image.new('RGB',(1600,1200),'gray').save(data,format='JPEG')
        body={'data':base64.b64encode(data.getvalue()).decode()}
        self.assertEqual(self.request('/api/photos','POST',body)[0],401)
        self.login()
        response=self.request('/api/photos','POST',body)
        self.assertEqual(response[0],200)
        photo_url=response[1]['url']
        request=urllib.request.Request(self.base+photo_url,headers={'Cookie':self.cookie})
        with urllib.request.urlopen(request) as uploaded:
            self.assertEqual(uploaded.headers['Cache-Control'],'no-store')
            image=Image.open(io.BytesIO(uploaded.read()))
            self.assertEqual(image.size,(600,450))
        self.cookie=''
        self.assertEqual(self.request(photo_url)[0],401)

    def test_manual_correction_requires_reason_and_preserves_audit(self):
        self.login()
        self.request('/api/employees','POST',{'id':'123','name':'Test','team':'N','schedule_id':'normal'})
        body={'employee_id':'123','work_date':'2026-10-10','time_in':'2026-10-10T07:45:00+08:00','time_out':'2026-10-10T17:40:00+08:00','reason':'Verified supervisor record'}
        self.assertEqual(self.request('/api/manual-attendance','POST',body)[0],200)
        sid=self.request('/api/attendance?from=2026-10-10&to=2026-10-10')[1]['sessions'][0]['id']
        self.assertEqual(self.request('/api/attendance/'+sid,'PUT',{**body,'reason':''})[0],400)
        self.assertEqual(self.request('/api/attendance/'+sid,'PUT',{**body,'time_out':'2026-10-10T18:00:00+08:00'})[0],200)
        self.assertEqual(self.request('/api/audit')[1]['audit'][0]['action'],'attendance_corrected')

    def test_overlap_and_cross_origin_are_rejected(self):
        self.login()
        body={'team':'A','start_date':'2026-10-01','end_date':'2026-10-07','schedule_id':'day'}
        self.assertEqual(self.request('/api/assignments','POST',body)[0],200)
        self.assertEqual(self.request('/api/assignments','POST',body)[0],409)
        self.assertEqual(self.request('/api/devices','POST',{'name':'Test'}, {'Origin':'https://unrelated.example'})[0],403)

    def test_backup_is_consistent_and_downloadable(self):
        self.login()
        status,blob=self.request('/api/backup')
        self.assertEqual(status,200)
        self.assertTrue(blob.startswith(b'SQLite format 3'))


if __name__=='__main__':
    unittest.main(verbosity=2)
