"""One writing job at a time, across processes.

The scheduler's jobs run in threads of the web process. The deploy's data steps and the hand-run
commands run in their own `python -m app.cli` processes, and the theme model runs in a child process
the scheduler starts. A threading lock only covers the first, so a job also holds an exclusive lock
on DATA_DIR/jobs.lock. The operating system drops that lock when its process ends, so a crash never
leaves it behind.

held() is re-entrant within a thread (a CLI command that calls a scheduled job takes it once).
A child started while the lock is held gets HELD_ENV=1 in its environment and does not take the
lock again: it would wait for its own parent.

Imports nothing heavy: the CLI takes the lock before it loads anything else."""
import os
import threading
import time
from contextlib import contextmanager

from . import settings

HELD_ENV = "DW_JOB_LOCK_HELD"
WAIT_NOTE = ("Another job holds the job lock ({path}): a scheduled job or another command. "
             "Waiting for it to finish.")

_thread = threading.RLock()
_depth = 0
_owner: int | None = None
_fd: int | None = None


def path():
    return settings.DATA_DIR / "jobs.lock"


def _try_lock(fd: int) -> bool:
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _wait_lock(fd: int) -> None:
    if os.name == "nt":
        while not _try_lock(fd):
            time.sleep(0.25)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX)


def _unlock(fd: int) -> None:
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _open() -> int:
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    # read-only is enough to lock, so a lock file another user created (a command run as root) still works
    return os.open(path(), os.O_RDONLY | os.O_CREAT, 0o666)


def is_held() -> bool:
    """Whether this thread holds the job lock (so a child it starts must not take it)."""
    return _depth > 0 and _owner == threading.get_ident()


@contextmanager
def held(note=None):
    """Hold the job lock for the block. `note(text)` is called once if another process holds it and
    we have to wait."""
    global _depth, _owner, _fd
    with _thread:
        if _depth == 0 and not os.environ.get(HELD_ENV):
            fd = _open()
            if not _try_lock(fd):
                if note:
                    note(WAIT_NOTE.format(path=path()))
                try:
                    _wait_lock(fd)
                except BaseException:
                    os.close(fd)
                    raise
            _fd = fd
        if _depth == 0:
            _owner = threading.get_ident()
        _depth += 1
        try:
            yield
        finally:
            _depth -= 1
            if _depth == 0:
                _owner = None
                if _fd is not None:
                    fd, _fd = _fd, None
                    _unlock(fd)
