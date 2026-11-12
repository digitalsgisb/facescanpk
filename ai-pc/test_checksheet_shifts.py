import copy
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
import checksheet_shifts as shifts
from server import Store

NOW = datetime(2026, 11, 2, 8, 45, tzinfo=timezone.utc)
ENV = {'CHECKSHEET_API_URL': 'http://checksheet:3700', 'CHECKSHEET_SHIFT_FEED_TOKEN': 'test-token-of-at-least-32-characters'}


def record(**changes):
    result = {'id': 'ABB2-day', 'line': 'ABB2', 'shiftId': '20261102-Day-ABB2', 'date': '2026-11-02', 'shift': 'Day', 'groupId': 'conversion-port-klang',
              'employeeIds': ['E1'], 'overtime': False, 'startAt': '2026-11-02T00:00:00Z', 'endAt': '2026-11-02T08:15:00Z', 'greyAt': '2026-11-02T08:45:00Z', 'graceMinutes': 30}
    result.update(changes)
    return result


def payload(*records, now=NOW):
    return {'schema': 1, 'generatedAt': now.isoformat(), 'shifts': list(records or [record()])}


def person(**changes):
    result = {'id': 'E1', 'name': 'Operator', 'active': 1, 'department': 'PRODUCTION', 'base': 'PORT KLANG', 'production_section': 'CONVERSION', 'line': 'FC', 'status': 'IN', 'session': {'time_in': '2026-11-02T08:00:00+08:00'}}
    result.update(changes)
    return result


class Opener:
    def __init__(self, data=None, failure=False):
        self.data, self.failure, self.requests = data or payload(), failure, []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        if self.failure:
            raise ValueError('secret upstream body or token')
        return io.BytesIO(json.dumps(self.data).encode())


class ChecksheetShiftTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name)/'attendance.sqlite3', seed=False)

    def install(self, data=None):
        self.assertTrue(shifts.sync_once(self.store, ENV, Opener(data), NOW))

    def decorate(self, now=NOW, employee=None):
        with self.store.connect() as db:
            return shifts.decorate(db, [employee or person()], now)[0]

    def test_grace_boundary_before_at_and_after(self):
        self.assertTrue(shifts.sync_once(self.store, ENV, Opener(), NOW-timedelta(seconds=2)))
        self.assertEqual(self.decorate(NOW-timedelta(seconds=1))['checksheet_shift']['state'], 'grace')
        self.assertEqual(self.decorate()['checksheet_shift']['state'], 'finished')
        self.assertEqual(self.decorate(NOW+timedelta(seconds=1))['checksheet_shift']['state'], 'finished')

    def test_15_minute_option(self):
        self.install(payload(record(graceMinutes=15, greyAt='2026-11-02T08:30:00Z')))
        self.assertEqual(self.decorate()['checksheet_shift']['state'], 'finished')

    def test_ot_update_replaces_cutoff_and_clears_finished_state(self):
        self.install()
        self.assertEqual(self.decorate()['checksheet_shift']['state'], 'finished')
        self.install(payload(record(overtime=True, endAt='2026-11-02T12:00:00Z', greyAt='2026-11-02T12:30:00Z')))
        self.assertEqual(self.decorate()['checksheet_shift']['state'], 'active')
        self.assertTrue(self.decorate()['checksheet_shift']['overtime'])

    def test_clock_status_and_sessions_are_unchanged(self):
        self.install()
        employee = person()
        original = copy.deepcopy(employee)
        result = self.decorate(employee=employee)
        self.assertEqual(result['status'], 'IN')
        self.assertEqual(result['session'], original['session'])
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)

    def test_ids_division_site_department_and_active_status_are_required(self):
        self.install()
        for changes in ({'id': 'other'}, {'base': 'SENDAYAN'}, {'production_section': 'ROLL MAKING'}, {'department': 'OFFICE'}, {'active': 0}, {'base': ''}):
            self.assertIsNone(self.decorate(employee=person(**changes))['checksheet_shift'])

    def test_roll_making_port_klang_is_separate(self):
        self.install(payload(record(groupId='roll-making-port-klang')))
        self.assertIsNone(self.decorate()['checksheet_shift'])
        self.assertEqual(self.decorate(employee=person(production_section='ROLL MAKING'))['checksheet_shift']['state'], 'finished')

    def test_new_shift_wins_over_old_finished_shift_and_future_shift_waits(self):
        new = record(id='ABB3-night', line='ABB3', shift='Night', startAt='2026-11-02T08:40:00Z', endAt='2026-11-02T16:30:00Z', greyAt='2026-11-02T17:00:00Z')
        self.install(payload(record(), new))
        self.assertEqual(self.decorate()['checksheet_shift']['line'], 'ABB3')
        self.assertEqual(self.decorate()['checksheet_shift']['state'], 'active')
        new['startAt'] = '2026-11-02T09:00:00Z'
        self.install(payload(record(), new))
        self.assertEqual(self.decorate()['checksheet_shift']['state'], 'finished')

    def test_night_shift_and_grace_cross_midnight(self):
        moment = datetime(2026, 11, 3, 0, 30, tzinfo=timezone.utc)
        data = payload(record(shift='Night', overtime=True, startAt='2026-11-02T12:00:00Z', endAt='2026-11-03T00:00:00Z', greyAt='2026-11-03T00:30:00Z'), now=moment)
        self.assertTrue(shifts.sync_once(self.store, ENV, Opener(data), moment))
        self.assertEqual(self.decorate(moment)['checksheet_shift']['state'], 'finished')

    def test_failure_and_expired_cache_suppress_grey_and_recover(self):
        self.install()
        self.assertIsNone(self.decorate(NOW+timedelta(seconds=91))['checksheet_shift'])
        self.assertFalse(shifts.sync_once(self.store, ENV, Opener(failure=True), NOW))
        self.assertIsNone(self.decorate()['checksheet_shift'])
        with self.store.connect() as db:
            self.assertNotIn('secret', json.dumps(shifts.status(db, NOW)))
        self.install()
        self.assertEqual(self.decorate()['checksheet_shift']['state'], 'finished')

    def test_feed_restart_and_removed_employee_links(self):
        self.install()
        self.store = Store(self.store.path, seed=False)
        self.assertEqual(self.decorate()['checksheet_shift']['state'], 'finished')
        self.install(payload(record(employeeIds=[])))
        self.assertIsNone(self.decorate()['checksheet_shift'])

    def test_disabling_connection_clears_cached_board_control(self):
        self.install()
        self.assertFalse(shifts.sync_once(self.store, {}, Opener(), NOW))
        self.assertIsNone(self.decorate()['checksheet_shift'])

    def test_auth_destination_and_token_stay_server_side(self):
        opener = Opener()
        self.assertTrue(shifts.sync_once(self.store, ENV, opener, NOW))
        request, timeout = opener.requests[0]
        self.assertEqual(request.full_url, 'http://checksheet:3700/api/integrations/shifts')
        self.assertEqual(request.get_header('Authorization'), 'Bearer '+ENV['CHECKSHEET_SHIFT_FEED_TOKEN'])
        self.assertEqual(timeout, 5)
        self.assertNotIn(ENV['CHECKSHEET_SHIFT_FEED_TOKEN'], json.dumps(self.decorate()))
        for url in ('http://user:password@host', 'http://host/path', 'http://host?secret=token', 'file:///tmp/feed'):
            bad = Opener()
            self.assertFalse(shifts.sync_once(self.store, {**ENV, 'CHECKSHEET_API_URL': url}, bad, NOW))
            self.assertFalse(bad.requests)

    def test_invalid_or_stale_feed_never_replaces_good_cache(self):
        self.install()
        for data in (payload(now=NOW-timedelta(minutes=5)), payload(record(graceMinutes=0)), payload(record(greyAt='2026-11-02T08:15:00Z')), payload(record(startAt='2026-11-02T00:00')), payload(record(groupId='unknown')), payload(record(), record())):
            self.assertFalse(shifts.sync_once(self.store, ENV, Opener(data), NOW))
        with self.store.connect() as db:
            stored = json.loads(db.execute('SELECT payload FROM checksheet_board_state').fetchone()[0])
            self.assertEqual(stored, payload())


if __name__ == '__main__':
    unittest.main()
