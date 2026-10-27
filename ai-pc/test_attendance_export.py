import io
import unittest
import urllib.request
from xml.etree import ElementTree as ET
from zipfile import ZipFile
import test_server as legacy
import test_plant_workflows as plant_tests

NS = {'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


class ExportTests(unittest.TestCase):
    setUp = legacy.HttpTests.setUp
    tearDown = legacy.HttpTests.tearDown
    request = legacy.HttpTests.request
    login = legacy.HttpTests.login
    setup_people = plant_tests.PlantWorkflowTests.setup_people
    site = plant_tests.PlantWorkflowTests.site
    session = plant_tests.PlantWorkflowTests.session

    def sheet(self, path):
        status, raw = self.request(path)
        self.assertEqual(status, 200)
        with ZipFile(io.BytesIO(raw)) as archive:
            for name in archive.namelist():
                ET.fromstring(archive.read(name))
            return ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))

    def test_dates_search_overnight_and_literal_employee_text(self):
        self.setup_people()
        with self.server.store.connect() as db:
            db.execute("UPDATE employees SET name=? WHERE id='PK'", ('=SUM(1,2) & 工人',))
        self.session(start='2026-01-01T20:00:00+08:00',end='2026-01-02T08:00:00+08:00')
        self.session(start='2026-01-02T08:00:00+08:00',end=None)
        self.session(start='2026-01-03T08:00:00+08:00')
        self.session(eid='SD')
        root = self.sheet('/api/attendance/export?from=2026-01-01&to=2026-01-02&search=pk')
        rows = root.findall('s:sheetData/s:row', NS)
        self.assertEqual(len(rows), 3)
        texts = [e.text for e in root.findall('.//s:t', NS)]
        self.assertIn('=SUM(1,2) & 工人', texts)
        self.assertIn('2026-01-02 08:00:00', texts)
        self.assertIn('Still in', texts)
        self.assertEqual(root.findall('.//s:f', NS), [])
        self.assertIn('12.0', [e.text for e in root.findall('.//s:v', NS)])

    def test_empty_export_has_headers_and_download_metadata(self):
        self.login()
        path='/api/attendance/export?from=2026-01-01&to=2026-01-02'
        root=self.sheet(path)
        self.assertEqual(len(root.findall('s:sheetData/s:row', NS)), 1)
        req=urllib.request.Request(self.base+path,headers={'Cookie':self.cookie})
        with urllib.request.urlopen(req) as response:
            self.assertEqual(response.headers.get_content_type(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            self.assertIn('attendance_2026-01-01_to_2026-01-02.xlsx',response.headers['Content-Disposition'])
            self.assertEqual(response.headers['Cache-Control'],'no-store')

    def test_invalid_ranges_and_auth(self):
        path='/api/attendance/export'
        self.assertEqual(self.request(path)[0],401)
        self.login()
        for query in ('','?from=bad&to=2026-01-01','?from=2026-01-02&to=2026-01-01','?from=2024-01-01&to=2026-01-01'):
            self.assertEqual(self.request(path+query)[0],400)
        for scope in ('integration','kiosk'):
            token=self.request('/api/devices','POST',{'name':scope,'scope':scope})[1]['token']
            self.assertEqual(self.request(path+'?from=2026-01-01&to=2026-01-02',headers={'Authorization':'Bearer '+token})[0],403)

    def test_plant_export_is_scoped_and_employee_admin_is_denied(self):
        self.setup_people()
        self.session(eid='PK')
        self.session(eid='SD')
        self.site()
        root=self.sheet('/api/attendance/export?from=2026-01-01&to=2026-01-01')
        texts=[e.text for e in root.findall('.//s:t', NS)]
        self.assertIn('SD',texts)
        self.assertNotIn('PK',texts)
        self.cookie=''
        self.assertEqual(self.request('/api/auth/login','POST',{'password':'test-password-long-enough'})[0],200)
        self.site(role='employee_admin')
        self.assertEqual(self.request('/api/attendance/export?from=2026-01-01&to=2026-01-01')[0],403)


if __name__ == '__main__':
    unittest.main()
