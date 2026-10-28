import io
import unittest
from openpyxl import load_workbook
import test_server as legacy
import test_plant_workflows as plant


class ExportTests(unittest.TestCase):
    setUp=legacy.HttpTests.setUp
    tearDown=legacy.HttpTests.tearDown
    request=legacy.HttpTests.request
    login=legacy.HttpTests.login
    setup_people=plant.PlantWorkflowTests.setup_people
    site=plant.PlantWorkflowTests.site

    def test_roster_without_attendance_includes_dates_location_and_overnight_shift(self):
        self.setup_people()
        self.request('/api/employees/PK','PUT',{'schedule_id':'night-ot'})
        status,raw=self.request('/api/employee-export','POST',{'from':'2026-01-01','to':'2026-01-02','employee_ids':['PK']})
        self.assertEqual(status,200)
        sheet=load_workbook(io.BytesIO(raw)).active
        rows=list(sheet.values)
        self.assertEqual(len(rows),3)
        self.assertEqual(rows[1][4],'PORT KLANG')
        self.assertEqual(rows[1][15:18],('2026-01-01 20:00','2026-01-02 08:00','Yes'))
        self.assertEqual(sheet.auto_filter.ref,'A1:R3')

    def test_plant_scope_and_invalid_range(self):
        self.setup_people();self.site()
        data={'from':'2026-01-01','to':'2026-01-01','employee_ids':['SD']}
        self.assertEqual(self.request('/api/employee-export','POST',data)[0],200)
        self.assertEqual(self.request('/api/employee-export','POST',{**data,'employee_ids':['PK']})[0],403)
        self.assertEqual(self.request('/api/employee-export','POST',{**data,'to':'2025-01-01'})[0],400)
