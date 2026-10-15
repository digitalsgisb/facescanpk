import tempfile
import unittest
from pathlib import Path
from server import Store, digest, password_hash
from manage import init_admin, create_kiosk

TEST_ROOT=Path(__file__).resolve().parent/'runtime/tests'
TEST_ROOT.mkdir(parents=True,exist_ok=True)


class HeadlessSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=TEST_ROOT)
        self.store=Store(Path(self.temp.name)/'test.sqlite3',seed=False)

    def tearDown(self):
        self.temp.cleanup()

    def test_admin_password_is_hashed_and_cannot_be_overwritten(self):
        init_admin(self.store,'temporary-test-password','temporary-test-password')
        with self.store.connect() as db:
            first=dict(db.execute('SELECT * FROM admin').fetchone())
            self.assertEqual(first['password'],password_hash('temporary-test-password',first['salt']))
            self.assertNotIn('temporary-test-password',str([dict(r) for r in db.execute('SELECT * FROM audit')]))
        with self.assertRaises(ValueError):
            init_admin(self.store,'different-test-password','different-test-password')
        with self.store.connect() as db:
            self.assertEqual(dict(db.execute('SELECT * FROM admin').fetchone()),first)

    def test_invalid_passwords_do_not_create_an_admin(self):
        for password,confirmation in [('short','short'),('temporary-test-password','different-test-password')]:
            with self.assertRaises(ValueError):
                init_admin(self.store,password,confirmation)
        with self.store.connect() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM admin').fetchone())

    def test_kiosk_token_is_scoped_hashed_and_audited_without_recording_attendance(self):
        with self.assertRaises(ValueError):
            create_kiosk(self.store,'Pi')
        init_admin(self.store,'temporary-test-password','temporary-test-password')
        token=create_kiosk(self.store,'Port Klang Pi')
        with self.store.connect() as db:
            device=dict(db.execute('SELECT * FROM devices').fetchone())
            self.assertEqual(device['scope'],'kiosk')
            self.assertEqual(device['token_hash'],digest(token))
            self.assertNotIn(token,str([dict(r) for r in db.execute('SELECT * FROM audit')]))
            self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
