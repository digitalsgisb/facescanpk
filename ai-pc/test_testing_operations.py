import json
import unittest
import uuid
import zipfile
from datetime import datetime,timedelta
from unittest.mock import patch
import test_server as legacy
from server import KL


class PlantOperationsTests(unittest.TestCase):
    setUp=legacy.HttpTests.setUp
    tearDown=legacy.HttpTests.tearDown
    request=legacy.HttpTests.request
    login=legacy.HttpTests.login

    def setUp(self):
        legacy.HttpTests.setUp(self)
        self.login()
        for eid,base in [('PK','PORT KLANG'),('SD','SENDAYAN')]:
            self.assertEqual(self.request('/api/employees','POST',{'id':eid,'name':eid,'base':base,'team':'N','line':'FC','photo_url':'https://example.invalid/photo.jpg','schedule_id':'normal','position':'OLD'})[0],200)

    def unlock(self,password='test-password-long-enough'):
        self.assertEqual(self.request('/api/auth/unlock-attendance','POST',{'password':password})[0],200)

    def open_session(self,eid='PK',when='2026-01-01T08:00:00+08:00'):
        return self.server.store.scan({'employee_id':eid,'event_id':str(uuid.uuid4()),'timestamp':when},'test-pi')

    def staff_login(self,base='PORT KLANG',role='admin'):
        self.assertEqual(self.request('/api/staff/plant-user','PUT',{'password':'plant-password-long','role':role,'base':base})[0],200)
        self.cookie=''
        self.assertEqual(self.request('/api/auth/login','POST',{'username':'plant-user','password':'plant-password-long'})[0],200)

    def reset_body(self):
        return {'request_id':str(uuid.uuid4()),'reason':'Testing finished, fresh start','confirmation':'CLOCK OUT EVERYONE'}

    def payload(self,base='PORT KLANG',eid='PK'):
        return {'format':'sgi-employees-v1','employees':[{'id':eid,'name':'Updated Name','company':'Test Company','base':base,'employment_department':'PRODUCTION','job_type':'SR LEADER, PROD'}]}

    def test_reset_closes_stale_and_archived_open_sessions_and_retry_does_not_close_new_ones(self):
        self.open_session('PK');self.open_session('SD')
        with self.server.store.connect() as db:
            db.execute("UPDATE employees SET active=0 WHERE id='SD'")
        self.unlock();body=self.reset_body()
        status,result=self.request('/api/clock/reset','POST',body)
        self.assertEqual(status,200);self.assertEqual(result['closed'],2)
        backup=self.server.store.path.parent/'backups'/result['backup']
        self.assertTrue(zipfile.is_zipfile(backup))
        with self.server.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT count(*) FROM sessions WHERE time_out IS NULL').fetchone()[0],0)
            self.assertTrue(all('testing_reset' in json.loads(r['flags']) for r in db.execute('SELECT flags FROM sessions')))
        # Even a successful old request retried after a new arrival must be harmless.
        with self.server.store.connect() as db:
            db.execute("INSERT INTO sessions(id,employee_id,work_date,time_in,flags,source) VALUES('new','PK','2026-10-20',?,'[]','test')",(datetime.now(KL).isoformat(),))
        self.assertEqual(self.request('/api/clock/reset','POST',body)[1],result)
        with self.server.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM sessions WHERE time_out IS NULL").fetchone()[0],1)

    def test_reset_requires_unlock_confirmation_and_successful_backup(self):
        self.open_session()
        body=self.reset_body()
        self.assertEqual(self.request('/api/clock/reset','POST',body)[0],403)
        self.unlock()
        self.assertEqual(self.request('/api/clock/reset','POST',{**body,'confirmation':''})[0],400)
        with patch.object(self.server.store,'backup',side_effect=OSError('disk full')):
            self.assertEqual(self.request('/api/clock/reset','POST',body)[0],500)
        with self.server.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sessions WHERE time_out IS NULL').fetchone()[0],1)

    def test_plant_account_sees_only_own_plant_and_cannot_change_scope(self):
        self.open_session('PK');self.open_session('SD')
        self.staff_login()
        self.assertEqual(self.request('/api/auth/status')[1]['base'],'PORT KLANG')
        for route,key in [('/api/state','employees'),('/api/employees','employees')]:
            self.assertEqual([e['id'] for e in self.request(route)[1][key]],['PK'])
        sessions=self.request('/api/attendance?from=2026-01-01&to=2026-01-02')[1]['sessions']
        self.assertEqual([s['employee_id'] for s in sessions],['PK'])
        self.assertEqual(self.request('/api/employees/SD','PUT',{'name':'Blocked'})[0],404)
        self.assertEqual(self.request('/api/employees/PK','PUT',{'base':'SENDAYAN'})[0],403)
        for route in ('/api/staff','/api/audit','/api/backup'):
            self.assertEqual(self.request(route)[0],403)
        self.assertEqual(self.request('/api/devices','POST',{'name':'No'})[0],403)
        self.unlock('plant-password-long')
        self.assertEqual(self.request('/api/clock/batch','POST',{'employee_ids':['PK','SD'],'action':'OUT','batch_id':str(uuid.uuid4())})[0],404)
        self.assertEqual(self.request('/api/clock/reset','POST',self.reset_body())[1]['closed'],1)
        with self.server.store.connect() as db:
            self.assertEqual([r['employee_id'] for r in db.execute('SELECT employee_id FROM sessions WHERE time_out IS NULL')],['SD'])

    def test_previewed_import_preserves_working_details_and_exact_sheet_position(self):
        payload=self.payload()
        self.open_session()
        status,preview=self.request('/api/employee-import/preview','POST',{'payload':payload})
        self.assertEqual(status,200);self.assertEqual(preview['summary']['update'],1)
        self.assertEqual(self.request('/api/employees')[1]['employees'][0]['position'],'OLD')
        body={'payload':payload,'preview_token':preview['preview_token'],'request_id':str(uuid.uuid4())}
        status,result=self.request('/api/employee-import/apply','POST',body)
        self.assertEqual(status,200)
        self.assertEqual(self.request('/api/employee-import/apply','POST',body)[1],result)
        people={e['id']:e for e in self.request('/api/employees')[1]['employees']}
        self.assertEqual(people['PK']['position'],'SR LEADER, PROD')
        self.assertEqual(people['PK']['team'],'N');self.assertEqual(people['PK']['line'],'FC')
        self.assertEqual(people['PK']['photo_url'],'https://example.invalid/photo.jpg')
        self.assertEqual(people['PK']['status'],'IN')
        self.assertEqual(people['SD']['position'],'OLD')
        second=self.request('/api/employee-import/preview','POST',{'payload':payload})[1]
        self.assertEqual(second['summary']['unchanged'],1)

    def test_import_is_atomic_and_rejects_stale_preview_duplicates_and_cross_plant_rows(self):
        payload=self.payload()
        report=self.request('/api/employee-import/preview','POST',{'payload':payload})[1]
        self.request('/api/employees/PK','PUT',{'nickname':'New nickname'})
        body={'payload':payload,'preview_token':report['preview_token'],'request_id':str(uuid.uuid4())}
        self.assertEqual(self.request('/api/employee-import/apply','POST',body)[0],409)
        duplicate={**payload,'employees':payload['employees']*2}
        self.assertEqual(self.request('/api/employee-import/preview','POST',{'payload':duplicate})[0],400)
        self.staff_login()
        self.assertEqual(self.request('/api/employee-import/preview','POST',{'payload':self.payload('SENDAYAN','SD')})[0],403)
        self.assertEqual(self.request('/api/employee-import/preview','POST',{'payload':self.payload('PORT KLANG','SD')})[0],403)

    def test_plant_kiosk_receives_and_scans_only_assigned_location(self):
        token=self.request('/api/devices','POST',{'name':'PK Pi','scope':'kiosk','base':'PORT KLANG'})[1]['token']
        headers={'Authorization':'Bearer '+token,'Cookie':''}
        data=self.request('/api/employees',headers=headers)[1]
        self.assertEqual([e['id'] for e in data['employees']],['PK'])
        self.assertNotIn('photo_url',data['employees'][0])
        self.assertEqual(self.request('/api/scans','POST',{'employee_id':'SD'},headers)[0],404)
        self.request('/api/heartbeat','POST',{'metadata_version':data['metadata_version']},headers)
        people={e['id']:e for e in self.request('/api/employees')[1]['employees']}
        self.assertEqual(people['PK']['metadata_sync']['status'],'synced')
        self.assertEqual(people['SD']['metadata_sync']['status'],'no_kiosk')

    def test_developer_account_oversees_both_plants(self):
        self.assertEqual(self.request('/api/staff/developer','PUT',{'password':'developer-private-password','role':'admin','base':''})[0],200)
        self.cookie=''
        self.assertEqual(self.request('/api/auth/login','POST',{'username':'developer','password':'developer-private-password'})[0],200)
        self.assertEqual(self.request('/api/auth/status')[1]['base'],'')
        self.assertEqual(len(self.request('/api/state')[1]['employees']),2)
        self.assertEqual(self.request('/api/staff')[0],200)
        self.unlock('developer-private-password')

    def test_plant_photo_access_and_manual_order_do_not_leak_other_employees(self):
        import base64,io
        from PIL import Image
        raw=io.BytesIO();Image.new('RGB',(10,10),'gray').save(raw,format='JPEG')
        url=self.request('/api/photos','POST',{'data':base64.b64encode(raw.getvalue()).decode()})[1]['url']
        self.request('/api/employees/SD','PUT',{'photo_url':url})
        self.request('/api/settings','PUT',{'employee_order':['SD','PK']})
        self.staff_login()
        self.assertEqual(self.request(url)[0],404)
        self.assertEqual(self.request('/api/employees/SD/photo','DELETE')[0],404)
        self.assertEqual(self.request('/api/employees/PK','PUT',{'photo_url':url})[0],403)
        self.assertEqual(self.request('/api/state')[1]['settings']['employee_order'],['PK'])

    def test_import_audit_failure_rolls_back_all_changes(self):
        payload=self.payload()
        report=self.request('/api/employee-import/preview','POST',{'payload':payload})[1]
        with patch.object(self.server.store,'audit',side_effect=RuntimeError('simulated audit failure')):
            self.assertEqual(self.request('/api/employee-import/apply','POST',{'payload':payload,'preview_token':report['preview_token'],'request_id':str(uuid.uuid4())})[0],500)
        people={e['id']:e for e in self.request('/api/employees')[1]['employees']}
        self.assertEqual(people['PK']['name'],'PK')
        self.assertEqual(people['PK']['position'],'OLD')

    def test_future_dated_open_session_prevents_partial_reset(self):
        self.open_session('PK')
        self.open_session('SD',(datetime.now(KL)+timedelta(minutes=1)).isoformat())
        self.unlock()
        self.assertEqual(self.request('/api/clock/reset','POST',self.reset_body())[0],409)
        with self.server.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sessions WHERE time_out IS NULL').fetchone()[0],2)


if __name__=='__main__': unittest.main()
