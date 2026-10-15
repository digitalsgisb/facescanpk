import json
import queue
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).parent.parent/'ai-pc'))
from server import make_server,digest
from kiosk_transport import ReliableTransport
from kiosk_config import load_config, validate_config
from configure_kiosk import check_connection, save_config

TEST_ROOT=Path(__file__).resolve().parent.parent/'ai-pc/runtime/tests'
TEST_ROOT.mkdir(parents=True,exist_ok=True)


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=TEST_ROOT)
        self.server=make_server(Path(self.temp.name)/'server.sqlite3',port=0,seed=False)
        with self.server.store.connect() as db:
            self.server.store.insert_employee(db,{'id':'123','name':'Test Worker','team':'N','schedule_id':'normal'})
            db.execute('INSERT INTO devices(id,name,token_hash,scope) VALUES(?,?,?,?)',('test-pi','Test Pi',digest('test-token'),'kiosk'))
        self.server_thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.server_thread.start()
        self.results=queue.Queue()
        self.transport=None

    def tearDown(self):
        if self.transport:
            self.transport.close()
            self.transport.thread.join(timeout=5)
        self.server.shutdown()
        self.server.server_close()
        assert Path(self.temp.name).resolve().is_relative_to(TEST_ROOT.resolve())
        self.temp.cleanup()

    def create_transport(self,base=None):
        return ReliableTransport(base or f'http://127.0.0.1:{self.server.server_port}','test-token',Path(self.temp.name)/'kiosk',
            lambda uid,r:self.results.put((uid,r)),lambda *args:None)

    def test_connection_setup_verifies_kiosk_scope_without_attendance(self):
        url=f'http://127.0.0.1:{self.server.server_port}'
        self.assertEqual(check_connection(url,'test-token'),1)
        with self.assertRaises(ValueError):
            check_connection(url,'wrong-token')
        with self.server.store.connect() as db:
            db.execute('INSERT INTO devices(id,name,token_hash,scope) VALUES(?,?,?,?)',('production','Production',digest('read-only'),'integration'))
        with self.assertRaisesRegex(ValueError,'kiosk token'):
            check_connection(url,'read-only')
        with self.server.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],0)

    def test_configuration_loads_for_direct_launch_and_env_overrides(self):
        folder=Path(self.temp.name)
        save_config(folder,'http://192.168.1.2:8765/','saved-token')
        self.assertEqual(load_config(folder,{}),('http://192.168.1.2:8765','saved-token'))
        self.assertEqual(load_config(folder,{'ATTENDANCE_DEVICE_TOKEN':'environment-token'}),('http://192.168.1.2:8765','environment-token'))
        with self.assertRaises(ValueError):
            save_config(folder,'http://0.0.0.0:8765','bad-token')
        self.assertEqual(load_config(folder,{})[1],'saved-token')
        for url,token in [('', 'token'),('http://pc:8765',''),('http://pc:8765','replace-with-a-token'),('http://user:pass@pc:8765','token')]:
            with self.assertRaises(ValueError):
                validate_config(url,token)

    def test_lost_confirmation_is_retried_without_duplicate(self):
        original=ReliableTransport.request
        lost=[False]
        def request(transport,path,payload=None):
            r=original(transport,path,payload)
            if path=='/api/scans' and not lost[0]:
                lost[0]=True
                raise ConnectionError('Simulated lost response after database commit')
            return r
        with patch.object(ReliableTransport,'request',request):
            self.transport=self.create_transport()
            eid,created=self.transport.submit('123','Test Worker')
            self.assertTrue(created)
            uid,result=self.results.get(timeout=10)
            self.assertEqual(result['event_id'],eid)
            self.assertEqual(result['action'],'IN')
            self.assertEqual(self.transport.pending(),0)
            with self.server.store.connect() as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0],1)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],1)

    def test_pending_scan_survives_kiosk_restart(self):
        self.transport=self.create_transport('')
        self.transport.url=''
        eid,created=self.transport.submit('123','Test Worker')
        self.transport.close()
        self.transport.thread.join(timeout=5)
        self.transport=self.create_transport()
        uid,result=self.results.get(timeout=10)
        self.assertEqual(result['event_id'],eid)
        self.assertEqual(self.transport.pending(),0)

    def test_offline_arrival_and_later_departure_are_both_queued(self):
        with patch.object(threading.Thread,'start'):
            self.transport=self.create_transport()
        self.transport.thread=None
        first,created=self.transport.submit('123','Test Worker')
        repeated,created=self.transport.submit('123','Test Worker')
        self.assertFalse(created)
        self.assertEqual(first,repeated)
        db=self.transport.connect()
        try:
            with db:
                db.execute('UPDATE outbox SET created_at=created_at-3600')
        finally:
            db.close()
        second,created=self.transport.submit('123','Test Worker')
        self.assertTrue(created)
        self.assertNotEqual(first,second)
        self.assertEqual(self.transport.pending(),2)
        self.transport=None


if __name__=='__main__':
    unittest.main(verbosity=2)
