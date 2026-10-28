"""Company-network attendance service. Run on the AI PC; no cloud dependency."""
import argparse
import attendance_maintenance
import employee_export
import employee_spreadsheet
import base64
import hashlib
import hmac
import io
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
import zipfile
import ssl
import employee_admin
import testing_operations
import plant_workflows
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone, date
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

BASE = Path(__file__).resolve().parent
KL = timezone(timedelta(hours=8), 'Asia/Kuala_Lumpur')
SESSION_COOKIE_AGE = 400 * 24 * 3600  # Browser persistence, renewed on authenticated requests.
FIELDS = ('id', 'name', 'nickname', 'department', 'position', 'line', 'team', 'photo_url', 'schedule_id', 'production_section', 'office_department', 'checksheet_group', 'company', 'base', 'employment_department', 'job_type', 'active')
TEMPLATES = [
    ('normal', 'Normal working hours', '07:45', '17:40', 0),
    ('day', 'Day shift', '08:00', '16:15', 0),
    ('day-ot', 'Day shift + OT', '08:00', '20:00', 1),
    ('night', 'Night shift', '16:15', '00:30', 0),
    ('night-ot', 'Night shift + OT', '20:00', '08:00', 1),
]
PENDING_REVIEW = plant_workflows.PENDING_REVIEW
ATTENTION_SESSION = plant_workflows.ATTENTION_SESSION


class Problem(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


def now_iso():
    return datetime.now(KL).isoformat(timespec='seconds')


def stamp(value):
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            raise ValueError('timezone required')
        return dt.astimezone(KL)
    except (ValueError, TypeError, AttributeError):
        raise Problem('Timestamp must be ISO 8601 with a timezone.')


def day(value):
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        raise Problem('Use a date in YYYY-MM-DD format.')


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600_000).hex()


def schedule_scopes(employee):
    e = dict(employee)
    department = (e.get('department') or '').strip().upper()
    scopes = []
    if department == 'PRODUCTION':
        line = (e.get('line') or '').strip()
        section = e.get('production_section') or ('ROLL MAKING' if line.upper() == 'ROLL MAKING' else 'CONVERSION')
        if line:
            scopes.append('line:'+line)
        scopes.append('section:'+section)
    if department:
        scopes.append('department:'+department)
    return scopes


def validate_scope(scope):
    if not isinstance(scope, str) or len(scope)>150 or not re.fullmatch(r'(section:(CONVERSION|ROLL MAKING)|(?:line|department):[^\r\n]+)', scope):
        raise Problem('Choose a department, production section or line.')


def validate_team_settings(db, config):
    if not isinstance(config, dict) or set(config)-{'team_schedules','team_overtime','rotation'}:
        raise Problem('Invalid team settings.')
    for key in ('team_schedules','team_overtime'):
        value=config.get(key,{})
        if not isinstance(value,dict) or any(team not in ('A','B','C','D','N') for team in value):
            raise Problem('Choose a valid team.')
        for choice in value.values():
            if key=='team_overtime':
                if not isinstance(choice,bool):
                    raise Problem('Overtime must be on or off for each team.')
            elif choice is not None and (not isinstance(choice,str) or not db.execute('SELECT 1 FROM schedules WHERE id=?',(choice,)).fetchone()):
                raise Problem('Choose an existing team schedule.')
    rotation=config.get('rotation')
    if rotation is not None:
        if not isinstance(rotation,dict):
            raise Problem('Invalid rotation.')
        day(rotation.get('anchor_date'))
        if 'teams' in rotation and rotation['teams'] not in (['A','B'],['C','D']):
            raise Problem('Choose A/B or C/D rotation.')
        if type(rotation.get('interval_days')) is not int or not 1<=rotation['interval_days']<=60:
            raise Problem('Rotation interval must be between 1 and 60 days.')
        ids=rotation.get('schedule_ids',[])
        if not isinstance(ids,list) or len(ids)!=2 or any(not isinstance(s,str) or not db.execute('SELECT 1 FROM schedules WHERE id=?',(s,)).fetchone() for s in ids):
            raise Problem('Choose two rotation schedules.')


class Store:
    def __init__(self, path, seed=True):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.changed = threading.Condition()
        self.revision = 0
        self.failures = {}
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS employees (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, nickname TEXT, department TEXT,
              position TEXT, line TEXT, team TEXT, photo_url TEXT, schedule_id TEXT,
              active INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS schedules (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, start TEXT NOT NULL,
              end TEXT NOT NULL, ot INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS assignments (
              id TEXT PRIMARY KEY, employee_id TEXT, team TEXT, start_date TEXT NOT NULL,
              end_date TEXT NOT NULL, schedule_id TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (
              id TEXT PRIMARY KEY, employee_id TEXT NOT NULL REFERENCES employees(id),
              work_date TEXT NOT NULL, time_in TEXT NOT NULL, time_out TEXT,
              schedule_id TEXT, schedule_name TEXT, planned_in TEXT, planned_out TEXT,
              flags TEXT NOT NULL, source TEXT NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS one_open_session ON sessions(employee_id) WHERE time_out IS NULL;
            CREATE TABLE IF NOT EXISTS events (
              id TEXT PRIMARY KEY, employee_id TEXT NOT NULL, device_id TEXT NOT NULL,
              occurred_at TEXT NOT NULL, received_at TEXT NOT NULL, request_hash TEXT NOT NULL,
              result TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS employee_events ON events(employee_id, occurred_at);
            CREATE TABLE IF NOT EXISTS employee_snapshots (
              session_id TEXT PRIMARY KEY REFERENCES sessions(id), name TEXT, nickname TEXT,
              department TEXT, line TEXT, team TEXT);
            CREATE TABLE IF NOT EXISTS devices (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
              scope TEXT NOT NULL, last_seen TEXT, health TEXT, active INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS audit (
              id INTEGER PRIMARY KEY AUTOINCREMENT, occurred_at TEXT NOT NULL, actor TEXT NOT NULL,
              action TEXT NOT NULL, entity_id TEXT NOT NULL, before_json TEXT, after_json TEXT);
            CREATE INDEX IF NOT EXISTS audit_entity_action ON audit(entity_id,action);
            CREATE INDEX IF NOT EXISTS review_events ON events(occurred_at,id) WHERE json_extract(result,'$.action')='REVIEW';
            CREATE TABLE IF NOT EXISTS admin (id INTEGER PRIMARY KEY CHECK(id=1), salt TEXT NOT NULL, password TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS auth_sessions (token_hash TEXT PRIMARY KEY, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS attendance_access (token_hash TEXT PRIMARY KEY, expires REAL NOT NULL);
            ''')
            employee_admin.migrate(db)
            testing_operations.migrate(db)
            plant_workflows.migrate(db)
            columns={r['name'] for r in db.execute('PRAGMA table_info(employees)')}
            for column in ('production_section','office_department','checksheet_group','company','base','employment_department','job_type'):
                if column not in columns:
                    db.execute(f"ALTER TABLE employees ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
            if 'scope' not in {r['name'] for r in db.execute('PRAGMA table_info(assignments)')}:
                db.execute("ALTER TABLE assignments ADD COLUMN scope TEXT NOT NULL DEFAULT ''")
            # Upgrade still-valid sessions; never revive a session that already expired.
            db.execute('UPDATE auth_sessions SET expires=0 WHERE expires>?', (time.time(),))
            for s in TEMPLATES:
                db.execute('INSERT OR IGNORE INTO schedules VALUES(?,?,?,?,?)', s)
            for key, value in {'cooldown_seconds':300, 'early_in_minutes':120, 'late_in_minutes':120,
                               'early_out_minutes':120, 'late_out_minutes':120,
                               'normal_auto_out_enabled':1, 'normal_auto_out_hour':3, 'max_open_hours':20, 'late_grace_minutes':15,
                               'early_departure_grace_minutes':15, 'rotation':None,
                               'team_schedules':{}, 'team_overtime':{}, 'schedule_groups':{},
                               'employee_sort':'position', 'employee_order':[]}.items():
                db.execute('INSERT OR IGNORE INTO settings VALUES(?,?)', (key, json.dumps(value)))
            if seed and not db.execute('SELECT 1 FROM employees LIMIT 1').fetchone():
                seed_path = BASE / 'data/employees.json'
                if not seed_path.exists():
                    seed_path = BASE / 'data/employees.example.json'
                source = json.loads(seed_path.read_text(encoding='utf-8'))
                for e in source['employees']:
                    # A/B and blank teams need roster configuration; do not guess current rotation.
                    if e['team'] != 'N':
                        e['schedule_id'] = None
                    self.insert_employee(db, e)
                self.audit(db, 'migration', 'import_employee_snapshot', 'workers', None,
                           {'count':len(source['employees']), 'source':source['source']})

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA synchronous=FULL')
            db.execute('PRAGMA foreign_keys=ON')
            with db:
                yield db
        finally:
            db.close()

    def emit(self):
        with self.changed:
            self.revision += 1
            self.changed.notify_all()

    def audit(self, db, actor, action, entity, before, after):
        db.execute('INSERT INTO audit(occurred_at,actor,action,entity_id,before_json,after_json) VALUES(?,?,?,?,?,?)',
                   (now_iso(), actor, action, entity, json.dumps(before) if before is not None else None,
                    json.dumps(after) if after is not None else None))

    def snapshot(self, db, sid, employee):
        db.execute('INSERT INTO employee_snapshots VALUES(?,?,?,?,?,?)',
                   (sid,employee['name'],employee['nickname'],employee['department'],employee['line'],employee['team']))

    def backup(self, destination):
        destination=Path(destination)
        destination.parent.mkdir(parents=True,exist_ok=True)
        temporary=destination.with_suffix('.sqlite3')
        try:
            with self.connect() as db:
                out=sqlite3.connect(temporary)
                try:
                    db.backup(out)
                finally:
                    out.close()
            with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as archive:
                archive.write(temporary,'attendance.sqlite3')
                for photo in (self.path.parent/'uploads').glob('*.jpg'):
                    archive.write(photo,'uploads/'+photo.name)
        finally:
            temporary.unlink(missing_ok=True)

    def insert_employee(self, db, e):
        values = [e.get(f, '') for f in FIELDS[:-1]] + [int(e.get('active', True)), now_iso()]
        db.execute('INSERT INTO employees ('+','.join(FIELDS)+',updated_at) VALUES('+','.join('?' for _ in values)+')', values)

    def settings(self, db):
        return {r['key']:json.loads(r['value']) for r in db.execute('SELECT * FROM settings')}

    def attention_summary(self, db, employees=None, plant=''):
        return plant_workflows.summary(self,db,plant,employees)

    def attention_page(self, db, category, offset, limit, plant=''):
        return plant_workflows.page(self,db,category,offset,limit,plant)

    def resolve_schedule(self, db, e, work_date):
        e=dict(e)
        scopes=schedule_scopes(e)
        rows=list(db.execute('SELECT * FROM assignments WHERE start_date<=? AND end_date>=? AND (employee_id=? OR ((employee_id IS NULL OR employee_id=\'\') AND team=?)) ORDER BY start_date DESC',
                             (str(work_date),str(work_date),e['id'],e['team'])))
        personal=next((row for row in rows if row['employee_id']==e['id']),None)
        team=next((row for scope in [*scopes,''] for row in rows if not row['employee_id'] and row['team']==e['team'] and row['scope']==scope),None)
        override=personal or team
        if override:
            return plant_workflows.schedule(db,override['schedule_id'],e.get('base',''))
        settings = plant_workflows.schedule_settings(db,e.get('base',''),self.settings(db))
        settings=next((settings['schedule_groups'][scope] for scope in scopes if scope in settings['schedule_groups']),settings)
        rotation = settings.get('rotation')
        def team_hours(schedule_id):
            base = schedule_id.removesuffix('-ot') if schedule_id else None
            overtime = settings.get('team_overtime',{})
            if base in ('day','night') and e['team'] in overtime:
                schedule_id = base+('-ot' if overtime[e['team']] else '')
            return plant_workflows.schedule(db,schedule_id,e.get('base',''))
        pair=rotation.get('teams',['A','B']) if rotation else ['A','B']
        if rotation and e['team'] in pair and work_date >= day(rotation['anchor_date']):
            index = ((work_date-day(rotation['anchor_date'])).days // rotation['interval_days']) % 2
            if e['team'] == pair[1]:
                index = 1-index
            return team_hours(rotation['schedule_ids'][index])
        team_schedule = settings.get('team_schedules',{}).get(e['team'])
        if team_schedule:
            return team_hours(team_schedule)
        return plant_workflows.schedule(db,e['schedule_id'],e.get('base',''))

    def planned(self, schedule, work_date):
        start = datetime.fromisoformat(f'{work_date}T{schedule["start"]}:00').replace(tzinfo=KL)
        end = datetime.fromisoformat(f'{work_date}T{schedule["end"]}:00').replace(tzinfo=KL)
        if end <= start:
            end += timedelta(days=1)
        return start, end

    def validate_employee(self, db, e):
        if not re.fullmatch(r'[A-Za-z0-9-]{1,40}', str(e.get('id', ''))):
            raise Problem('Employee ID must contain 1–40 letters, numbers or hyphens.')
        if not str(e.get('name', '')).strip():
            raise Problem('Full name is required.')
        if e.get('team', '') not in ('', 'A', 'B', 'C', 'D', 'N'):
            raise Problem('Select a team or leave it unassigned.')
        if e.get('production_section','') not in ('','CONVERSION','ROLL MAKING'):
            raise Problem('Choose Conversion, Roll Making or automatic section.')
        if e.get('checksheet_group','') not in ('','fc1','fc2','fc3'):
            raise Problem('Choose FC Line 1, FC Line 2, FC Line 3 or unassigned.')
        if e.get('checksheet_group') and ((e.get('department') or '').strip().upper() != 'PRODUCTION' or (e.get('line') or '').strip().upper() != 'FC'):
            raise Problem('FC Checksheet assignments require Production department and FC line.')
        for f in FIELDS[:-1]:
            if e.get(f) is not None and (not isinstance(e[f], str) or len(e[f]) > 2000):
                raise Problem('Employee field is invalid or too long.')
        if e.get('active', True) not in (True, False, 0, 1):
            raise Problem('Active must be true or false.')
        if e.get('base') and not re.fullmatch(r'[A-Z0-9][A-Z0-9 &_.-]{0,79}',e['base']):
            raise Problem('Use an uppercase plant location of 1–80 characters.')
        if e.get('schedule_id') and not db.execute('SELECT 1 FROM schedules WHERE id=?', (e['schedule_id'],)).fetchone():
            raise Problem('Schedule does not exist.')
        photo = e.get('photo_url', '')
        if photo and not (photo.startswith('https://') or re.fullmatch(r'/uploads/[a-f0-9]+\.jpg', photo)):
            raise Problem('Photo must be an HTTPS URL or an app upload.')
        if photo and db.execute('SELECT 1 FROM profile_photos WHERE url=? AND deleted_at IS NOT NULL',(photo,)).fetchone():
            raise Problem('This profile photo was deleted. Choose a new photo.')

    def employees(self, db):
        today = datetime.now(KL).date()
        opened = {r['employee_id']:dict(r) for r in db.execute('SELECT * FROM sessions WHERE time_out IS NULL')}
        result = []
        for row in db.execute('SELECT * FROM employees ORDER BY active DESC, nickname, name'):
            e = dict(row)
            schedule = self.resolve_schedule(db, e, today)
            e['effective_schedule'] = dict(schedule) if schedule else None
            e['session'] = opened.get(e['id'])
            e['status'] = 'IN' if e['session'] else 'OUT'
            e['stale_session'] = bool(e['session'] and (datetime.now(KL)-stamp(e['session']['time_in'])).total_seconds()>self.settings(db)['max_open_hours']*3600)
            result.append(e)
        return attendance_maintenance.decorate_enrollment(db, result)

    def scan(self, data, device, dashboard=False, skip_unchanged=False):
        event_id = data.get('event_id', '')
        if not re.fullmatch(r'[A-Za-z0-9-]{8,80}', event_id):
            raise Problem('A stable event_id is required for safe retries.')
        occurred = stamp(data.get('timestamp'))
        if occurred > datetime.now(KL)+timedelta(minutes=5):
            raise Problem('Kiosk clock is ahead. Correct its clock before retrying.', 422)
        eid = str(data.get('employee_id', ''))
        details = {'employee_id':eid,'timestamp':occurred.isoformat(),'device_id':device}
        if dashboard:
            if data.get('action') not in ('IN', 'OUT'):
                raise Problem('Choose clock in or clock out.')
            details['dashboard_action'] = data['action']
        fingerprint = digest(json.dumps(details, sort_keys=True))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone()
            if old:
                if old['request_hash'] != fingerprint:
                    raise Problem('event_id was already used with different scan details.', 409)
                return json.loads(old['result'])
            e = db.execute('SELECT * FROM employees WHERE id=?', (eid,)).fetchone()
            if not e or not e['active']:
                raise Problem('Employee is unknown or archived.', 422)
            opened = db.execute('SELECT * FROM sessions WHERE employee_id=? AND time_out IS NULL', (eid,)).fetchone()
            cfg = self.settings(db)
            latest = db.execute("SELECT * FROM events WHERE employee_id=? AND json_extract(result,'$.action') IN ('IN','OUT','DUPLICATE') ORDER BY occurred_at DESC LIMIT 1", (eid,)).fetchone()
            # Review flags do not lock current attendance. Release only a stale
            # session on an in-order new scan; an explicit OUT still records departure.
            stale = bool(opened and (occurred-stamp(opened['time_in'])).total_seconds()>cfg['max_open_hours']*3600)
            in_order = not latest or occurred >= stamp(latest['occurred_at'])
            outside_cooldown = dashboard or not latest or (occurred-stamp(latest['occurred_at'])).total_seconds() >= cfg['cooldown_seconds']
            if stale and in_order and outside_cooldown and (not dashboard or data['action']=='IN'):
                attendance_maintenance.release_stale_session(self,db,opened,occurred,cfg)
                opened = None
            if dashboard and data['action'] != ('OUT' if opened else 'IN'):
                if skip_unchanged:
                    result = {'event_id':event_id,'employee_id':eid,'accepted':True,'action':'UNCHANGED',
                              'timestamp':occurred.isoformat(),'source':'dashboard','flags':[],
                              'message':'Already clocked '+('in' if opened else 'out')+'; no change.'}
                    db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?)',
                               (event_id,eid,device,occurred.isoformat(),now_iso(),fingerprint,json.dumps(result)))
                    self.audit(db,'admin','clock_unchanged',eid,None,result)
                    return result
                raise Problem('Attendance already changed. Refresh and check the current status.', 409)
            flags = []
            if (latest and occurred < stamp(latest['occurred_at'])) or (opened and occurred < stamp(opened['time_in'])):
                result = {'event_id':event_id,'employee_id':eid,'accepted':True,'action':'REVIEW',
                          'flags':['out_of_order_scan'], 'message':'Scan stored for review; current attendance was not changed.'}
            elif not dashboard and latest and (occurred-stamp(latest['occurred_at'])).total_seconds() < cfg['cooldown_seconds']:
                result = {'event_id':event_id,'employee_id':eid,'accepted':True,'action':'DUPLICATE',
                          'flags':[], 'message':'Already recorded recently; attendance unchanged.'}
            else:
                if opened:
                    if stale:
                        flags.append('stale_open_session')
                    if opened['planned_out']:
                        diff = (occurred-stamp(opened['planned_out'])).total_seconds()/60
                        if diff < -cfg['early_out_minutes'] or diff > cfg['late_out_minutes']:
                            flags.append('outside_scheduled_hours')
                        if diff < -cfg['early_departure_grace_minutes']:
                            flags.append('early_departure')
                    else:
                        flags.append('schedule_unassigned')
                    all_flags = list(dict.fromkeys(json.loads(opened['flags'])+flags))
                    db.execute('UPDATE sessions SET time_out=?,flags=? WHERE id=?', (occurred.isoformat(), json.dumps(all_flags), opened['id']))
                    result = {'event_id':event_id,'employee_id':eid,'accepted':True,'action':'OUT','session_id':opened['id'],
                              'work_date':opened['work_date'],'flags':flags,'message':'Clock-out saved.'}
                else:
                    candidates = []
                    for offset in (-1, 0, 1):
                        wd = occurred.date()+timedelta(days=offset)
                        s = self.resolve_schedule(db, e, wd)
                        if s:
                            start, end = self.planned(s, wd)
                            # Prefer the shift interval containing the scan, then the nearest start.
                            score = abs((occurred-start).total_seconds())
                            if start-timedelta(minutes=cfg['early_in_minutes']) <= occurred <= end:
                                score -= 86400
                            candidates.append((score, wd, s, start, end))
                    if candidates:
                        _, wd, s, start, end = min(candidates, key=lambda c:c[0])
                        diff = (occurred-start).total_seconds()/60
                        if diff < -cfg['early_in_minutes'] or diff > cfg['late_in_minutes']:
                            flags.append('outside_scheduled_hours')
                        if diff > cfg['late_grace_minutes']:
                            flags.append('late_arrival')
                    else:
                        wd, s, start, end = occurred.date(), None, None, None
                        flags.append('schedule_unassigned')
                    sid = str(uuid.uuid4())
                    db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                               (sid,eid,str(wd),occurred.isoformat(),None,s['id'] if s else None,
                                s['name'] if s else None,start.isoformat() if start else None,end.isoformat() if end else None,
                                json.dumps(flags),device))
                    self.snapshot(db,sid,e)
                    result = {'event_id':event_id,'employee_id':eid,'accepted':True,'action':'IN',
                              'session_id':sid,'work_date':str(wd),'flags':flags,'message':'Clock-in saved.'}
            result['timestamp'] = occurred.isoformat()
            if dashboard:
                result['source'] = 'dashboard'
                result['reason'] = 'Administrator clicked Clock in' if data['action'] == 'IN' else 'Administrator clicked Clock out'
            db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?)',
                       (event_id,eid,device,occurred.isoformat(),now_iso(),fingerprint,json.dumps(result)))
            self.audit(db, device, 'scan_'+result['action'].lower(), eid, None, result)
        self.emit()
        return result


class Handler(BaseHTTPRequestHandler):
    server_version = 'SugiharaAttendance/1.0'

    @property
    def store(self):
        return self.server.store

    def log_message(self, fmt, *args):
        # Deliberately exclude paths, tokens, passwords and personnel data from logs.
        pass

    def send(self, data, status=200, headers=None, content_type='application/json'):
        headers = dict(headers or {})
        if getattr(self, 'session_token', None) and 'Set-Cookie' not in headers:
            headers['Set-Cookie'] = self.session_cookie(self.session_token)
        raw = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store' if self.path.startswith(('/api','/uploads/')) else 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'same-origin')
        for k,v in (headers or {}).items():
            self.send_header(k,v)
        self.end_headers()
        self.wfile.write(raw)

    def session_cookie(self, token):
        secure = '; Secure' if self.server.is_tls else ''
        return f'attendance_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_COOKIE_AGE}{secure}'

    def body(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 0:
                raise Problem('Invalid request length.')
            if length > 7_000_000:
                raise Problem('Upload too large.', 413)
            data = json.loads(self.rfile.read(length) or b'{}')
            if not isinstance(data, dict):
                raise Problem('Request must be a JSON object.')
            return data
        except (ValueError, json.JSONDecodeError):
            raise Problem('Invalid JSON request.')

    def identity(self, db, allow_device=False):
        auth = self.headers.get('Authorization', '')
        if allow_device and auth.startswith('Bearer '):
            device = db.execute('SELECT * FROM devices WHERE token_hash=? AND active=1', (digest(auth[7:]),)).fetchone()
            if device:
                return dict(device)
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            token = cookie['attendance_session'].value
        except Exception:
            token = ''
        if token and db.execute('SELECT 1 FROM auth_sessions WHERE token_hash=? AND (expires=0 OR expires>?)', (digest(token),time.time())).fetchone():
            self.session_token = token
            return {'id':'admin','scope':'admin'}
        staff = db.execute('SELECT s.username,s.role,s.base FROM staff_sessions t JOIN staff s ON s.username=t.username WHERE t.token_hash=? AND t.expires>? AND s.active=1', (digest(token),time.time())).fetchone() if token else None
        if staff:
            self.session_token = token
            return {'id':staff['username'], 'scope':staff['role'],'base':staff['base']}
        raise Problem('Please sign in.', 401)

    def guard_origin(self):
        origin = self.headers.get('Origin')
        if origin:
            parsed = urlparse(origin)
            host = self.headers.get('Host', '')
            # Compare the browser-facing authority, including a published Docker
            # port, rather than the internal server socket's port.
            if parsed.scheme not in ('http','https') or parsed.netloc.lower() != host.lower() or parsed.username or parsed.password:
                raise Problem('Request origin is not allowed.', 403)

    def do_GET(self):
        self.handle_request('GET')

    def do_POST(self):
        self.handle_request('POST')

    def do_PUT(self):
        self.handle_request('PUT')

    def do_DELETE(self):
        self.handle_request('DELETE')

    def handle_request(self, method):
        self.session_token = None
        try:
            url = urlparse(self.path)
            route = unquote(url.path)
            query = parse_qs(url.query)
            if method != 'GET':
                self.guard_origin()
            if route.startswith('/api/auth/'):
                return self.auth(route, method)
            if route == '/api/health' and method == 'GET':
                return self.send({'ok':True,'time':now_iso()})
            if not route.startswith('/api/'):
                return self.static(route)
            with self.store.connect() as db:
                who = self.identity(db, allow_device=True)
                scope = who['scope']
                self.actor = who['id']
                self.plant = who.get('base','')
                if self.plant and scope == 'admin':
                    allowed=(method=='GET' and route in ('/api/employee-template','/api/state','/api/events','/api/employees','/api/schedules','/api/attendance','/api/review','/api/clock-access','/api/attention','/api/plant-controls')) or (method in ('POST','DELETE') and route in ('/api/employee-export','/api/clock','/api/clock/batch','/api/clock/reset','/api/clock-access','/api/photos','/api/manual-attendance','/api/employee-import/preview','/api/employee-import/spreadsheet','/api/employee-import/apply','/api/reviews/preview','/api/reviews/bulk')) or bool(re.fullmatch(r'/api/employees(?:/[A-Za-z0-9-]+(?:/consents|/photo)?)?',route)) or (method in ('PUT','POST') and bool(re.fullmatch(r'/api/(?:attendance|review)/[A-Za-z0-9-]+',route)))
                    if route=='/api/plant-controls' and method=='PUT':allowed=True
                    if route=='/api/board-layout' and method in ('GET','PUT'):allowed=True
                    if not allowed:
                        raise Problem('This account manages its assigned plant only.',403)
                if self.plant and route.startswith('/api/employees/'):
                    eid=route.split('/')[3]
                    self.check_plant(db,eid)
                if scope == 'employee_admin':
                    allowed = (method == 'GET' and route in ('/api/state','/api/events','/api/employees','/api/schedules')) or (route in ('/api/photos','/api/employee-export') and method == 'POST') or (re.fullmatch(r'/api/employees(?:/[A-Za-z0-9-]+(?:/consents|/photo)?)?', route) and method in ('GET','POST','PUT','DELETE'))
                    if not allowed:
                        raise Problem('Employee administrator permission is required for this operation.',403)
                if scope == 'kiosk' and route not in ('/api/scans','/api/heartbeat','/api/employees','/api/schedules'):
                    raise Problem('Kiosk access is limited to scanning and employee lookup.', 403)
                if scope == 'integration' and (method != 'GET' or route not in ('/api/employees','/api/attendance')):
                    raise Problem('Integration token is read-only.', 403)
                if route == '/api/events' and method == 'GET':
                    return self.events()
                if route == '/api/state' and method == 'GET':
                    return self.send(self.state(db))
                if route == '/api/employees' and method == 'GET':
                    employees = self.store.employees(db)
                    if self.plant:
                        employees=[e for e in employees if e.get('base')==self.plant]
                    if scope == 'kiosk':
                        employees = [{**row,'status':e['status'],'effective_schedule':e['effective_schedule']}
                                     for row,e in zip(employee_admin.metadata(employees),sorted(employees,key=lambda e:e['id']))]
                    elif scope in ('admin','employee_admin'):
                        employee_admin.decorate(db, employees)
                    return self.send({'employees':employees,'cooldown_seconds':self.store.settings(db)['cooldown_seconds'],
                                      'metadata_version':employee_admin.version(employees),
                                      'connection_scope':scope})
                if route == '/api/schedules' and method == 'GET':
                    return self.send({'schedules':[plant_workflows.schedule(db,r['id'],self.plant) for r in db.execute('SELECT id FROM schedules')]})
                if route == '/api/scans' and method == 'POST':
                    if scope != 'kiosk':
                        raise Problem('Use a registered kiosk to submit scans.', 403)
                    data=self.body()
                    self.check_plant(db,data.get('employee_id'))
                    result = self.store.scan(data, who['id'])
                    return self.send(result)
                if route == '/api/heartbeat' and method == 'POST':
                    if scope != 'kiosk':
                        raise Problem('Kiosk token required.',403)
                    data = self.body()
                    attendance_maintenance.validate_enrollment(data, Problem)
                    metadata_version = data.get('metadata_version')
                    if metadata_version is not None:
                        if not isinstance(metadata_version,str) or not re.fullmatch(r'[a-f0-9]{64}',metadata_version):
                            raise Problem('Invalid metadata acknowledgement.')
                        db.execute('INSERT OR REPLACE INTO metadata_receipts VALUES(?,?,?)',(who['id'],metadata_version,now_iso()))
                    db.execute('UPDATE devices SET last_seen=?,health=? WHERE id=?', (now_iso(), json.dumps(data), who['id']))
                    db.commit()
                    self.store.emit()
                    return self.send({'ok':True})
                if route == '/api/employee-template' and method == 'GET':
                    if scope != 'admin':
                        raise Problem('Administrator access required.',403)
                    return self.send(employee_spreadsheet.template(db,self.plant),content_type=employee_export.MIME,
                                     headers={'Content-Disposition':'attachment; filename="employee-import-template.xlsx"'})
                if route == '/api/employee-export' and method == 'POST':
                    if scope not in ('admin','employee_admin'):
                        raise Problem('Employee management permission is required to export shifts.',403)
                    data = self.body()
                    start, end = day(data.get('from')), day(data.get('to'))
                    if end < start or (end-start).days > 366:
                        raise Problem('Choose a date range of up to one year.')
                    ids = data.get('employee_ids')
                    if not isinstance(ids,list) or any(not isinstance(eid,str) for eid in ids):
                        raise Problem('Choose the employees to export.')
                    ids = set(ids)
                    employees = [dict(e) for e in db.execute('SELECT * FROM employees')
                                 if e['id'] in ids and (not self.plant or e['base'] == self.plant)]
                    if len(employees) != len(ids):
                        raise Problem('Some selected employees are unavailable for this account.',403)
                    if len(employees) * ((end-start).days+1) > 1048575:
                        raise Problem('Too many rows for Excel. Choose fewer employees or dates.')
                    raw = employee_export.workbook(employee_export.roster_rows(self.store,db,employees,start,end))
                    filename = f'employee_shifts_{start}_to_{end}.xlsx'
                    return self.send(raw, content_type=employee_export.MIME,
                                     headers={'Content-Disposition':f'attachment; filename="{filename}"'})
                if route == '/api/attendance' and method == 'GET':
                    return self.send({'sessions':self.sessions(db, query)})
                if scope not in ('admin','employee_admin'):
                    raise Problem('Administrator access required.',403)
                if route == '/api/attention' and method == 'GET':
                    category=query.get('category',['hours'])[0]
                    if category not in ('hours','attendance','scans'):
                        raise Problem('Choose a valid issue category.')
                    try:
                        offset=int(query.get('offset',['0'])[0])
                        limit=int(query.get('limit',['50'])[0])
                    except (ValueError,TypeError):
                        raise Problem('Invalid issue page.')
                    if offset<0 or not 1<=limit<=100:
                        raise Problem('Invalid issue page.')
                    base=plant_workflows.scope(self.plant,query.get('base',[None])[0],Problem)
                    return self.send(self.store.attention_page(db,category,offset,limit,base))
                if route == '/api/board-layout' and method in ('GET','PUT'):
                    if scope!='admin':raise Problem('Administrator access required.',403)
                    data=self.body() if method=='PUT' else {}
                    base=plant_workflows.scope(self.plant,data.get('base') if method=='PUT' else query.get('base',[None])[0],Problem)
                    if method=='GET':return self.send(plant_workflows.board_layout(db,base))
                    db.execute('BEGIN IMMEDIATE')
                    result=plant_workflows.save_board_layout(self.store,db,base,data,self.actor,Problem)
                    db.commit();self.store.emit()
                    return self.send(result)
                if route == '/api/plant-controls' and method in ('GET','PUT'):
                    if scope!='admin':raise Problem('Administrator access required.',403)
                    data=self.body() if method=='PUT' else {}
                    base=plant_workflows.scope(self.plant,data.get('base') if method=='PUT' else query.get('base',[None])[0],Problem)
                    if method=='GET':return self.send(plant_workflows.controls(self.store,db,base))
                    db.execute('BEGIN IMMEDIATE')
                    result=plant_workflows.save_controls(self.store,db,base,{k:v for k,v in data.items() if k!='base'},self.actor,validate_team_settings,validate_scope,Problem,now_iso())
                    db.commit();self.store.emit()
                    return self.send(result)
                if route in ('/api/reviews/preview','/api/reviews/bulk') and method=='POST':
                    if scope!='admin':raise Problem('Administrator access required.',403)
                    data=self.body();db.execute('BEGIN IMMEDIATE')
                    if route.endswith('/preview'):result,_=plant_workflows.review_preview(self.store,db,data,self.plant,Problem)
                    else:result=plant_workflows.review_apply(self.store,db,data,self.actor,self.plant,Problem,now_iso())
                    db.commit()
                    if route.endswith('/bulk'):self.store.emit()
                    return self.send(result)
                if route=='/api/automatic-clockout' and method in ('GET','PUT'):
                    if scope!='admin' or self.plant:raise Problem('All-plants administrator access required.',403)
                    if method=='GET':return self.send(plant_workflows.clockout_config(db))
                    data=self.body();db.execute('BEGIN IMMEDIATE')
                    result=plant_workflows.save_clockout(self.store,db,data,self.actor,Problem,datetime.now(KL).isoformat())
                    db.commit();self.store.emit()
                    return self.send(result)
                if route == '/api/clock-access' and method == 'GET':
                    access = db.execute('SELECT expires FROM attendance_access WHERE token_hash=? AND expires>?',
                                        (digest(self.session_token), time.time())).fetchone()
                    return self.send({'unlocked':bool(access),'expires_at':access['expires'] if access else None})
                if route == '/api/clock-access' and method == 'DELETE':
                    db.execute('DELETE FROM attendance_access WHERE token_hash=?',(digest(self.session_token),))
                    db.commit()
                    return self.send({'ok':True})
                if route in ('/api/clock','/api/clock/batch','/api/clock/reset') and method == 'POST':
                    if not db.execute('SELECT 1 FROM attendance_access WHERE token_hash=? AND expires>?',
                                      (digest(self.session_token),time.time())).fetchone():
                        raise Problem('Enter the administrator password to unlock attendance controls.',403)
                if route in ('/api/clock/reset','/api/employee-import/preview','/api/employee-import/spreadsheet','/api/employee-import/apply') and method == 'POST':
                    if scope != 'admin':
                        raise Problem('Administrator access required.',403)
                    data=self.body()
                    db.execute('BEGIN IMMEDIATE')
                    if route.endswith('/spreadsheet'):
                        data={'payload':employee_spreadsheet.parse(data.get('file_base64'),Problem)}
                    if route.endswith(('/preview','/spreadsheet')):
                        response,_=testing_operations.preview(self.store,db,data.get('payload'),FIELDS,Problem,self.plant)
                    else:
                        response=testing_operations.operation(self.store,db,'reset' if route.endswith('/reset') else 'employee-import',data,self.actor,FIELDS,Problem,datetime.now(KL).isoformat(),self.plant)
                    if route.endswith('/spreadsheet'):
                        response['payload']=data['payload']
                    db.commit()
                    if not route.endswith(('/preview','/spreadsheet')):
                        self.store.emit()
                    return self.send(response)
                if route == '/api/clock/batch' and method == 'POST':
                    data = self.body()
                    ids, action, batch_id = data.get('employee_ids'), data.get('action'), data.get('batch_id','')
                    if action not in ('IN','OUT') or not isinstance(ids,list) or not 1 <= len(ids) <= 200:
                        raise Problem('Choose clock in or out and between 1 and 200 employees.')
                    if not all(isinstance(eid,str) and eid for eid in ids) or len(set(ids)) != len(ids):
                        raise Problem('Employee IDs must be unique non-empty strings.')
                    for eid in ids:
                        self.check_plant(db,eid)
                    if not isinstance(batch_id,str) or not re.fullmatch(r'[A-Za-z0-9-]{8,80}', batch_id):
                        raise Problem('A stable batch_id is required for safe retries.')
                    results = []
                    for eid in ids:
                        event_id = str(uuid.uuid5(uuid.NAMESPACE_URL,f'attendance:{batch_id}:{eid}'))
                        previous = db.execute('SELECT occurred_at FROM events WHERE id=?',(event_id,)).fetchone()
                        try:
                            result = self.store.scan({'event_id':event_id,'employee_id':eid,'action':action,
                                'timestamp':previous['occurred_at'] if previous else now_iso()},'admin',dashboard=True,skip_unchanged=True)
                            results.append({**result,'status':'saved' if result['action']==action else 'skipped' if result['action']=='UNCHANGED' else 'review'})
                        except Problem as exc:
                            results.append({'employee_id':eid,'status':'error','message':exc.message})
                    return self.send({'results':results})
                if route == '/api/clock' and method == 'POST':
                    data = self.body()
                    self.check_plant(db,data.get('employee_id'))
                    # Server time is authoritative. Reuse the committed time for an idempotent retry.
                    previous = db.execute('SELECT occurred_at FROM events WHERE id=?', (data.get('event_id', ''),)).fetchone()
                    data['timestamp'] = previous['occurred_at'] if previous else now_iso()
                    return self.send(self.store.scan(data, 'admin', dashboard=True))
                if route == '/api/audit' and method == 'GET':
                    return self.send({'audit':[dict(r) for r in db.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 200')]})
                if route == '/api/review' and method == 'GET':
                    return self.send({'events':[dict(r) for r in db.execute('''SELECT v.*,e.name,e.nickname,e.base FROM events v
                        JOIN employees e ON e.id=v.employee_id WHERE json_extract(v.result,'$.action')='REVIEW'
                        AND NOT EXISTS(SELECT 1 FROM audit a WHERE a.entity_id=v.id AND a.action='scan_reviewed')
                        AND (?='' OR e.base=?) ORDER BY v.occurred_at DESC LIMIT 1000''',(self.plant,self.plant)) if plant_workflows.review_enabled(db,self.plant) and plant_workflows.review_enabled(db,r['base'])]})
                if route == '/api/backup' and method == 'GET':
                    backup = self.store.path.parent / ('backup-'+str(uuid.uuid4())+'.sqlite3')
                    try:
                        out = sqlite3.connect(backup)
                        try:
                            db.backup(out)
                        finally:
                            out.close()
                        return self.send(backup.read_bytes(), content_type='application/octet-stream',
                                         headers={'Content-Disposition':'attachment; filename="attendance-backup.sqlite3"'})
                    finally:
                        backup.unlink(missing_ok=True)
                if route == '/api/photos' and method == 'POST':
                    return self.photo(self.body(), db)
                if route == '/api/staff' and method == 'GET':
                    return self.send({'staff':[dict(r) for r in db.execute('SELECT username,role,active,base FROM staff')]})
                if route == '/api/retention' and method == 'POST':
                    days = self.body().get('unreferenced_photo_days',30)
                    if type(days) is not int or not 1 <= days <= 3650:
                        raise Problem('Photo retention must be between 1 and 3650 days.')
                    db.execute('BEGIN IMMEDIATE')
                    count = employee_admin.cleanup_photos(self.store,db,days,self.actor,now_iso())
                    db.commit()
                    employee_admin.erase_deleted_photos(self.store,db)
                    return self.send({'deleted_photos':count})
                data = self.body() if method in ('POST','PUT') else {}
                db.execute('BEGIN IMMEDIATE')
                response = self.mutate(db, route, method, data)
                db.commit()
                employee_admin.erase_deleted_photos(self.store,db)
            self.store.emit()
            self.send(response)
        except Problem as exc:
            self.send({'error':exc.message}, exc.status)
        except sqlite3.IntegrityError:
            self.send({'error':'That ID already exists or conflicts with an existing record.'},409)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except Exception as exc:
            print('[ERROR]', type(exc).__name__, str(exc))
            self.send({'error':'The operation failed. Your existing records were preserved.'},500)

    def auth(self, route, method):
        with self.store.connect() as db:
            admin = db.execute('SELECT * FROM admin').fetchone()
            if route == '/api/auth/status' and method == 'GET':
                signed = False
                role = None
                base = ''
                try:
                    who=self.identity(db)
                    role = who['scope']
                    base = who.get('base','')
                    signed = True
                except Problem:
                    pass
                return self.send({'setup_required':not bool(admin),'signed_in':signed,'role':role,'base':base})
            if route == '/api/auth/logout' and method == 'POST':
                cookie = SimpleCookie(self.headers.get('Cookie',''))
                if 'attendance_session' in cookie:
                    db.execute('DELETE FROM auth_sessions WHERE token_hash=?',(digest(cookie['attendance_session'].value),))
                    db.execute('DELETE FROM staff_sessions WHERE token_hash=?',(digest(cookie['attendance_session'].value),))
                    db.execute('DELETE FROM attendance_access WHERE token_hash=?',(digest(cookie['attendance_session'].value),))
                db.commit()
                return self.send({'ok':True},headers={'Set-Cookie':'attendance_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
            if route not in ('/api/auth/setup','/api/auth/login','/api/auth/unlock-attendance') or method != 'POST':
                raise Problem('Endpoint not found.',404)
            if route == '/api/auth/unlock-attendance':
                unlock_who=self.identity(db)
                if unlock_who['scope'] != 'admin':
                    raise Problem('Administrator access required.',403)
            credentials = self.body()
            username = credentials.get('username','')
            if not isinstance(username,str) or len(username)>80:
                raise Problem('Invalid username.')
            password = credentials.get('password','')
            if not isinstance(password,str) or len(password)>256:
                raise Problem('Invalid password.')
            key = self.client_address[0]
            failures, until = self.store.failures.get(key,(0,0))
            if until>time.time():
                raise Problem('Too many attempts. Try again in 5 minutes.',429)
            db.execute('BEGIN IMMEDIATE')
            admin = db.execute('SELECT * FROM admin').fetchone()
            if route == '/api/auth/unlock-attendance' and unlock_who['id']!='admin':
                admin=db.execute('SELECT * FROM staff WHERE username=? AND active=1',(unlock_who['id'],)).fetchone()
            if username and route == '/api/auth/login':
                staff = db.execute('SELECT * FROM staff WHERE username=? AND active=1',(username,)).fetchone()
                # Perform the same password work for unknown usernames.
                salt = staff['salt'] if staff else '0'*32
                checked = password_hash(password,salt)
                if not staff or not hmac.compare_digest(checked,staff['password']):
                    failures += 1
                    self.store.failures[key]=(failures,time.time()+300 if failures>=5 else 0)
                    raise Problem('Incorrect username or password.',401)
                self.store.failures.pop(key,None)
                token = secrets.token_urlsafe(32)
                db.execute('DELETE FROM staff_sessions WHERE expires<?',(time.time(),))
                db.execute('INSERT INTO staff_sessions VALUES(?,?,?)',(digest(token),username,time.time()+8*3600))
                self.store.audit(db,username,'staff_login',username,None,{'role':staff['role']})
                db.commit()
                return self.send({'ok':True,'role':staff['role']},headers={'Set-Cookie':self.session_cookie(token)})
            if route.endswith('setup'):
                # The initial administrator can only be created from the PC itself.
                if key not in ('127.0.0.1','::1'):
                    raise Problem('Create the first administrator from the AI PC.',403)
                if admin:
                    raise Problem('Administrator is already configured.',409)
                if len(password)<12:
                    raise Problem('Use at least 12 characters for the administrator password.')
                salt = secrets.token_hex(16)
                db.execute('INSERT INTO admin VALUES(1,?,?)',(salt,password_hash(password,salt)))
            elif not admin or not hmac.compare_digest(password_hash(password,admin['salt']),admin['password']):
                failures+=1
                self.store.failures[key]=(failures,time.time()+300 if failures>=5 else 0)
                raise Problem('Incorrect password.',401)
            self.store.failures.pop(key,None)
            if route == '/api/auth/unlock-attendance':
                expires = time.time()+30*60
                db.execute('INSERT OR REPLACE INTO attendance_access VALUES(?,?)',(digest(self.session_token),expires))
                db.commit()
                return self.send({'ok':True,'expires_at':expires})
            token = secrets.token_urlsafe(32)
            db.execute('DELETE FROM auth_sessions WHERE expires>0 AND expires<?',(time.time(),))
            db.execute('INSERT INTO auth_sessions VALUES(?,?)',(digest(token),0))
            db.commit()
            return self.send({'ok':True},headers={'Set-Cookie':self.session_cookie(token)})

    def check_plant(self,db,eid):
        plant=getattr(self,'plant','')
        if plant and not db.execute('SELECT 1 FROM employees WHERE id=? AND base=?',(eid,plant)).fetchone():
            raise Problem('Employee not found in your plant.',404)

    def sessions(self, db, query):
        start = query.get('from', [str(datetime.now(KL).date()-timedelta(days=7))])[0]
        end = query.get('to', [str(datetime.now(KL).date())])[0]
        if day(end)<day(start) or (day(end)-day(start)).days>366:
            raise Problem('Choose a date range of up to one year.')
        return [dict(r) for r in db.execute('''SELECT s.*,COALESCE(p.name,e.name) AS name,
                COALESCE(p.nickname,e.nickname) AS nickname,COALESCE(p.department,e.department) AS department,
                COALESCE(p.line,e.line) AS line,COALESCE(p.team,e.team) AS team
                FROM sessions s JOIN employees e ON e.id=s.employee_id
                LEFT JOIN employee_snapshots p ON p.session_id=s.id
                WHERE s.work_date BETWEEN ? AND ? AND (?='' OR e.base=?) ORDER BY s.time_in DESC''', (start,end,getattr(self,'plant',''),getattr(self,'plant','')))]

    def state(self, db):
        employees=employee_admin.decorate(db,self.store.employees(db))
        plant=getattr(self,'plant','')
        if plant:
            employees=[e for e in employees if e.get('base')==plant]
        settings=plant_workflows.schedule_settings(db,plant,self.store.settings(db))
        if plant:
            ids={e['id'] for e in employees}
            settings['employee_order']=[eid for eid in settings.get('employee_order',[]) if eid in ids]
        if getattr(self,'actor','admin') != 'admin':
            who = self.identity(db)
            if who['scope'] == 'employee_admin':
                for e in employees:
                    e.pop('session',None)
                return {'employees':employees,'plant':plant,'schedules':[plant_workflows.schedule(db,r['id'],plant) for r in db.execute('SELECT id FROM schedules')],
                        'assignments':[],'settings':settings,'devices':[],
                        'recent_events':[],'revision':self.store.revision,'time':now_iso()}
        return {'employees':employees,'plant':plant,'review_enabled':plant_workflows.review_enabled(db,plant),'attention_summary':self.store.attention_summary(db,employees,plant),
                'board_layouts':{base:plant_workflows.board_layout(db,base) for base in ({plant} if plant else {''}|{e.get('base','') for e in employees}|{r['base'] for r in db.execute('SELECT base FROM board_layouts')})},
                'plant_controls':{base:plant_workflows.controls(self.store,db,base)['settings'] for base in {e.get('base','') for e in employees}},
                'plant_templates':{base:[plant_workflows.schedule(db,r['id'],base) for r in db.execute('SELECT id FROM schedules')] for base in {e.get('base','') for e in employees}},
                'schedules':[plant_workflows.schedule(db,r['id'],plant) for r in db.execute('SELECT id FROM schedules')],
                'assignments':[dict(r) for r in db.execute("SELECT a.* FROM assignments a LEFT JOIN employees e ON e.id=a.employee_id WHERE (?='' OR e.base=?) ORDER BY start_date DESC",(plant,plant))],
                'settings':settings,
                'devices':[{**{k:r[k] for k in ('id','name','scope','last_seen','health','active','base')},
                            'online':bool(r['last_seen'] and (datetime.now(KL)-stamp(r['last_seen'])).total_seconds()<90)}
                           for r in db.execute("SELECT * FROM devices WHERE ?=''",(plant,))],
                'recent_events':[dict(r) for r in db.execute("SELECT v.*,e.nickname,e.name FROM events v JOIN employees e ON e.id=v.employee_id WHERE (?='' OR e.base=?) ORDER BY received_at DESC LIMIT 30",(plant,plant))],
                'revision':self.store.revision,'time':now_iso()}

    def mutate(self, db, route, method, data):
        actor = getattr(self,'actor','admin')
        plant=getattr(self,'plant','')
        if plant and route.startswith('/api/employees') and method in ('POST','PUT'):
            if 'base' in data and data['base']!=plant:
                raise Problem('You cannot move employees to another plant.',403)
            data={**data,'base':plant}
            photo=data.get('photo_url','')
            if isinstance(photo,str) and photo.startswith('/uploads/'):
                foreign=db.execute("SELECT 1 FROM employees WHERE photo_url=? AND base<>?",(photo,plant)).fetchone()
                owner=db.execute('SELECT actor FROM profile_photos WHERE url=?',(photo,)).fetchone()
                if foreign or (owner and owner['actor']!=actor and not db.execute('SELECT 1 FROM employees WHERE photo_url=? AND base=?',(photo,plant)).fetchone()):
                    raise Problem('Choose a profile photo belonging to this plant.',403)
        if route.startswith('/api/staff/') and method == 'PUT':
            username = route.split('/')[-1]
            if not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}',username) or username == 'admin':
                raise Problem('Choose a staff username other than admin.')
            previous = db.execute('SELECT * FROM staff WHERE username=?',(username,)).fetchone()
            role = data.get('role',previous['role'] if previous else 'employee_admin')
            base = data.get('base',previous['base'] if previous else '')
            if not isinstance(base,str) or (base and not re.fullmatch(r'[A-Z0-9][A-Z0-9 &_.-]{0,79}',base)):
                raise Problem('Use an uppercase plant location of 1–80 characters, or blank for all plants.')
            active = data.get('active',True)
            if role not in ('admin','employee_admin') or type(active) is not bool:
                raise Problem('Choose a valid role and active status.')
            password = data.get('password')
            if password is not None and (not isinstance(password,str) or not 12<=len(password)<=256):
                raise Problem('Use a staff password between 12 and 256 characters.')
            if not previous and password is None:
                raise Problem('A password is required for new staff.')
            salt = secrets.token_hex(16) if password is not None else previous['salt']
            hashed = password_hash(password,salt) if password is not None else previous['password']
            db.execute('INSERT INTO staff(username,salt,password,role,active,base) VALUES(?,?,?,?,?,?) ON CONFLICT(username) DO UPDATE SET salt=excluded.salt,password=excluded.password,role=excluded.role,active=excluded.active,base=excluded.base',(username,salt,hashed,role,int(active),base))
            db.execute('DELETE FROM staff_sessions WHERE username=?',(username,))
            self.store.audit(db,actor,'staff_updated',username,None,{'role':role,'active':active,'base':base})
            return {'ok':True}
        match = re.fullmatch(r'/api/employees/([A-Za-z0-9-]+)/(consents|photo)',route)
        if match:
            eid, kind = match.groups()
            if not db.execute('SELECT 1 FROM employees WHERE id=?',(eid,)).fetchone():
                raise Problem('Employee not found.',404)
            if kind == 'consents' and method == 'GET':
                return {'consents':[dict(r) for r in db.execute('SELECT * FROM employee_consents WHERE employee_id=? ORDER BY id DESC',(eid,))]}
            if kind == 'consents' and method == 'POST':
                employee_admin.record_consent(self.store,db,eid,data,actor,Problem,now_iso())
                return {'ok':True}
            if kind == 'photo' and method == 'DELETE':
                url = db.execute('SELECT photo_url FROM employees WHERE id=?',(eid,)).fetchone()[0]
                updated_at = datetime.now(KL).isoformat()
                db.execute("UPDATE employees SET photo_url='',updated_at=? WHERE id=?",(updated_at,eid))
                # Shared photos stay until all references have been removed.
                if re.fullmatch(r'/uploads/[a-f0-9]+\.jpg',url or '') and not db.execute('SELECT 1 FROM employees WHERE photo_url=?',(url,)).fetchone():
                    db.execute('INSERT INTO profile_photos VALUES(?,?,?,?) ON CONFLICT(url) DO UPDATE SET deleted_at=excluded.deleted_at',(url,actor,now_iso(),now_iso()))
                self.store.audit(db,actor,'profile_photo_deleted',eid,{'photo_url':url},None)
                return {'ok':True,'updated_at':updated_at}
        if route == '/api/manual-attendance' and method == 'POST':
            eid=str(data.get('employee_id',''))
            self.check_plant(db,eid)
            e=db.execute('SELECT * FROM employees WHERE id=?',(eid,)).fetchone()
            if not e:
                raise Problem('Employee not found.')
            reason=str(data.get('reason','')).strip()
            if len(reason)<5:
                raise Problem('Explain why this attendance is being entered manually.')
            tin=stamp(data.get('time_in'))
            tout=stamp(data['time_out']) if data.get('time_out') else None
            if tout and tout<tin:
                raise Problem('Clock-out must be after clock-in.')
            wd=day(data.get('work_date'))
            if db.execute('SELECT 1 FROM sessions WHERE employee_id=? AND time_in<=? AND (time_out IS NULL OR time_out>=?)',
                          (eid,(tout or tin).isoformat(),tin.isoformat())).fetchone():
                raise Problem('This period overlaps an existing attendance session.',409)
            s=self.store.resolve_schedule(db,e,wd)
            pin,pout=self.store.planned(s,wd) if s else (None,None)
            sid=str(uuid.uuid4())
            db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?,?,?)',(sid,eid,str(wd),tin.isoformat(),
                tout.isoformat() if tout else None,s['id'] if s else None,s['name'] if s else None,
                pin.isoformat() if pin else None,pout.isoformat() if pout else None,'[]','manual'))
            self.store.audit(db,'admin','manual_attendance',sid,None,{**data,'reason':reason})
            self.store.snapshot(db,sid,e)
            return {'ok':True}
        if route == '/api/employees' and method == 'POST':
            self.store.validate_employee(db,data)
            self.store.insert_employee(db,data)
            if data.get('consent_record') is not None:
                employee_admin.record_consent(self.store,db,data['id'],data['consent_record'],actor,Problem,now_iso())
            self.store.audit(db,actor,'employee_created',data['id'],None,{f:data.get(f) for f in FIELDS})
            return {'ok':True}
        if route.startswith('/api/employees/') and method in ('PUT','DELETE'):
            eid = route.split('/')[-1]
            previous = db.execute('SELECT * FROM employees WHERE id=?',(eid,)).fetchone()
            if not previous:
                raise Problem('Employee not found.',404)
            before = dict(previous)
            if 'updated_at' in data and data['updated_at'] != before['updated_at']:
                raise Problem('This employee changed since you opened the profile. Close and reopen it before saving.',409)
            after = {**before,**data,'id':eid}
            if method == 'DELETE':
                if db.execute('SELECT 1 FROM sessions WHERE employee_id=? AND time_out IS NULL',(eid,)).fetchone():
                    raise Problem('Close or correct the open session before archiving this employee.',409)
                after['active']=0
            self.store.validate_employee(db,after)
            after['updated_at']=datetime.now(KL).isoformat()
            db.execute('UPDATE employees SET '+','.join(f'{f}=?' for f in FIELDS[1:])+',updated_at=? WHERE id=?',
                       [after.get(f,'') for f in FIELDS[1:]]+[after['updated_at'],eid])
            if data.get('consent_record') is not None:
                employee_admin.record_consent(self.store,db,eid,data['consent_record'],actor,Problem,now_iso())
            self.store.audit(db,actor,'employee_archived' if method=='DELETE' else 'employee_updated',eid,before,{f:after.get(f) for f in FIELDS})
            return {'ok':True}
        if route.startswith('/api/schedules/') and method == 'PUT':
            sid = route.split('/')[-1]
            previous = db.execute('SELECT * FROM schedules WHERE id=?',(sid,)).fetchone()
            if not previous:
                raise Problem('Schedule not found.',404)
            for f in ('start','end'):
                if not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d',data.get(f,'')):
                    raise Problem('Choose valid start and end times.')
            if data['start']==data['end'] or not data.get('name','').strip():
                raise Problem('Name is required and shift times must differ.')
            db.execute('UPDATE schedules SET name=?,start=?,end=?,ot=? WHERE id=?',
                       (data['name'][:100],data['start'],data['end'],int(bool(data.get('ot'))),sid))
            self.store.audit(db,'admin','schedule_updated',sid,dict(previous),data)
            return {'ok':True}
        if route == '/api/assignments' and method == 'POST':
            start, end = day(data.get('start_date')),day(data.get('end_date'))
            if end<start or (end-start).days>366:
                raise Problem('Choose a roster period of up to one year.')
            employee = data.get('employee_id') or None
            team = data.get('team') if not employee else None
            scope = data.get('scope','') if not employee else ''
            if not isinstance(scope,str):
                raise Problem('Choose a valid assignment group.')
            if scope:
                validate_scope(scope)
            if employee:
                if not db.execute('SELECT 1 FROM employees WHERE id=? AND active=1',(employee,)).fetchone():
                    raise Problem('Employee not found.')
            elif team not in ('A','B','C','D','N'):
                raise Problem('Select a team or employee.')
            if not db.execute('SELECT 1 FROM schedules WHERE id=?',(data.get('schedule_id'),)).fetchone():
                raise Problem('Choose a schedule.')
            field,value = ('employee_id',employee) if employee else ('team',team)
            if db.execute(f'SELECT 1 FROM assignments WHERE {field}=? AND scope=? AND start_date<=? AND end_date>=?',(value,scope,str(end),str(start))).fetchone():
                raise Problem('This period overlaps another assignment. Remove the earlier assignment first.',409)
            aid=str(uuid.uuid4())
            db.execute('INSERT INTO assignments (id,employee_id,team,start_date,end_date,schedule_id,scope) VALUES(?,?,?,?,?,?,?)',(aid,employee,team,str(start),str(end),data['schedule_id'],scope))
            self.store.audit(db,'admin','roster_assigned',aid,None,data)
            return {'ok':True}
        if route.startswith('/api/assignments/') and method == 'DELETE':
            aid=route.split('/')[-1]
            previous=db.execute('SELECT * FROM assignments WHERE id=?',(aid,)).fetchone()
            if not previous:
                raise Problem('Assignment not found.',404)
            db.execute('DELETE FROM assignments WHERE id=?',(aid,))
            self.store.audit(db,'admin','roster_removed',aid,dict(previous),None)
            return {'ok':True}
        if route == '/api/settings' and method == 'PUT':
            previous=self.store.settings(db)
            validate_team_settings(db,{key:data.get(key,previous[key]) for key in ('team_schedules','team_overtime','rotation')})
            for key,value in data.items():
                if key not in previous:
                    raise Problem('Unknown setting.')
                if key in ('team_schedules','team_overtime','rotation'):
                    pass  # Validated together above, including partial updates.
                elif key=='schedule_groups':
                    if not isinstance(value,dict) or len(value)>200:
                        raise Problem('Invalid department working hours.')
                    for scope,config in value.items():
                        validate_scope(scope)
                        validate_team_settings(db,config)
                elif key=='employee_sort':
                    if value not in ('position','manual','name'):
                        raise Problem('Choose position, manual or name sorting.')
                elif key=='employee_order':
                    if not isinstance(value,list) or len(value)>10000 or any(not isinstance(eid,str) for eid in value) or len(set(value))!=len(value):
                        raise Problem('Invalid employee order.')
                    known={row['id'] for row in db.execute('SELECT id FROM employees')}
                    if any(eid not in known for eid in value):
                        raise Problem('Employee order includes an unknown employee.')
                elif key in ('normal_auto_out_enabled','normal_auto_out_hour'):
                    if type(value) is not int or not 0<=value<=(1 if key=='normal_auto_out_enabled' else 23):
                        raise Problem('Choose on/off and a cutoff hour from 0 to 23.')
                elif not isinstance(value,int) or not 0<=value<=1440 or (key=='max_open_hours' and not 1<=value<=48):
                    raise Problem('Invalid timing setting.')
                db.execute('UPDATE settings SET value=? WHERE key=?',(json.dumps(value),key))
            self.store.audit(db,'admin','settings_updated','settings',previous,data)
            return {'ok':True}
        if route == '/api/devices' and method == 'POST':
            name=str(data.get('name','')).strip()
            scope=data.get('scope','kiosk')
            base=data.get('base','')
            if not isinstance(base,str) or (base and not re.fullmatch(r'[A-Z0-9][A-Z0-9 &_.-]{0,79}',base)):
                raise Problem('Use an uppercase plant location of 1–80 characters.')
            if not name or scope not in ('kiosk','integration'):
                raise Problem('Enter a name and select a valid access type.')
            token=secrets.token_urlsafe(32)
            did=str(uuid.uuid4())
            db.execute('INSERT INTO devices(id,name,token_hash,scope,base) VALUES(?,?,?,?,?)',(did,name,digest(token),scope,base))
            self.store.audit(db,actor,'device_registered',did,None,{'name':name,'scope':scope,'base':base})
            return {'id':did,'token':token,'name':name}
        if route.startswith('/api/devices/') and method == 'PUT':
            did=route.split('/')[-1]
            base=data.get('base','')
            if not isinstance(base,str) or (base and not re.fullmatch(r'[A-Z0-9][A-Z0-9 &_.-]{0,79}',base)):
                raise Problem('Use an uppercase plant location of 1–80 characters.')
            if not db.execute('SELECT 1 FROM devices WHERE id=?',(did,)).fetchone():
                raise Problem('Device not found.',404)
            db.execute('UPDATE devices SET base=? WHERE id=?',(base,did))
            db.execute('DELETE FROM metadata_receipts WHERE device_id=?',(did,))
            self.store.audit(db,actor,'device_plant_updated',did,None,{'base':base})
            return {'ok':True}
        if route.startswith('/api/devices/') and method == 'DELETE':
            did=route.split('/')[-1]
            db.execute('UPDATE devices SET active=0 WHERE id=?',(did,))
            self.store.audit(db,'admin','device_revoked',did,None,{'active':False})
            return {'ok':True}
        if route.startswith('/api/attendance/') and method == 'PUT':
            sid=route.split('/')[-1]
            previous=db.execute('SELECT * FROM sessions WHERE id=?',(sid,)).fetchone()
            if not previous:
                raise Problem('Session not found.',404)
            self.check_plant(db,previous['employee_id'])
            reason=str(data.get('reason','')).strip()
            if len(reason)<5:
                raise Problem('Explain the correction (at least 5 characters).')
            tin=stamp(data.get('time_in'))
            tout=stamp(data['time_out']) if data.get('time_out') else None
            if tout and tout<tin:
                raise Problem('Clock-out must be after clock-in.')
            work_date=str(day(data.get('work_date',previous['work_date'])))
            if db.execute('SELECT 1 FROM sessions WHERE employee_id=? AND id<>? AND time_in<=? AND (time_out IS NULL OR time_out>=?)',
                          (previous['employee_id'],sid,(tout or datetime.max.replace(tzinfo=KL)).isoformat(),tin.isoformat())).fetchone():
                raise Problem('These times overlap another attendance session.',409)
            flags=json.loads(previous['flags'])
            if data.get('resolve_flags'):
                flags=[]
            after={**dict(previous),'time_in':tin.isoformat(),'time_out':tout.isoformat() if tout else None,
                   'work_date':work_date,'flags':json.dumps(flags),'reason':reason}
            db.execute('UPDATE sessions SET time_in=?,time_out=?,work_date=?,flags=? WHERE id=?',
                       (after['time_in'],after['time_out'],work_date,after['flags'],sid))
            self.store.audit(db,'admin','attendance_corrected',sid,dict(previous),after)
            return {'ok':True}
        if route.startswith('/api/review/') and method == 'POST':
            event_id=route.split('/')[-1]
            event=db.execute('SELECT * FROM events WHERE id=?',(event_id,)).fetchone()
            if not event:
                raise Problem('Scan not found.',404)
            self.check_plant(db,event['employee_id'])
            reason=str(data.get('reason','')).strip()
            if len(reason)<5:
                raise Problem('Explain the review decision.')
            self.store.audit(db,'admin','scan_reviewed',event_id,None,{'reason':reason})
            return {'ok':True}
        raise Problem('Endpoint not found.',404)

    def photo(self, data, db):
        from PIL import Image, ImageOps
        saved_path = None
        try:
            if not isinstance(data.get('data'),str):
                raise Problem('Choose a valid JPG, PNG or WebP photo.')
            raw=base64.b64decode(data.get('data',''),validate=True)
            if len(raw)>5_000_000:
                raise Problem('Choose a photo smaller than 5 MB.')
            with Image.open(io.BytesIO(raw)) as im:
                if im.format not in ('JPEG','PNG','WEBP') or getattr(im,'n_frames',1) != 1:
                    raise Problem('Choose a single-frame JPG, PNG or WebP photo.')
                if im.width*im.height>20_000_000:
                    raise Problem('Photo dimensions are too large.')
                im=ImageOps.exif_transpose(im).convert('RGB')
                im.thumbnail((600,600))
                folder=self.store.path.parent/'uploads'
                folder.mkdir(mode=0o700,exist_ok=True)
                name=secrets.token_hex(16)+'.jpg'
                saved_path = folder/name
                im.save(saved_path,quality=88)
                os.chmod(saved_path,0o600)
            url = '/uploads/'+name
            try:
                db.execute('INSERT INTO profile_photos VALUES(?,?,?,NULL)',(url,self.actor,now_iso()))
                self.store.audit(db,self.actor,'profile_photo_uploaded',url,None,{'bytes':len(raw)})
                db.commit()
            except Exception:
                (folder/name).unlink(missing_ok=True)
                raise
        except Problem:
            raise
        except Exception:
            if saved_path:
                saved_path.unlink(missing_ok=True)
            raise Problem('Choose a valid JPG, PNG or WebP photo.')
        self.send({'url':'/uploads/'+name})

    def events(self):
        self.send_response(200)
        self.send_header('Content-Type','text/event-stream')
        self.send_header('Cache-Control','no-cache')
        self.send_header('Connection','keep-alive')
        self.end_headers()
        revision=-1
        deadline=time.monotonic()+300
        try:
            while time.monotonic()<deadline:
                with self.store.changed:
                    if revision==self.store.revision:
                        self.store.changed.wait(timeout=15)
                    revision=self.store.revision
                self.wfile.write(f'data: {{"revision":{revision}}}\n\n'.encode())
                self.wfile.flush()
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
            pass
        self.close_connection=True

    def static(self, route):
        if self.command!='GET':
            raise Problem('Method not allowed.',405)
        if route.startswith('/uploads/'):
            with self.store.connect() as db:
                who = self.identity(db, allow_device=True)
                if who['scope'] not in ('admin', 'employee_admin', 'integration'):
                    raise Problem('Photo access requires admin or read-only integration access.', 403)
                if not re.fullmatch(r'/uploads/[a-f0-9]+\.jpg', route):
                    raise Problem('Photo not found.', 404)
                if db.execute('SELECT 1 FROM profile_photos WHERE url=? AND deleted_at IS NOT NULL',(route,)).fetchone():
                    raise Problem('Photo not found.',404)
                plant=who.get('base','')
                if plant and not db.execute('SELECT 1 FROM employees WHERE photo_url=? AND base=?',(route,plant)).fetchone():
                    owned=db.execute('SELECT 1 FROM profile_photos WHERE url=? AND actor=?',(route,who['id'])).fetchone()
                    referenced=db.execute('SELECT 1 FROM employees WHERE photo_url=?',(route,)).fetchone()
                    if not owned or referenced:
                        raise Problem('Photo not found.',404)
                if who['scope'] == 'integration' and not db.execute(
                    'SELECT 1 FROM employees WHERE photo_url=? AND active=1', (route,)
                ).fetchone():
                    raise Problem('Photo not found.', 404)
            root=self.store.path.parent/'uploads'
            candidate=root/route.split('/')[-1]
        else:
            root=BASE/'dist'
            candidate=root/route.lstrip('/')
            if not candidate.is_file():
                candidate=root/'index.html'
        if not candidate.resolve().is_relative_to(root.resolve()) or not candidate.is_file():
            raise Problem('Build the React app first (npm run build).',404)
        content_type={'/manifest.webmanifest':'application/manifest+json','/sw.js':'application/javascript'}.get(route)
        raw=candidate.read_bytes()
        if route=='/sw.js':
            # Every new React build changes the worker version without reloading an open form.
            version=hashlib.sha256((root/'index.html').read_bytes()).hexdigest()[:12]
            raw=raw.replace(b'attendance-public-v1',('attendance-public-v1-'+version).encode())
        self.send(raw,content_type=content_type or mimetypes.guess_type(candidate)[0] or 'application/octet-stream')


def make_server(path, host='127.0.0.1', port=8765, seed=True):
    server=ThreadingHTTPServer((host,port),Handler)
    server.store=Store(path,seed)
    server.daemon_threads=True
    server.is_tls=False
    return server


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--db',default=str(BASE/'runtime/attendance.sqlite3'))
    parser.add_argument('--certfile',help='Trusted TLS certificate for company-network HTTPS')
    parser.add_argument('--keyfile',help='TLS private key')
    args=parser.parse_args()
    server=make_server(args.db,args.host,args.port)
    if bool(args.certfile)!=bool(args.keyfile):
        parser.error('Provide both --certfile and --keyfile.')
    if args.certfile:
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version=ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(args.certfile,args.keyfile)
        server.socket=context.wrap_socket(server.socket,server_side=True)
        server.is_tls=True
    clockout_stop,clockout_thread=plant_workflows.start_clockout_worker(server.store)
    normal_stop,normal_thread=attendance_maintenance.start_worker(server.store)
    backup_stop=threading.Event()
    def daily_backup():
        while not backup_stop.is_set():
            destination=server.store.path.parent/'backups'/('attendance-'+str(datetime.now(KL).date())+'.zip')
            if not destination.exists():
                try:
                    server.store.backup(destination)
                    print('[BACKUP] Daily local backup saved.',flush=True)
                except Exception as exc:
                    print('[BACKUP] Failed:',type(exc).__name__,flush=True)
            backup_stop.wait(3600)
    threading.Thread(target=daily_backup,daemon=True).start()
    print(f'Attendance service: {"https" if server.is_tls else "http"}://{args.host}:{args.port}',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        backup_stop.set()
        normal_stop.set()
        clockout_stop.set()
        server.server_close()
