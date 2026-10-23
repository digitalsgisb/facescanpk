"""Normal-shift cutoff and kiosk-reported face enrollment (no biometric data)."""
import json
import threading
import uuid
from datetime import datetime, timedelta, timezone

KL = timezone(timedelta(hours=8))


def release_stale_session(store, db, session, occurred, config):
    """Free current attendance while retaining the old missing departure for review.

    Called inside the scan transaction, so retries cannot close an old record twice.
    The estimated end is explicit in flags and audit, never represented as a scan.
    """
    started = datetime.fromisoformat(session['time_in']).astimezone(KL)
    estimated = (datetime.fromisoformat(session['planned_out']).astimezone(KL)
                 if session['planned_out'] else started + timedelta(hours=config['max_open_hours']))
    if estimated <= started:
        estimated = started + timedelta(hours=config['max_open_hours'])
    estimated = min(estimated, occurred)
    flags = list(dict.fromkeys(json.loads(session['flags']) +
                              ['stale_open_session', 'missing_clock_out', 'estimated_clock_out']))
    db.execute('UPDATE sessions SET time_out=?,flags=? WHERE id=? AND time_out IS NULL',
               (estimated.isoformat(),json.dumps(flags),session['id']))
    store.audit(db,'system','stale_session_released_for_review',session['id'],dict(session),
                {**dict(session),'time_out':estimated.isoformat(),'flags':json.dumps(flags),
                 'reason':'Estimated departure; new attendance can continue while the old record awaits review.'})


def run_normal_clockout(store, now=None):
    now = (now or datetime.now(KL)).astimezone(KL)
    closed = 0
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        config = store.settings(db)
        if not config['normal_auto_out_enabled']:
            return 0
        for row in db.execute("SELECT * FROM sessions WHERE time_out IS NULL AND schedule_id='normal'").fetchall():
            started = datetime.fromisoformat(row['time_in']).astimezone(KL)
            work_day = datetime.fromisoformat(row['work_date']).date()
            # An overnight version of Normal is not a daytime normal shift.
            if row['planned_out'] and datetime.fromisoformat(row['planned_out']).astimezone(KL).date() > work_day:
                continue
            cutoff = datetime.combine(work_day + timedelta(days=1), datetime.min.time(), KL)
            cutoff += timedelta(hours=config['normal_auto_out_hour'])
            if not started < cutoff <= now:
                continue
            before = dict(row)
            flags = list(dict.fromkeys(json.loads(row['flags']) + ['automatic_clock_out']))
            db.execute('UPDATE sessions SET time_out=?,flags=? WHERE id=? AND time_out IS NULL',
                       (cutoff.isoformat(), json.dumps(flags), row['id']))
            event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'normal-auto-out:' + row['id']))
            result = {'event_id':event_id, 'employee_id':row['employee_id'], 'session_id':row['id'],
                      'accepted':True, 'action':'OUT', 'timestamp':cutoff.isoformat(),
                      'work_date':row['work_date'], 'source':'automatic_clockout',
                      'flags':['automatic_clock_out'], 'message':'Normal shift automatically clocked out; actual departure needs review.'}
            db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?)',
                       (event_id,row['employee_id'],'normal-auto-out',cutoff.isoformat(),now.isoformat(),
                        'normal-auto-out:' + row['id'],json.dumps(result)))
            store.audit(db,'system','normal_automatic_clock_out',row['id'],before,
                        {**before,'time_out':cutoff.isoformat(),'flags':json.dumps(flags)})
            closed += 1
    if closed:
        store.emit()
    return closed


def start_worker(store):
    stop = threading.Event()
    def work():
        while not stop.is_set():
            try:
                run_normal_clockout(store)
            except Exception as error:
                print('[NORMAL CLOCKOUT]', type(error).__name__, str(error), flush=True)
            stop.wait(15)
    worker = threading.Thread(target=work, daemon=True, name='normal-clockout')
    worker.start()
    return stop, worker


def validate_enrollment(data, Problem):
    ids = data.get('face_employee_ids')
    if 'face_employee_ids' in data and (not isinstance(ids,list) or len(ids)>10000 or
                            any(not isinstance(eid,str) or len(eid)>40 for eid in ids)):
        raise Problem('Invalid face registration report.')


def decorate_enrollment(db, employees, now=None):
    now = now or datetime.now(KL)
    devices = []
    for row in db.execute("SELECT * FROM devices WHERE active=1 AND scope='kiosk'"):
        device = dict(row)
        health = json.loads(device['health'] or '{}')
        devices.append((device, set(health.get('face_employee_ids', [])),
                        'face_employee_ids' in health))
    for employee in employees:
        relevant = [(device, ids, reported) for device, ids, reported in devices
                    if not device.get('base') or device.get('base') == employee.get('base')]
        fresh = [(device, ids) for device, ids, reported in relevant
                 if reported and device['last_seen'] and
                 0 <= (now-datetime.fromisoformat(device['last_seen'])).total_seconds() < 90]
        # Pending requires a current inventory; offline/old kiosks stay unknown.
        employee['face_registration'] = ('registered' if any(employee['id'] in ids for _,ids in fresh)
                                         else 'pending' if fresh and len(fresh)==len(relevant) else 'unknown')
        employee['face_reported_at'] = max((device['last_seen'] for device,_,reported in relevant
                                           if reported and device['last_seen']), default=None)
    return employees
