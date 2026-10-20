"""HTTP regression coverage using disposable databases and generated test images."""
import base64
import io
import json
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import test_server as legacy
from server import Store, digest


class EmployeeAdminTests(unittest.TestCase):
    setUp = legacy.HttpTests.setUp
    tearDown = legacy.HttpTests.tearDown
    request = legacy.HttpTests.request
    login = legacy.HttpTests.login

    def employee(self, eid='111', **fields):
        self.assertEqual(self.request('/api/employees','POST',{'id':eid,'name':'Test Employee',**fields})[0],200)

    def photo(self, fmt='JPEG'):
        raw=io.BytesIO()
        Image.new('RGB',(100,80),'gray').save(raw,format=fmt)
        return self.request('/api/photos','POST',{'data':base64.b64encode(raw.getvalue()).decode()})

    def kiosk(self):
        token=self.request('/api/devices','POST',{'name':'Test Pi','scope':'kiosk'})[1]['token']
        return {'Authorization':'Bearer '+token,'Cookie':''}

    def test_named_employee_admin_cannot_escalate_or_access_attendance(self):
        self.login()
        body={'password':'long-staff-password','role':'employee_admin','active':True}
        self.assertEqual(self.request('/api/staff/hr-user','PUT',body)[0],200)
        admin_cookie=self.cookie
        self.cookie=''
        self.assertEqual(self.request('/api/auth/login','POST',{'username':'hr-user','password':body['password']})[0],200)
        self.assertEqual(self.request('/api/auth/status')[1]['role'],'employee_admin')
        self.employee()
        state=self.request('/api/state')[1]
        self.assertNotIn('session',state['employees'][0])
        self.assertEqual(state['recent_events'],[])
        for route,method,data in [('/api/audit','GET',None),('/api/backup','GET',None),('/api/staff','GET',None),
                ('/api/staff/hacker','PUT',body),('/api/attendance','GET',None),('/api/devices','POST',{}),
                ('/api/settings','PUT',{}),('/api/retention','POST',{}),('/api/auth/unlock-attendance','POST',{'password':'test-password-long-enough'})]:
            self.assertEqual(self.request(route,method,data)[0],403,route)
        staff_cookie=self.cookie
        self.cookie=admin_cookie
        self.assertEqual(self.request('/api/staff/hr-user','PUT',{'active':False})[0],200)
        self.cookie=staff_cookie
        self.assertEqual(self.request('/api/employees')[0],401)

    def test_staff_password_and_role_changes_revoke_sessions_and_never_audit_password(self):
        self.login()
        self.request('/api/staff/hr','PUT',{'password':'long-staff-password','role':'employee_admin'})
        self.request('/api/staff/hr','PUT',{'password':'different-password-long','role':'admin'})
        audit=json.dumps(self.request('/api/audit')[1])
        self.assertNotIn('long-staff-password',audit)
        self.assertNotIn('different-password-long',audit)
        self.cookie=''
        self.assertEqual(self.request('/api/auth/login','POST',{'username':'hr','password':'different-password-long'})[0],200)
        self.assertEqual(self.request('/api/auth/status')[1]['role'],'admin')
        with patch('server.time.time',return_value=time.time()+9*3600):
            self.assertEqual(self.request('/api/state')[0],401)

    def test_consent_is_append_only_atomic_and_not_assumed_for_existing_employees(self):
        self.login()
        self.employee()
        self.assertEqual(self.request('/api/state')[1]['employees'][0]['consents'],{})
        consent={'purpose':'employee_data','granted':True,'notice':'HR notice v1','evidence':'Signed form 111'}
        self.assertEqual(self.request('/api/employees/111/consents','POST',consent)[0],200)
        self.assertEqual(self.request('/api/employees/111/consents','POST',{**consent,'granted':False})[0],200)
        history=self.request('/api/employees/111/consents')[1]['consents']
        self.assertEqual([r['granted'] for r in history],[0,1])
        self.assertEqual(history[0]['actor'],'admin')
        self.assertEqual(self.request('/api/employees','POST',{'id':'222','name':'Test','consent_record':{**consent,'evidence':''}})[0],400)
        self.assertEqual(len(self.request('/api/employees')[1]['employees']),1)
        self.assertEqual(self.request('/api/employees/111/consents','POST',{**consent,'purpose':'biometric'})[0],400)

    def test_metadata_only_sync_requires_durable_receipt_and_tracks_updates(self):
        self.login()
        self.employee(photo_url='https://example.invalid/profile.jpg')
        headers=self.kiosk()
        response=self.request('/api/employees',headers=headers)[1]
        e=response['employees'][0]
        self.assertNotIn('photo_url',e)
        self.assertNotIn('consents',e)
        self.assertNotIn('session',e)
        self.assertIn('department',e)
        version=response['metadata_version']
        self.request('/api/heartbeat','POST',{},headers)
        self.assertEqual(self.request('/api/state')[1]['employees'][0]['metadata_sync']['status'],'pending')
        self.assertEqual(self.request('/api/heartbeat','POST',{'metadata_version':version},headers)[0],200)
        self.assertEqual(self.request('/api/state')[1]['employees'][0]['metadata_sync']['status'],'synced')
        self.request('/api/employees/111','PUT',{'name':'Updated','active':False})
        self.assertEqual(self.request('/api/state')[1]['employees'][0]['metadata_sync']['status'],'pending')
        self.assertNotEqual(self.request('/api/employees',headers=headers)[1]['metadata_version'],version)
        self.assertEqual(self.request('/api/heartbeat','POST',{'metadata_version':'bad'},headers)[0],400)
        self.assertEqual(self.request('/uploads/'+'a'*32+'.jpg',headers=headers)[0],403)

    def test_photo_validation_metadata_stripping_and_audited_deletion(self):
        self.login()
        self.employee()
        self.assertEqual(self.photo('GIF')[0],400)
        for bad in ({'data':'not base64'},{'data':123},{'data':base64.b64encode(b'<svg/>').decode()}):
            self.assertEqual(self.request('/api/photos','POST',bad)[0],400)
        status,result=self.photo()
        self.assertEqual(status,200)
        url=result['url']
        saved=self.server.store.path.parent/'uploads'/url.split('/')[-1]
        self.request('/api/employees/111','PUT',{'photo_url':url})
        self.assertTrue(saved.exists())
        self.assertEqual(self.request('/api/employees/111/photo','DELETE')[0],200)
        self.assertFalse(saved.exists())
        self.assertEqual(self.request(url)[0],404)
        self.assertEqual(self.request('/api/employees')[1]['employees'][0]['photo_url'],'')
        self.assertEqual(self.request('/api/audit')[1]['audit'][0]['action'],'profile_photo_deleted')

    def test_retention_only_removes_old_tracked_unreferenced_photos(self):
        self.login()
        orphan=self.photo()[1]['url']
        referenced=self.photo()[1]['url']
        recent=self.photo()[1]['url']
        self.employee(photo_url=referenced,active=False)
        folder=self.server.store.path.parent/'uploads'
        untracked=folder/('f'*32+'.jpg')
        untracked.write_bytes(b'legacy image sentinel')
        with self.server.store.connect() as db:
            db.execute("UPDATE profile_photos SET created_at='2000-01-01T00:00:00+08:00' WHERE url IN (?,?)",(orphan,referenced))
        self.assertEqual(self.request('/api/retention','POST',{'unreferenced_photo_days':30})[1]['deleted_photos'],1)
        self.assertFalse((folder/orphan.split('/')[-1]).exists())
        self.assertTrue((folder/referenced.split('/')[-1]).exists())
        self.assertTrue((folder/recent.split('/')[-1]).exists())
        self.assertTrue(untracked.exists())
        self.assertEqual(self.request('/api/retention','POST',{'unreferenced_photo_days':0})[0],400)

    def test_shared_photo_survives_until_last_reference_removed(self):
        self.login()
        url=self.photo()[1]['url']
        self.employee(photo_url=url)
        self.employee('222',photo_url=url)
        self.request('/api/employees/111/photo','DELETE')
        self.assertEqual(self.request(url)[0],200)
        self.request('/api/employees/222/photo','DELETE')
        self.assertEqual(self.request(url)[0],404)

    def test_stale_phone_edit_does_not_overwrite_another_edit(self):
        self.login()
        self.employee()
        old=self.request('/api/employees')[1]['employees'][0]
        self.assertEqual(self.request('/api/employees/111','PUT',{**old,'name':'First edit'})[0],200)
        self.assertEqual(self.request('/api/employees/111','PUT',{**old,'name':'Stale edit'})[0],409)
        self.assertEqual(self.request('/api/employees')[1]['employees'][0]['name'],'First edit')

    def test_browser_origin_uses_published_port_and_rejects_other_authorities(self):
        self.login()
        headers={'Host':'attendance.example:3800','Origin':'http://attendance.example:3800'}
        self.assertEqual(self.request('/api/employees','POST',{'id':'111','name':'Phone registration'},headers)[0],200)
        for origin in ('https://other.example:3800','http://attendance.example:5173','http://attendance.example'):
            self.assertEqual(self.request('/api/employees/111','PUT',{'name':'Wrong origin'},{**headers,'Origin':origin})[0],403)

    def test_failed_delete_audit_keeps_photo_and_reference_intact(self):
        self.login()
        url=self.photo()[1]['url']
        self.employee(photo_url=url)
        with patch.object(self.server.store,'audit',side_effect=RuntimeError('simulated audit failure')):
            self.assertEqual(self.request('/api/employees/111/photo','DELETE')[0],500)
        self.assertEqual(self.request(url)[0],200)
        self.assertEqual(self.request('/api/employees')[1]['employees'][0]['photo_url'],url)

    def test_delete_disk_failure_revokes_access_and_cleanup_retries(self):
        self.login()
        url=self.photo()[1]['url']
        self.employee(photo_url=url)
        saved=self.server.store.path.parent/'uploads'/url.split('/')[-1]
        with patch('pathlib.Path.unlink',side_effect=PermissionError('simulated disk failure')):
            self.assertEqual(self.request('/api/employees/111/photo','DELETE')[0],200)
        self.assertTrue(saved.exists())
        self.assertEqual(self.request(url)[0],404)
        self.assertEqual(self.request('/api/employees/111','PUT',{'photo_url':url})[0],400)
        self.request('/api/retention','POST',{'unreferenced_photo_days':30})
        self.assertFalse(saved.exists())

    def test_upload_strips_exif_and_reencodes_to_jpeg(self):
        self.login()
        image=Image.new('RGB',(200,150),'gray')
        exif=Image.Exif()
        exif[0x010E]='private EXIF sentinel'
        raw=io.BytesIO()
        image.save(raw,format='JPEG',exif=exif)
        status,result=self.request('/api/photos','POST',{'data':base64.b64encode(raw.getvalue()).decode()})
        self.assertEqual(status,200)
        content=self.request(result['url'])[1]
        saved=Image.open(io.BytesIO(content))
        self.assertEqual(saved.format,'JPEG')
        self.assertFalse(saved.getexif())
        self.assertNotIn(b'private EXIF sentinel',content)


if __name__=='__main__':
    unittest.main()
