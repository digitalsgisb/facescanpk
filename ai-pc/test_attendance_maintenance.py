import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from server import Store, KL, Problem
from attendance_maintenance import run_normal_clockout, decorate_enrollment, validate_enrollment


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        test_root = Path(__file__).resolve().parent/'runtime'/'tests'
        test_root.mkdir(parents=True,exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=test_root)
        self.store = Store(Path(self.temp.name)/'test.sqlite3', seed=False)
        self.cutoff = datetime(2026,10,2,3,tzinfo=KL)

    def tearDown(self):
        self.temp.cleanup()

    def session(self,eid,schedule='normal',work_date='2026-10-01',time_out=None):
        with self.store.connect() as db:
            self.store.insert_employee(db,{'id':eid,'name':eid,'schedule_id':schedule,'team':'N'})
            start,end=self.store.planned({'start':'07:45','end':'17:40'},work_date)
            db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                       (eid,eid,work_date,start.isoformat(),time_out,schedule,schedule,
                        start.isoformat(),end.isoformat(),json.dumps(['late_arrival']),'test'))

    def test_cutoff_only_normal_once_and_audited(self):
        self.session('normal');self.session('night','night-ot');self.session('day','day')
        self.session('closed',time_out='2026-10-01T18:00:00+08:00')
        self.session('today',work_date='2026-10-02')
        self.assertEqual(run_normal_clockout(self.store,self.cutoff-timedelta(seconds=1)),0)
        self.assertEqual(run_normal_clockout(self.store,self.cutoff),1)
        self.assertEqual(run_normal_clockout(self.store,self.cutoff),0)
        with self.store.connect() as db:
            row=db.execute("SELECT * FROM sessions WHERE id='normal'").fetchone()
            self.assertEqual(datetime.fromisoformat(row['time_out']),self.cutoff)
            self.assertEqual(json.loads(row['flags']),['late_arrival','automatic_clock_out'])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit WHERE action='normal_automatic_clock_out'").fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions WHERE time_out IS NULL').fetchone()[0],3)

    def test_restart_catches_up_at_original_cutoff_and_disabled_stays_open(self):
        self.session('old')
        restarted=Store(self.store.path,seed=False)
        with restarted.connect() as db:
            db.execute("UPDATE settings SET value='0' WHERE key='normal_auto_out_enabled'")
        self.assertEqual(run_normal_clockout(restarted,self.cutoff+timedelta(days=2)),0)
        with restarted.connect() as db:
            db.execute("UPDATE settings SET value='1' WHERE key='normal_auto_out_enabled'")
        self.assertEqual(run_normal_clockout(restarted,self.cutoff+timedelta(days=2)),1)
        with restarted.connect() as db:
            self.assertEqual(datetime.fromisoformat(db.execute('SELECT time_out FROM sessions').fetchone()[0]),self.cutoff)

    def test_midnight_and_overnight_normal_exclusion(self):
        self.session('midnight');self.session('overnight')
        with self.store.connect() as db:
            db.execute("UPDATE settings SET value='0' WHERE key='normal_auto_out_hour'")
            db.execute("UPDATE sessions SET planned_out='2026-10-02T08:00:00+08:00' WHERE id='overnight'")
        self.assertEqual(run_normal_clockout(self.store,self.cutoff.replace(hour=0)),1)
        with self.store.connect() as db:
            self.assertIsNone(db.execute("SELECT time_out FROM sessions WHERE id='overnight'").fetchone()[0])

    def test_enrollment_fresh_pending_registered_and_unknown(self):
        with self.store.connect() as db:
            db.execute("INSERT INTO devices(id,name,token_hash,scope,last_seen,health) VALUES('pi','Pi','token','kiosk',?,?)",
                       (self.cutoff.isoformat(),json.dumps({'face_employee_ids':['yes']})))
            people=[{'id':'yes'},{'id':'no'}]
            self.assertEqual([e['face_registration'] for e in decorate_enrollment(db,people,self.cutoff)],['registered','pending'])
            self.assertEqual([e['face_registration'] for e in decorate_enrollment(db,people,self.cutoff+timedelta(seconds=90))],['unknown','unknown'])
            db.execute("INSERT INTO devices(id,name,token_hash,scope) VALUES('old','Old Pi','old-token','kiosk')")
            self.assertEqual([e['face_registration'] for e in decorate_enrollment(db,people,self.cutoff)],['registered','unknown'])
            db.execute("UPDATE devices SET active=0 WHERE id='old'")
            db.execute("UPDATE devices SET health='{}' WHERE id='pi'")
            self.assertEqual(decorate_enrollment(db,people,self.cutoff)[1]['face_registration'],'unknown')

    def test_invalid_registration_report(self):
        for value in (None,'yes',[None],['X'*41]):
            with self.assertRaises(Problem):validate_enrollment({'face_employee_ids':value},Problem)
        validate_enrollment({'face_employee_ids':[]},Problem)
        validate_enrollment({},Problem)

    def test_next_day_scan_opens_a_new_session_after_auto_out(self):
        self.session('normal')
        run_normal_clockout(self.store,self.cutoff)
        result=self.store.scan({'employee_id':'normal','event_id':'next-day-clock-in',
                                'timestamp':'2026-10-02T07:45:00+08:00'},'pi')
        self.assertEqual(result['action'],'IN')
        self.assertEqual(result['work_date'],'2026-10-02')

    def test_stale_review_does_not_block_clock_in_out_or_retries(self):
        self.session('old','day')
        data={'employee_id':'old','event_id':'rollover-new-clock-in',
              'timestamp':'2026-10-02T08:00:00+08:00'}
        result=self.store.scan(data,'pi')
        self.assertEqual(result['action'],'IN')
        self.assertEqual(self.store.scan(data,'pi'),result)
        out=self.store.scan({**data,'event_id':'rollover-new-clock-out',
                             'timestamp':'2026-10-02T16:15:00+08:00'},'pi')
        self.assertEqual(out['action'],'OUT')
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0],2)
            old=db.execute("SELECT * FROM sessions WHERE id='old'").fetchone()
            self.assertIn('missing_clock_out',json.loads(old['flags']))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit WHERE action='stale_session_released_for_review'").fetchone()[0],1)
            self.assertGreater(self.store.attention_summary(db)['attendance'],0)

    def test_explicit_admin_clock_in_and_out_work_with_stale_session(self):
        self.session('new-in','day');self.session('old-out','day')
        for eid,action in [('new-in','IN'),('old-out','OUT')]:
            result=self.store.scan({'employee_id':eid,'event_id':'admin-'+eid+'-action',
                                    'timestamp':'2026-10-02T08:00:00+08:00','action':action},
                                   'admin',dashboard=True)
            self.assertEqual(result['action'],action)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT time_out FROM sessions WHERE id='old-out'").fetchone()[0],
                             '2026-10-02T08:00:00+08:00')

    def test_review_only_events_do_not_hold_up_later_scans(self):
        self.session('review','day')
        first=self.store.scan({'employee_id':'review','event_id':'review-first-scan',
                               'timestamp':'2026-10-01T16:15:00+08:00'},'pi')
        self.assertEqual(first['action'],'OUT')
        late=self.store.scan({'employee_id':'review','event_id':'review-delayed-event',
                              'timestamp':'2026-10-01T07:00:00+08:00'},'pi')
        self.assertEqual(late['action'],'REVIEW')
        next_in=self.store.scan({'employee_id':'review','event_id':'review-next-day-in',
                                 'timestamp':'2026-10-02T08:00:00+08:00'},'pi')
        self.assertEqual(next_in['action'],'IN')
        with self.store.connect() as db:
            self.assertEqual(self.store.attention_summary(db)['scans'],1)

    def test_face_reports_respect_plant_when_supported(self):
        with self.store.connect() as db:
            if 'base' not in {row['name'] for row in db.execute('PRAGMA table_info(devices)')}:
                self.skipTest('Single-site app has no plant scoping')
            db.execute("INSERT INTO devices(id,name,token_hash,scope,last_seen,health,base) VALUES('pi','Pi','token','kiosk',?,?,'PORT KLANG')",
                       (self.cutoff.isoformat(),json.dumps({'face_employee_ids':['other']})))
            people=[{'id':'other','base':'SENDAYAN'},{'id':'local','base':'PORT KLANG'}]
            self.assertEqual([e['face_registration'] for e in decorate_enrollment(db,people,self.cutoff)],['unknown','pending'])


if __name__=='__main__':
    unittest.main()
