"""Production staff managed from Smart Checksheet.

The Checksheet integration token may add Production employees, edit their
details, and deactivate or reactivate them. Office staff stay out of reach.
Once the Checksheet has saved one employee, Production details become
read-only everywhere else in Attendance (admin form, archive, spreadsheet
import) so there is one place to edit them. Photos, consent, working hours and
face enrollment stay in Attendance.
"""
import json
import re

# Operator covers forming, waterjet and assembly. The three older values stay valid for records saved before Operator existed.
ROLES = ('', 'SUPERVISOR', 'LEADER', 'OPERATOR', 'QUALITY', 'FORMING', 'WATERJET', 'ASSEMBLY')
COVERING_ROLES = ('SUPERVISOR', 'LEADER')
# Production details the Checksheet owns once the lock is on.
LOCKED = ('name', 'nickname', 'department', 'position', 'line', 'team', 'production_section', 'checksheet_group', 'base', 'active')
EDITABLE = ('name', 'nickname', 'position', 'line', 'team', 'production_section', 'checksheet_group', 'base', 'active', 'checksheet_role', 'covers_lines')
SETTING = 'checksheet_manages_production'
LINE = re.compile(r'[A-Z0-9][A-Z0-9 &/.-]{0,39}')


def migrate(db):
    columns = {r['name'] for r in db.execute('PRAGMA table_info(employees)')}
    if 'checksheet_role' not in columns:
        db.execute("ALTER TABLE employees ADD COLUMN checksheet_role TEXT NOT NULL DEFAULT ''")
    if 'covers_lines' not in columns:
        db.execute("ALTER TABLE employees ADD COLUMN covers_lines TEXT NOT NULL DEFAULT '[]'")
    db.execute('INSERT OR IGNORE INTO settings VALUES(?,?)', (SETTING, json.dumps(0)))


def production(e):
    return bool(e) and (e.get('department') or '').strip().upper() == 'PRODUCTION'


def locked(db):
    row = db.execute('SELECT value FROM settings WHERE key=?', (SETTING,)).fetchone()
    return bool(row and json.loads(row['value']))


def guard(db, before, after, problem):
    """Refuse changes to Production details made outside the Checksheet while the lock is on."""
    if not locked(db) or not (production(before) or production(after)):
        return
    if before is None or any(_same(before.get(f)) != _same(after.get(f)) for f in LOCKED):
        raise problem('Production staff are managed in Smart Checksheet. Change their details there.', 403)


def _same(value):
    return int(value) if isinstance(value, bool) else '' if value is None else value


def _text(value, name, problem, limit=80, required=False):
    if not isinstance(value, str) or len(value.strip()) > limit:
        raise problem(f'Invalid {name}.')
    if required and not value.strip():
        raise problem(f'Enter the {name}.')
    return value.strip()


def _clean(e, problem):
    role = e.get('checksheet_role', '')
    if role not in ROLES:
        raise problem('Choose Supervisor, Leader, Operator or Quality.')
    covers = e.get('covers_lines', [])
    if isinstance(covers, str):
        covers = json.loads(covers or '[]')
    if not isinstance(covers, list) or len(covers) > 30 or any(not isinstance(l, str) or not LINE.fullmatch(l) for l in covers):
        raise problem('Choose the lines this person covers.')
    line = (e.get('line') or '').strip().upper()
    # Only supervisors and leaders cover other lines; their home line is always included.
    covers = sorted({*covers, line} - {''}) if role in COVERING_ROLES else []
    return {**e, 'line': line, 'checksheet_role': role, 'covers_lines': json.dumps(covers)}


def save(store, db, data, device, plant, problem, now, eid=None):
    """Create (eid None) or edit one Production employee. Runs inside the caller's transaction."""
    if not isinstance(data, dict) or not isinstance(data.get('employee'), dict):
        raise problem('Send the employee details.')
    changed_by = data.get('changed_by', '')
    if not isinstance(changed_by, str) or not changed_by.strip() or len(changed_by) > 80:
        raise problem('Name the Checksheet user making this change.')
    given = data['employee']
    if set(given) - {'id', *EDITABLE}:
        raise problem('Only Production details can be changed from the Checksheet.')
    row = db.execute('SELECT * FROM employees WHERE id=?', (eid if eid is not None else given.get('id'),)).fetchone()
    before = dict(row) if row else None
    if eid is None:
        if before:
            raise problem('That staff ID is already used.', 409)
        after = {'id': given.get('id', ''), 'photo_url': '', 'schedule_id': 'normal', 'office_department': '', 'company': '', 'employment_department': '', 'job_type': '', 'active': True, 'checksheet_role': '', 'covers_lines': '[]'}
    else:
        if not before:
            raise problem('Employee not found.', 404)
        if not production(before):
            raise problem('Only Production employees can be changed from the Checksheet.', 403)
        if data.get('updated_at') != before['updated_at']:
            raise problem('This employee changed since you opened it. Reload and try again.', 409)
        after = dict(before)
    for field in EDITABLE:
        if field in given:
            after[field] = given[field]
    after['department'] = 'PRODUCTION'
    after['name'] = _text(after.get('name'), 'full name', problem, required=True)
    for field in ('nickname', 'position'):
        after[field] = _text(after.get(field) or '', field, problem)
    after['base'] = _text(after.get('base') or '', 'plant', problem).upper()
    if not after['base']:
        raise problem('Choose the plant.')
    if not (after.get('line') or '').strip():
        raise problem('Choose a line.')
    if not isinstance(after.get('active'), (bool, int)) or after['active'] not in (True, False, 0, 1):
        raise problem('Active must be true or false.')
    after = _clean(after, problem)
    if after['line'] != 'FC':
        after['checksheet_group'] = ''
    # A plant-limited token may only manage its own plant.
    if plant and (after['base'] != plant or (before and before.get('base') != plant)):
        raise problem('This token manages its assigned plant only.', 403)
    if before and before['active'] and not after['active'] and db.execute('SELECT 1 FROM sessions WHERE employee_id=? AND time_out IS NULL', (before['id'],)).fetchone():
        raise problem('This person is still clocked in. Clock them out before deactivating.', 409)
    store.validate_employee(db, after)
    after['updated_at'] = now
    if before is None:
        store.insert_employee(db, after)
    columns = [f for f in LOCKED if f != 'department'] + ['department', 'checksheet_role', 'covers_lines']
    db.execute('UPDATE employees SET ' + ','.join(f'{c}=?' for c in columns) + ',updated_at=? WHERE id=?',
               [int(after[c]) if c == 'active' else after.get(c, '') for c in columns] + [now, after['id']])
    actor = f'{device}:{changed_by.strip()}'
    fields = ('id', *EDITABLE, 'department')
    store.audit(db, actor, 'employee_created_from_checksheet' if before is None else 'employee_updated_from_checksheet', after['id'],
                {f: before.get(f) for f in fields} if before else None, {f: after.get(f) for f in fields})
    if not locked(db):
        db.execute('UPDATE settings SET value=? WHERE key=?', (json.dumps(1), SETTING))
        store.audit(db, actor, 'production_staff_managed_by_checksheet', SETTING, {'value': 0}, {'value': 1})
    saved = dict(db.execute('SELECT * FROM employees WHERE id=?', (after['id'],)).fetchone())
    return {'ok': True, 'employee': {**{f: saved.get(f) for f in fields}, 'covers_lines': json.loads(saved['covers_lines'] or '[]'), 'updated_at': saved['updated_at']}}
