"""Opt-in contract test against an installed Smart Checksheet checkout, using synthetic data."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
import checksheet_shifts
from server import make_server, digest, KL


@unittest.skipUnless(os.environ.get('CHECKSHEET_TEST_DIR') and shutil.which('node'), 'Set CHECKSHEET_TEST_DIR to an installed Checksheet checkout for the two-app contract test')
class TwoAppShiftContract(unittest.TestCase):
    def test_actual_shift_details_reach_attendance_and_edit_without_touching_clock_records(self):
        with tempfile.TemporaryDirectory() as temp:
            attendance = make_server(Path(temp)/'attendance.sqlite3', port=0, seed=False)
            thread = threading.Thread(target=attendance.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(attendance.server_close)
            self.addCleanup(attendance.shutdown)
            with attendance.store.connect() as db:
                attendance.store.insert_employee(db, {'id': 'E1', 'name': 'Synthetic operator', 'department': 'PRODUCTION', 'line': 'FC', 'checksheet_group': 'fc1', 'base': 'PORT KLANG', 'production_section': 'CONVERSION', 'active': 1})
                db.execute('INSERT INTO devices(id,name,token_hash,scope) VALUES(?,?,?,?)', ('bridge', 'Contract test', digest('read-only-contract-token'), 'integration'))
            with socket.socket() as free:
                free.bind(('127.0.0.1', 0))
                port = free.getsockname()[1]
            token = 'contract-test-feed-token-of-at-least-32-characters'
            env = {**os.environ, 'PORT': str(port), 'HOST': '127.0.0.1', 'APP_MODE': 'attendance', 'DATABASE_PATH': ':memory:',
                   'ADMIN_PASSWORD': 'Contract-test-password-12345', 'ADMIN_USERNAME': 'developer', 'CHECKSHEET_SHIFT_FEED_TOKEN': token,
                   'ATTENDANCE_API_URL': f'http://127.0.0.1:{attendance.server_port}', 'ATTENDANCE_TOKEN': 'read-only-contract-token',
                   'ATTENDANCE_GROUPS': json.dumps([{'id': 'fc1', 'label': 'FC Line 1', 'lines': ['FC'], 'assignment': 'fc1', 'accountLines': ['ABB2']}])}
            child = subprocess.Popen([shutil.which('node'), 'server/index.js'], cwd=os.environ['CHECKSHEET_TEST_DIR'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.addCleanup(lambda: child.wait(timeout=10))
            self.addCleanup(child.terminate)
            base = f'http://127.0.0.1:{port}'
            deadline = time.monotonic()+10
            while True:
                try:
                    with urlopen(base+'/api/health', timeout=1):
                        break
                except OSError:
                    if time.monotonic() > deadline:
                        self.fail('Checksheet startup failed')
                    time.sleep(.05)
            cookie = ''
            def call(path, data=None, method=None):
                nonlocal cookie
                request = Request(base+'/api'+path, data=json.dumps(data).encode() if data is not None else None,
                                  method=method or ('POST' if data is not None else 'GET'), headers={'Content-Type': 'application/json', 'Cookie': cookie})
                with urlopen(request, timeout=8) as response:
                    if response.headers.get('Set-Cookie'):
                        cookie = response.headers['Set-Cookie'].split(';')[0]
                    return json.load(response)
            call('/auth/login', {'username': 'developer', 'password': 'Contract-test-password-12345'})
            call('/executive/line-groups', {'lineGroups': {'ABB2': 'conversion-port-klang'}}, 'PUT')
            self.assertEqual(call('/shift-board/options')['employees'][0]['id'], 'E1')
            moment = datetime.now(KL)
            daytime = 8 <= moment.hour < 20
            date = moment.date() if moment.hour >= 8 else moment.date()-timedelta(days=1)
            form = {'date': str(date), 'shift': 'Day' if daytime else 'Night', 'overtime': True, 'supervisor': 'Supervisor', 'leader': 'Leader',
                    'forming': ['Forming'], 'waterjet': ['Waterjet'], 'assembly': ['Assembly'], 'quality': 'Inspector', 'attendanceEmployeeIds': ['E1'], 'boardGraceMinutes': 30}
            call('/actions/shift', form)
            sync_env = {'CHECKSHEET_API_URL': base, 'CHECKSHEET_SHIFT_FEED_TOKEN': token}
            self.assertTrue(checksheet_shifts.sync_once(attendance.store, sync_env))
            with attendance.store.connect() as db:
                employee = attendance.store.employees(db)[0]
                self.assertEqual(employee['checksheet_shift']['line'], 'ABB2')
                self.assertTrue(employee['checksheet_shift']['overtime'])
                self.assertEqual(employee['status'], 'OUT')
                self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)
            active = call('/state')['shift']
            self.assertEqual(active['attendanceEmployeeIds'], ['E1'])
            edit = {**form, 'boardGraceMinutes': 15, 'expectedShiftId': active['id'], 'expectedVersion': active.get('editVersion', 0)}
            # When both choices cover the current time, exercise a real OT -> NO OT edit too.
            if daytime and (moment.hour, moment.minute) < (16, 15):
                edit['overtime'] = False
            call('/actions/shift-edit', edit)
            self.assertTrue(checksheet_shifts.sync_once(attendance.store, sync_env))
            with attendance.store.connect() as db:
                employee = attendance.store.employees(db)[0]
                self.assertEqual(employee['checksheet_shift']['graceMinutes'], 15)
                self.assertEqual(employee['checksheet_shift']['overtime'], edit['overtime'])
                self.assertEqual(employee['status'], 'OUT')
            call('/actions/end', {})
            self.assertTrue(checksheet_shifts.sync_once(attendance.store, sync_env))
            with attendance.store.connect() as db:
                employee = attendance.store.employees(db)[0]
                self.assertEqual(employee['checksheet_shift']['state'], 'grace')
                self.assertEqual(employee['status'], 'OUT')
