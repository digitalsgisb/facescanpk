"""Durable scan delivery for face.py. HTTP retries never run in the Tk thread."""
import json
import os
import queue
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
import urllib.request
import urllib.error

KL = timezone(timedelta(hours=8))


class Response:
    def __init__(self, status, raw):
        self.status_code, self.raw = status, raw

    def json(self):
        return json.loads(self.raw)

    def raise_for_status(self):
        if not 200 <= self.status_code < 300:
            raise ConnectionError(f'Attendance API returned HTTP {self.status_code}')


class ReliableTransport:
    def __init__(self, base_url, token, directory, on_result, on_health):
        self.url = base_url.rstrip('/')
        self.token = token
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db_path = self.directory / 'outbox.sqlite3'
        self.on_result, self.on_health = on_result, on_health
        self.stop = threading.Event()
        self.status_cache = {}
        self.worker_cache = {}
        self.cache_lock = threading.Lock()
        self.online = False
        self.cooldown_seconds = 300
        self.camera_health = 'starting'
        self.ai_health = 'starting'
        self.face_employee_ids = None
        self.headers = {'Authorization':'Bearer '+token}
        db = self.connect()
        try:
            with db:
                db.execute('''CREATE TABLE IF NOT EXISTS outbox (
                    event_id TEXT PRIMARY KEY, employee_id TEXT NOT NULL, payload TEXT NOT NULL,
                    created_at REAL NOT NULL, state TEXT NOT NULL DEFAULT 'pending', result TEXT, error TEXT)''')
        finally:
            db.close()
        self._read_cache()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def connect(self):
        # Use short-lived connections with explicit close at call sites.
        db = sqlite3.connect(self.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA synchronous=FULL')
        return db

    def pending(self):
        db = self.connect()
        try:
            return db.execute("SELECT COUNT(*) FROM outbox WHERE state='pending'").fetchone()[0]
        finally:
            db.close()

    def submit(self, employee_id, name):
        db = self.connect()
        try:
            with db:
                db.execute('BEGIN IMMEDIATE')
                # Deduplicate rapid repeats across restarts, but retain later encounters
                # so both arrival and departure are saved during a long PC outage.
                existing=db.execute('SELECT event_id,created_at FROM outbox WHERE employee_id=? ORDER BY created_at DESC LIMIT 1',
                                    (str(employee_id),)).fetchone()
                if existing and time.time()-existing['created_at'] < self.cooldown_seconds:
                    return existing['event_id'], False
                event_id=str(uuid.uuid4())
                payload={'event_id':event_id,'employee_id':str(employee_id),
                         'timestamp':datetime.now(KL).isoformat(timespec='seconds')}
                db.execute('INSERT INTO outbox(event_id,employee_id,payload,created_at) VALUES(?,?,?,?)',
                           (event_id,str(employee_id),json.dumps(payload),time.time()))
            return event_id, True
        finally:
            db.close()

    def _read_cache(self):
        try:
            workers=json.loads((self.directory/'employees-cache.json').read_text())['employees']
            self.set_cache(workers)
        except (OSError, ValueError, KeyError):
            pass

    def set_cache(self, workers):
        with self.cache_lock:
            self.worker_cache={str(w['id']):w for w in workers}
            self.status_cache={str(w['id']):w.get('status','UNKNOWN') for w in workers}

    def workers(self):
        with self.cache_lock:
            return dict(self.worker_cache)

    def confirmation(self, event_id):
        db=self.connect()
        try:
            row=db.execute('SELECT state,result FROM outbox WHERE event_id=?',(event_id,)).fetchone()
            return json.loads(row['result']) if row and row['state']=='confirmed' else None
        finally:
            db.close()

    def request(self, path, payload=None):
        request=urllib.request.Request(self.url+path,method='POST' if payload is not None else 'GET',
                    headers={**self.headers,'Content-Type':'application/json'},
                    data=json.dumps(payload).encode() if payload is not None else None)
        try:
            with urllib.request.urlopen(request,timeout=8) as response:
                return Response(response.status,response.read())
        except urllib.error.HTTPError as response:
            try:
                return Response(response.code,response.read())
            finally:
                response.close()

    def run(self):
        next_health=0
        delay=1
        while not self.stop.is_set():
            db=None
            try:
                if not self.url or not self.token:
                    self.on_health(False,self.pending(),'Configure the attendance API address and kiosk token.')
                    self.stop.wait(5)
                    continue
                if time.monotonic()>=next_health:
                    r=self.request('/api/employees')
                    r.raise_for_status()
                    data=r.json()
                    self.cooldown_seconds=data.get('cooldown_seconds',300)
                    self.set_cache(data['employees'])
                    temp=self.directory/'employees-cache.tmp'
                    with temp.open('w',encoding='utf-8') as cache_file:
                        json.dump(data,cache_file)
                        cache_file.flush()
                        os.fsync(cache_file.fileno())
                    os.replace(temp,self.directory/'employees-cache.json')
                    # Acknowledge only metadata already saved to the offline cache.
                    acknowledgement = {'metadata_version':data['metadata_version']} if data.get('metadata_version') else {}
                    health_db=self.connect()
                    try:
                        rejected=health_db.execute("SELECT COUNT(*) FROM outbox WHERE state='rejected'").fetchone()[0]
                    finally:
                        health_db.close()
                    self.request('/api/heartbeat',{'camera':self.camera_health,'ai':self.ai_health,
                                                  **({'face_employee_ids':list(self.face_employee_ids)} if self.face_employee_ids is not None else {}),
                                                  'pending_scans':self.pending(),'rejected_scans':rejected,
                                                  **acknowledgement}).raise_for_status()
                    next_health=time.monotonic()+20
                db=self.connect()
                item=db.execute("SELECT * FROM outbox WHERE state='pending' ORDER BY created_at, event_id LIMIT 1").fetchone()
                if item:
                    r=self.request('/api/scans',json.loads(item['payload']))
                    if r.status_code in (400,409,422):
                        # Keep rejected scans on disk for inspection; do not retry permanently invalid input.
                        message=r.json().get('error','Scan needs correction')
                        with db:
                            db.execute("UPDATE outbox SET state='rejected',error=? WHERE event_id=?",(message,item['event_id']))
                        self.on_result(item['employee_id'],{'action':'REJECTED','message':message})
                    else:
                        r.raise_for_status()
                        result=r.json()
                        if result.get('event_id')!=item['event_id'] or not result.get('accepted'):
                            raise ValueError('Invalid attendance confirmation')
                        with db:
                            db.execute("UPDATE outbox SET state='confirmed',result=?,error=NULL WHERE event_id=?",(json.dumps(result),item['event_id']))
                        with self.cache_lock:
                            if result['action'] in ('IN','OUT'):
                                self.status_cache[item['employee_id']]=result['action']
                        self.on_result(item['employee_id'],result)
                self.online=True
                self.on_health(True,self.pending(),'')
                delay=1
                self.stop.wait(.25 if item else 1)
            except Exception as exc:
                self.online=False
                self.on_health(False,self.pending(),str(exc)[:160])
                next_health=0
                self.stop.wait(delay)
                delay=min(delay*2,30)
            finally:
                if db:
                    db.close()

    def close(self):
        self.stop.set()

