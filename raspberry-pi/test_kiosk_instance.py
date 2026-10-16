"""Check competing processes and lock release without camera/Tk dependencies."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from kiosk_instance import kiosk_instance


CHILD = '''
import sys
from kiosk_instance import kiosk_instance, KioskAlreadyRunning
try:
    with kiosk_instance(sys.argv[1]):
        print('acquired')
except KioskAlreadyRunning:
    sys.exit(75)
'''


class KioskInstanceTests(unittest.TestCase):
    def setUp(self):
        scratch_root = Path(__file__).parent / 'runtime' / 'tests'
        scratch_root.mkdir(parents=True, exist_ok=True)
        self.scratch = tempfile.TemporaryDirectory(dir=scratch_root)
        self.addCleanup(self.scratch.cleanup)
        self.path = Path(self.scratch.name) / 'kiosk.lock'

    def child(self):
        return subprocess.run([sys.executable, '-c', CHILD, str(self.path)],
                              cwd=Path(__file__).parent, capture_output=True, text=True, timeout=10)

    def test_competing_process_is_rejected_then_can_start_after_owner_exits(self):
        with kiosk_instance(self.path):
            other = self.child()
            self.assertEqual(other.returncode, 75, other.stderr)
        other = self.child()
        self.assertEqual(other.returncode, 0, other.stderr)
        self.assertEqual(other.stdout.strip(), 'acquired')

    def test_stale_pid_text_does_not_block_a_new_instance(self):
        self.path.write_text('999999999\n', encoding='ascii')
        with kiosk_instance(self.path):
            pass
        self.assertEqual(self.path.read_text().strip(), str(os.getpid()))

    def test_exception_releases_lock_and_file_remains(self):
        with self.assertRaisesRegex(RuntimeError, 'test'):
            with kiosk_instance(self.path):
                raise RuntimeError('test')
        self.assertTrue(self.path.exists())
        self.assertEqual(self.child().returncode, 0)


if __name__ == '__main__':
    unittest.main()
