"""A shared OS lock prevents duplicate kiosks, including copies in other folders."""
from contextlib import contextmanager
import errno
import os
from pathlib import Path
import tempfile


class KioskAlreadyRunning(RuntimeError):
    pass


def default_lock_path():
    # A fixed per-user path on the Pi, independent of cwd, clone or service env.
    if os.name == 'posix':
        return Path('/tmp') / f'digital-attendance-kiosk-{os.getuid()}.lock'
    return Path(tempfile.gettempdir()) / 'digital-attendance-kiosk.lock'


@contextmanager
def kiosk_instance(path=None):
    path = default_lock_path() if path is None else Path(path)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(descriptor, 'r+b') as handle:
        if os.name == 'nt' and os.fstat(handle.fileno()).st_size == 0:
            handle.write(b'\n')
            handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise
            raise KioskAlreadyRunning(
                'Attendance kiosk is already running for this user. '
                'This second launch will exit without opening the camera.') from None
        # Do not truncate before acquiring the lock, or unlink this file after
        # closing: every launcher must continue to lock the same filesystem object.
        handle.seek(0)
        handle.write(f'{os.getpid()}\n'.encode('ascii'))
        handle.truncate()
        handle.flush()
        yield
        # close() releases the OS lock, including after an exception.
