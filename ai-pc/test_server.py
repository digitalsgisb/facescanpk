import json
import tempfile
import threading
import unittest
import uuid
import urllib.request
import urllib.error
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
            db.execute('INSERT INTO assignments VALUES(?,?,?,?,?,?)',('override','A',None,'2026-10-09','2026-10-09','normal'))
            self.assertEqual(self.store.resolve_schedule(db,e,date(2026,10,9))['id'],'normal')

    def test_archived_employee_cannot_scan(self):
        with self.store.connect() as db:
            db.execute("UPDATE employees SET active=0 WHERE id='A'")
        with self.assertRaises(Problem):
            self.scan('A','2026-10-10T08:00:00+08:00')

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
                    self.cookie=r.headers['Set-Cookie'].split(';')[0]
                raw=r.read()
                return r.status,json.loads(raw) if r.headers.get_content_type()=='application/json' else raw
        except urllib.error.HTTPError as e:
            return e.code,json.loads(e.read())

    def login(self):
        self.assertEqual(self.request('/api/auth/setup','POST',{'password':'test-password-long-enough'})[0],200)

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
