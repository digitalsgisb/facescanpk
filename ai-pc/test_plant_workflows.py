import json
import unittest
import uuid
from datetime import datetime,timedelta,date
from unittest.mock import patch
import test_server as legacy
from server import KL,Store,Problem
import plant_workflows as workflows


class PlantWorkflowTests(unittest.TestCase):
    setUp=legacy.HttpTests.setUp
    tearDown=legacy.HttpTests.tearDown
    request=legacy.HttpTests.request
    login=legacy.HttpTests.login

    def setup_people(self):
        self.login()
        for eid,base,team in [('PK','PORT KLANG','A'),('SD','SENDAYAN','C')]:
            self.assertEqual(self.request('/api/employees','POST',{'id':eid,'name':eid,'base':base,'team':team,'schedule_id':'normal'})[0],200)

    def site(self,base='SENDAYAN',role='admin'):
        self.assertEqual(self.request('/api/staff/site','PUT',{'password':'site-test-password-long','role':role,'base':base})[0],200)
        self.cookie=''
        self.assertEqual(self.request('/api/auth/login','POST',{'username':'site','password':'site-test-password-long'})[0],200)

    def session(self,eid='PK',sid=None,start='2026-01-01T08:00:00+08:00',end='2026-01-01T17:00:00+08:00',flags='["late_arrival"]'):
        sid=sid or str(uuid.uuid4())
        with self.server.store.connect() as db:
            db.execute('INSERT INTO sessions(id,employee_id,work_date,time_in,time_out,flags,source) VALUES(?,?,?,?,?,?,?)',(sid,eid,start[:10],start,end,flags,'test'))
        return sid

    def preview(self,category='attendance',**kwargs):
        data={'category':category,'base':'',**kwargs}
        status,result=self.request('/api/reviews/preview','POST',data)
        self.assertEqual(status,200,result)
        return {**data,**result,'reason':'Verified testing backlog','request_id':str(uuid.uuid4())}

    def test_bulk_review_handles_250_sessions_without_changing_times_or_flags(self):
        self.setup_people()
        for i in range(250):self.session(sid='bulk-'+str(i))
        body=self.preview()
        self.assertEqual(body['count'],250)
        status,result=self.request('/api/reviews/bulk','POST',body)
        self.assertEqual(status,200);self.assertEqual(result['reviewed'],250)
        self.assertEqual(self.request('/api/reviews/bulk','POST',body)[1],result)
        self.assertEqual(self.request('/api/state')[1]['attention_summary']['attendance'],0)
        with self.server.store.connect() as db:
            rows=list(db.execute('SELECT * FROM sessions'))
            self.assertEqual(len(rows),250)
            self.assertTrue(all(r['time_out']=='2026-01-01T17:00:00+08:00' and json.loads(r['flags'])==['late_arrival'] for r in rows))
            self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE action='attendance_bulk_reviewed'").fetchone()[0],250)
            db.execute("UPDATE sessions SET flags='[\"early_departure\"]' WHERE id='bulk-0'")
        self.assertEqual(self.request('/api/state')[1]['attention_summary']['attendance'],1)

    def test_review_preview_stale_rows_and_cross_plant_attempts_are_rejected(self):
        self.setup_people();pk=self.session();sd=self.session('SD')
        body=self.preview()
        self.session()
        self.assertEqual(self.request('/api/reviews/bulk','POST',body)[0],409)
        self.site()
        self.assertEqual(self.request('/api/reviews/preview','POST',{'category':'attendance','base':'PORT KLANG'})[0],403)
        self.assertEqual(self.request('/api/reviews/preview','POST',{'category':'attendance','base':'SENDAYAN','ids':[pk]})[0],409)
        own=self.preview(base='SENDAYAN',ids=[sd])
        self.assertEqual(self.request('/api/reviews/bulk','POST',own)[1]['reviewed'],1)
        self.assertEqual(self.request('/api/attention?category=attendance')[1]['total'],0)

    def test_bulk_scan_review_does_not_apply_scans_or_close_open_sessions(self):
        self.setup_people()
        opened=self.server.store.scan({'employee_id':'PK','event_id':str(uuid.uuid4()),'timestamp':'2026-01-02T08:00:00+08:00'},'test')
        review=self.server.store.scan({'employee_id':'PK','event_id':str(uuid.uuid4()),'timestamp':'2026-01-01T08:00:00+08:00'},'test')
        self.assertEqual(review['action'],'REVIEW')
        body=self.preview('scans')
        self.assertEqual(self.request('/api/reviews/bulk','POST',body)[1]['reviewed'],1)
        self.assertEqual(self.request('/api/review')[1]['events'],[])
        with self.server.store.connect() as db:
            self.assertIsNone(db.execute('SELECT time_out FROM sessions WHERE id=?',(opened['session_id'],)).fetchone()[0])

    def test_disabling_reviews_hides_backlog_and_reenabling_restores_it(self):
        self.setup_people();self.session('SD')
        self.assertEqual(self.request('/api/plant-controls','PUT',{'base':'SENDAYAN','review_enabled':False})[0],200)
        self.assertEqual(self.request('/api/state')[1]['attention_summary']['attendance'],0)
        with self.server.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],1)
        self.assertEqual(self.request('/api/plant-controls','PUT',{'base':'SENDAYAN','review_enabled':True})[0],200)
        self.assertEqual(self.request('/api/state')[1]['attention_summary']['attendance'],1)

    def test_shift_rotation_and_template_times_are_plant_specific(self):
        self.setup_people()
        config={'base':'SENDAYAN','team_schedules':{'C':'day','D':'night','N':'normal'},'team_overtime':{'C':False,'D':True,'N':False},
                'rotation':{'anchor_date':'2026-01-01','interval_days':7,'schedule_ids':['day','night'],'teams':['C','D']},
                'schedules':{'day':{'name':'Sendayan Day','start':'09:00','end':'18:00','ot':0}}}
        self.site()
        self.assertEqual(self.request('/api/plant-controls','PUT',config)[0],200)
        self.assertEqual(self.request('/api/plant-controls')[1]['teams'],['C','D','N'])
        self.assertEqual(self.request('/api/plant-controls','PUT',{**config,'base':'PORT KLANG'})[0],403)
        self.assertEqual(self.request('/api/plant-controls','PUT',{'team_schedules':{'A':'day'}})[0],400)
        with self.server.store.connect() as db:
            sd=dict(db.execute("SELECT * FROM employees WHERE id='SD'").fetchone())
            pk=dict(db.execute("SELECT * FROM employees WHERE id='PK'").fetchone())
            self.assertEqual(self.server.store.resolve_schedule(db,sd,date(2026,1,1))['start'],'09:00')
            self.assertEqual(self.server.store.resolve_schedule(db,{**sd,'team':'D'},date(2026,1,1))['id'],'night-ot')
            self.assertEqual(self.server.store.resolve_schedule(db,sd,date(2026,1,8))['id'],'night')
            self.assertEqual(self.server.store.resolve_schedule(db,pk,date(2026,1,1))['start'],'07:45')
            self.assertEqual(db.execute("SELECT start FROM schedules WHERE id='day'").fetchone()[0],'08:00')

    def test_only_all_plant_admin_can_set_automatic_clockout(self):
        self.setup_people()
        self.assertEqual(self.request('/api/automatic-clockout','PUT',{'enabled':True,'clock_time':'18:30'})[0],200)
        self.assertEqual(self.request('/api/automatic-clockout')[1]['clock_time'],'18:30')
        self.assertEqual(self.request('/api/automatic-clockout','PUT',{'enabled':True,'clock_time':'25:00'})[0],400)
        self.site()
        self.assertEqual(self.request('/api/automatic-clockout')[0],403)
        self.assertEqual(self.request('/api/automatic-clockout','PUT',{'enabled':False,'clock_time':'18:00'})[0],403)

    def scheduled(self):
        now=datetime.now(KL).replace(hour=18,minute=0,second=0,microsecond=0)
        with self.server.store.connect() as db:
            workflows.save_clockout(self.server.store,db,{'enabled':True,'clock_time':'18:00'},'developer',Problem,(now-timedelta(hours=2)).isoformat())
        return now

    def test_scheduled_clockout_closes_all_plants_once_and_preserves_later_arrivals(self):
        self.setup_people();cutoff=self.scheduled()
        self.assertEqual(self.request('/api/employees','POST',{'id':'SD2','name':'Second Sendayan','base':'SENDAYAN','team':'D'})[0],200)
        self.session('PK','early-pk',(cutoff-timedelta(hours=8)).isoformat(),None,'[]')
        self.session('SD2','early-sd',(cutoff-timedelta(hours=8)).isoformat(),None,'[]')
        self.session('SD','late-sd',(cutoff+timedelta(minutes=10)).isoformat(),None,'[]')
        result=workflows.run_clockout(self.server.store,cutoff+timedelta(minutes=30))
        self.assertEqual(result['closed'],2);self.assertTrue(result['backup'])
        self.assertIsNone(workflows.run_clockout(self.server.store,cutoff+timedelta(minutes=31)))
        with self.server.store.connect() as db:
            self.assertEqual(db.execute("SELECT time_out FROM sessions WHERE id='early-pk'").fetchone()[0],cutoff.isoformat())
            self.assertEqual(db.execute("SELECT time_out FROM sessions WHERE id='early-sd'").fetchone()[0],cutoff.isoformat())
            self.assertIsNone(db.execute("SELECT time_out FROM sessions WHERE id='late-sd'").fetchone()[0])
            self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE action='scheduled_clock_out'").fetchone()[0],2)

    def test_schedule_persists_and_catches_up_after_midnight_without_touching_new_shift(self):
        self.setup_people();cutoff=self.scheduled()
        self.session('PK','old',(cutoff-timedelta(hours=8)).isoformat(),None,'[]')
        self.session('SD','new',(cutoff+timedelta(hours=6)).isoformat(),None,'[]')
        restarted=Store(self.server.store.path,seed=False)
        result=workflows.run_clockout(restarted,cutoff+timedelta(hours=7))
        self.assertEqual(result['closed'],1)
        self.assertEqual(result['date'],cutoff.date().isoformat())
        with restarted.connect() as db:self.assertIsNone(db.execute("SELECT time_out FROM sessions WHERE id='new'").fetchone()[0])

    def test_schedule_does_not_run_immediately_when_enabled_after_cutoff(self):
        self.setup_people();cutoff=self.scheduled()
        with self.server.store.connect() as db:db.execute('UPDATE automatic_clockout SET activated_at=?',((cutoff+timedelta(minutes=1)).isoformat(),))
        self.session('PK','open',(cutoff-timedelta(hours=8)).isoformat(),None,'[]')
        self.assertIsNone(workflows.run_clockout(self.server.store,cutoff+timedelta(minutes=2)))

    def test_resaving_unchanged_time_does_not_skip_a_due_run(self):
        self.setup_people();cutoff=self.scheduled()
        self.session('PK','open',(cutoff-timedelta(hours=8)).isoformat(),None,'[]')
        with self.server.store.connect() as db:
            workflows.save_clockout(self.server.store,db,{'enabled':True,'clock_time':'18:00'},'developer',Problem,(cutoff+timedelta(seconds=1)).isoformat())
        self.assertEqual(workflows.run_clockout(self.server.store,cutoff+timedelta(seconds=2))['closed'],1)

    def test_scheduled_backup_failure_preserves_open_sessions_for_retry(self):
        self.setup_people();cutoff=self.scheduled()
        self.session('PK','open',(cutoff-timedelta(hours=8)).isoformat(),None,'[]')
        with patch.object(self.server.store,'backup',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):workflows.run_clockout(self.server.store,cutoff)
        with self.server.store.connect() as db:
            self.assertIsNone(db.execute("SELECT time_out FROM sessions WHERE id='open'").fetchone()[0])
            self.assertEqual(db.execute('SELECT count(*) FROM automatic_clockout_runs').fetchone()[0],0)
        self.assertEqual(workflows.run_clockout(self.server.store,cutoff)['closed'],1)


if __name__=='__main__':unittest.main()
