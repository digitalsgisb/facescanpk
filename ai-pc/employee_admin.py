"""Ordinary employee administration only; no biometric data or processing."""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

METADATA = ('id', 'name', 'nickname', 'department', 'position', 'line', 'team',
            'production_section', 'office_department', 'checksheet_group', 'company', 'base', 'employment_department', 'job_type', 'active')


def migrate(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS staff (
      username TEXT PRIMARY KEY, salt TEXT NOT NULL, password TEXT NOT NULL,
      role TEXT NOT NULL CHECK(role IN ('admin','employee_admin')), active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS staff_sessions (
      token_hash TEXT PRIMARY KEY, username TEXT NOT NULL REFERENCES staff(username), expires REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS employee_consents (
      id INTEGER PRIMARY KEY, employee_id TEXT NOT NULL REFERENCES employees(id),
      purpose TEXT NOT NULL, granted INTEGER NOT NULL, notice TEXT NOT NULL,
      evidence TEXT NOT NULL, actor TEXT NOT NULL, recorded_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS profile_photos (
      url TEXT PRIMARY KEY, actor TEXT NOT NULL, created_at TEXT NOT NULL, deleted_at TEXT);
    CREATE TABLE IF NOT EXISTS metadata_receipts (
      device_id TEXT PRIMARY KEY REFERENCES devices(id), version TEXT NOT NULL, acknowledged_at TEXT NOT NULL);
    ''')
    if 'base' not in {r['name'] for r in db.execute('PRAGMA table_info(staff)')}:
        db.execute("ALTER TABLE staff ADD COLUMN base TEXT NOT NULL DEFAULT ''")
    if 'base' not in {r['name'] for r in db.execute('PRAGMA table_info(devices)')}:
        db.execute("ALTER TABLE devices ADD COLUMN base TEXT NOT NULL DEFAULT ''")


def metadata(employees):
    return [{key: e.get(key, '') for key in METADATA} for e in sorted(employees, key=lambda e:e['id'])]


def version(employees):
    return hashlib.sha256(json.dumps(metadata(employees), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def decorate(db, employees):
    everyone=[dict(r) for r in db.execute('SELECT * FROM employees')]
    devices = list(db.execute("SELECT d.id,d.name,d.base,d.last_seen,r.version,r.acknowledged_at FROM devices d LEFT JOIN metadata_receipts r ON r.device_id=d.id WHERE d.scope='kiosk' AND d.active=1"))
    now = datetime.now(timezone.utc)
    statuses = []
    for d in devices:
        current=version([e for e in everyone if not d['base'] or e.get('base')==d['base']])
        online = bool(d['last_seen'] and (now-datetime.fromisoformat(d['last_seen'])).total_seconds()<90)
        statuses.append({'id':d['id'], 'name':d['name'],'base':d['base'], 'status': 'offline' if not online else 'synced' if d['version']==current else 'pending',
                         'acknowledged_at':d['acknowledged_at']})
    latest = {}
    for row in db.execute('SELECT * FROM employee_consents ORDER BY id'):
        latest.setdefault(row['employee_id'], {})[row['purpose']] = dict(row)
    for e in employees:
        e['consents'] = latest.get(e['id'], {})
        matching=[d for d in statuses if not d['base'] or d['base']==e.get('base')]
        e['metadata_sync'] = {'status': 'no_kiosk' if not matching else 'synced' if all(d['status']=='synced' for d in matching) else 'offline' if any(d['status']=='offline' for d in matching) else 'pending', 'devices':matching}
    return employees


def record_consent(store, db, eid, data, actor, Problem, now):
    if not isinstance(data, dict) or data.get('purpose') not in ('employee_data', 'profile_photo') or type(data.get('granted')) is not bool:
        raise Problem('Choose employee data or profile photo consent, and grant or withdraw it.')
    for field in ('notice', 'evidence'):
        if not isinstance(data.get(field), str) or not 3 <= len(data[field].strip()) <= 500:
            raise Problem('Provide the notice version and an evidence reference (3–500 characters).')
    if not db.execute('SELECT 1 FROM employees WHERE id=?', (eid,)).fetchone():
        raise Problem('Employee not found.', 404)
    db.execute('INSERT INTO employee_consents(employee_id,purpose,granted,notice,evidence,actor,recorded_at) VALUES(?,?,?,?,?,?,?)',
               (eid,data['purpose'],int(data['granted']),data['notice'].strip(),data['evidence'].strip(),actor,now))
    store.audit(db,actor,'consent_recorded',eid,None,data)


def cleanup_photos(store, db, days, actor, now):
    """Explicit cleanup: tracked, unreferenced uploads only. Never employee/history deletion."""
    cutoff = (datetime.fromisoformat(now)-timedelta(days=days)).isoformat()
    removed = 0
    for row in db.execute('SELECT url FROM profile_photos WHERE deleted_at IS NULL AND created_at<?', (cutoff,)).fetchall():
        url = row['url']
        if db.execute('SELECT 1 FROM employees WHERE photo_url=?', (url,)).fetchone():
            continue
        if re.fullmatch(r'/uploads/[a-f0-9]{32}\.jpg', url):
            db.execute('UPDATE profile_photos SET deleted_at=? WHERE url=?', (now,url))
            store.audit(db,actor,'photo_retention_deleted',url,None,{'retention_days':days})
            removed += 1
    return removed


def erase_deleted_photos(store, db):
    """Retry physical deletion after the database transaction is committed."""
    for row in db.execute('SELECT url FROM profile_photos WHERE deleted_at IS NOT NULL'):
        url = row['url']
        if re.fullmatch(r'/uploads/[a-f0-9]+\.jpg', url) and not db.execute('SELECT 1 FROM employees WHERE photo_url=?',(url,)).fetchone():
            try:
                (store.path.parent/'uploads'/url.split('/')[-1]).unlink(missing_ok=True)
            except OSError:
                # Access is already revoked; the next cleanup retries disk removal.
                pass
