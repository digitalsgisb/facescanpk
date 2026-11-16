"""Checksheet integration writes: correct an employee's shift team and line.

The integration token stays read-only for everything else. Only these fields of
active Production employees may change, all changes in one request are applied
together or not at all, and every change is audited with the Checksheet user.
"""
import re

FIELDS = ('team', 'line', 'checksheet_group', 'production_section', 'base')
TEAMS = ('', 'A', 'B', 'N')


def _text(value, name, problem, limit=40):
    if not isinstance(value, str) or len(value.strip()) > limit or not re.fullmatch(r'[A-Za-z0-9 &/.-]*', value.strip()):
        raise problem(f'Invalid {name}.')
    return value.strip()


def apply(store, db, data, device, plant, problem, now):
    changes = data.get('changes') if isinstance(data, dict) else None
    changed_by = data.get('changed_by', '') if isinstance(data, dict) else ''
    if not isinstance(changed_by, str) or not changed_by.strip() or len(changed_by) > 80:
        raise problem('Name the Checksheet user making this change.')
    if not isinstance(changes, list) or not 1 <= len(changes) <= 500:
        raise problem('Send between 1 and 500 employee changes.')
    actor = f'{device}:{changed_by.strip()}'
    seen, results = set(), []
    for change in changes:
        if not isinstance(change, dict) or not isinstance(change.get('id'), str) or set(change) - {'id', *FIELDS} or len(change) < 2:
            raise problem('Each change needs an employee ID and only team, line, FC group, section or plant.')
        eid = change['id']
        if eid in seen:
            raise problem('Each employee may appear only once.')
        seen.add(eid)
        row = db.execute('SELECT * FROM employees WHERE id=?', (eid,)).fetchone()
        if not row:
            raise problem('Employee not found.', 404)
        before = dict(row)
        if not before['active'] or (before.get('department') or '').strip().upper() != 'PRODUCTION':
            raise problem('Only active Production employees can be changed from the Checksheet.', 403)
        after = dict(before)
        if 'team' in change:
            if change['team'] not in TEAMS:
                raise problem('Choose shift A, B or N.')
            after['team'] = change['team']
        for field, name in (('line', 'line'), ('production_section', 'section'), ('base', 'plant'), ('checksheet_group', 'FC group')):
            if field in change:
                after[field] = _text(change[field], name, problem)
        if not after.get('line'):
            raise problem('Choose a line.')
        if (after.get('line') or '').strip().upper() != 'FC':
            after['checksheet_group'] = ''
        # A plant-limited token may only move people within its own plant.
        if plant and (before.get('base') != plant or after.get('base') != plant):
            raise problem('This token manages its assigned plant only.', 403)
        store.validate_employee(db, after)
        after['updated_at'] = now
        db.execute('UPDATE employees SET team=?,line=?,checksheet_group=?,production_section=?,base=?,updated_at=? WHERE id=?',
                   (after['team'], after['line'], after['checksheet_group'], after['production_section'], after['base'], now, eid))
        store.audit(db, actor, 'employee_assignment_from_checksheet', eid,
                    {f: before.get(f) for f in FIELDS}, {f: after.get(f) for f in FIELDS})
        results.append({'id': eid, **{f: after.get(f) for f in FIELDS}})
    return {'ok': True, 'employees': results}
