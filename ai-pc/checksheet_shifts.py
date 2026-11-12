"""Read confirmed Checksheet shifts for board presentation; never alter clock records."""
import json
import os
import threading
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

GROUPS = {
    'conversion-port-klang': ('PORT KLANG', 'CONVERSION'),
    'conversion-sendayan': ('SENDAYAN', 'CONVERSION'),
    'roll-making-port-klang': ('PORT KLANG', 'ROLL MAKING'),
}
MAX_BYTES = 2_000_000


def instant(value):
    if not isinstance(value, str):
        raise ValueError('Timezone-aware timestamp required')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timezone-aware timestamp required')
    return result


def migrate(db):
    db.execute('CREATE TABLE IF NOT EXISTS checksheet_board_state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT, received_at TEXT, error INTEGER NOT NULL DEFAULT 0)')


def validate(payload, now):
    if not isinstance(payload, dict) or payload.get('schema') != 1 or abs((instant(payload.get('generatedAt'))-now).total_seconds()) > 120:
        raise ValueError('Invalid or stale feed')
    rows = payload.get('shifts')
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError('Invalid shift list')
    ids = set()
    for row in rows:
        if not isinstance(row, dict) or row.get('groupId') not in GROUPS or not isinstance(row.get('id'), str) or not row['id'] or row['id'] in ids:
            raise ValueError('Invalid shift identity')
        ids.add(row['id'])
        if type(row.get('overtime')) is not bool or type(row.get('graceMinutes')) is not int or row['graceMinutes'] not in (15, 30):
            raise ValueError('Invalid shift settings')
        people = row.get('employeeIds')
        if not isinstance(people, list) or len(people) > 500 or any(not isinstance(p, str) or not p or len(p) > 100 for p in people) or len(set(people)) != len(people):
            raise ValueError('Invalid employee IDs')
        start, end, grey = (instant(row.get(key)) for key in ('startAt', 'endAt', 'greyAt'))
        if not start <= end <= start + timedelta(hours=24) or grey != end + timedelta(minutes=row['graceMinutes']):
            raise ValueError('Invalid shift boundaries')
        if any(not isinstance(row.get(key), str) or not row[key] or len(row[key]) > 150 for key in ('line', 'shiftId', 'date', 'shift')):
            raise ValueError('Invalid shift labels')
    return payload


def status(db, now=None):
    now = now or datetime.now(timezone.utc)
    row = db.execute('SELECT * FROM checksheet_board_state WHERE id=1').fetchone()
    if not row:
        return {'state': 'waiting' if os.environ.get('CHECKSHEET_API_URL') else 'disabled'}
    fresh = row['received_at'] and 0 <= (now-instant(row['received_at'])).total_seconds() <= 90
    return {'state': 'live' if fresh and not row['error'] else 'unavailable', 'updatedAt': row['received_at']}


def decorate(db, employees, now=None):
    now = now or datetime.now(timezone.utc)
    health = status(db, now)
    row = db.execute('SELECT payload FROM checksheet_board_state WHERE id=1').fetchone()
    shifts = json.loads(row['payload'])['shifts'] if row and row['payload'] else []
    for employee in employees:
        employee['checksheet_shift'] = None
        if health['state'] != 'live':
            continue
        section = employee.get('production_section') or ('ROLL MAKING' if employee.get('line') == 'ROLL MAKING' else 'CONVERSION')
        if not employee.get('active') or (employee.get('department') or '').strip().upper() != 'PRODUCTION':
            continue
        group = ((employee.get('base') or '').strip().upper(), section.strip().upper())
        matches = [shift for shift in shifts if GROUPS[shift['groupId']] == group and employee['id'] in shift['employeeIds'] and instant(shift['startAt']) <= now]
        if not matches:
            continue
        # A new on-duty shift wins over an older completed shift, even across lines.
        current = [shift for shift in matches if now < instant(shift['greyAt'])]
        shift = max(current or matches, key=lambda item: instant(item['startAt']))
        state = 'finished' if now >= instant(shift['greyAt']) else 'grace' if now >= instant(shift['endAt']) else 'active'
        employee['checksheet_shift'] = {key: shift[key] for key in ('line', 'shiftId', 'shift', 'overtime', 'startAt', 'endAt', 'greyAt', 'graceMinutes')}
        employee['checksheet_shift']['state'] = state
    return employees


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def sync_once(store, env=None, opener=None, now=None):
    env = os.environ if env is None else env
    now = now or datetime.now(timezone.utc)
    origin, token = env.get('CHECKSHEET_API_URL', '').strip(), env.get('CHECKSHEET_SHIFT_FEED_TOKEN', '').strip()
    if not origin and not token:
        with store.connect() as db:
            removed = db.execute('DELETE FROM checksheet_board_state').rowcount
        if removed:
            store.emit()
        return False
    try:
        parsed = urlsplit(origin)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment or len(token) < 32:
            raise ValueError('Invalid integration configuration')
        request = Request(origin.rstrip('/')+'/api/integrations/shifts', headers={'Authorization': 'Bearer '+token, 'Accept': 'application/json'})
        with (opener or build_opener(NoRedirect())).open(request, timeout=5) as response:
            raw = response.read(MAX_BYTES+1)
        if len(raw) > MAX_BYTES:
            raise ValueError('Oversized feed')
        payload = validate(json.loads(raw), now)
        with store.connect() as db:
            db.execute('INSERT INTO checksheet_board_state VALUES(1,?,?,0) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,received_at=excluded.received_at,error=0', (json.dumps(payload), now.isoformat()))
    except Exception:
        # Do not disclose origins, tokens or upstream response bodies through the UI/logs.
        with store.connect() as db:
            db.execute('INSERT INTO checksheet_board_state VALUES(1,NULL,NULL,1) ON CONFLICT(id) DO UPDATE SET error=1')
        store.emit()
        return False
    store.emit()
    return True


def start_worker(store):
    stop = threading.Event()
    def run():
        while not stop.is_set():
            sync_once(store)
            stop.wait(15)
    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    return stop, worker
