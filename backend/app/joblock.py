"""One writing job at a time, across processes.

The scheduler's jobs run in threads of the web process. The deploy's data steps and the hand-run
commands run in their own `python -m app.cli` processes, and the theme model and the recomputes run
in child processes the scheduler starts. A threading lock only covers the first, so a job also holds
an exclusive lock on DATA_DIR/jobs.lock. The operating system drops that lock when its process ends,
so a crash never leaves it behind.

held() is re-entrant within a thread (a CLI command that calls a scheduled job takes it once).
A child started while the lock is held gets HELD_ENV=1 in its environment and does not take the
lock again: it would wait for its own parent.

Next to the lock file, jobs.lock.holder says who holds it (pid, job, since) for the admin health
page. It is written and removed on a best-effort basis: the lock itself is the file lock, never the
sidecar, so a stale sidecar after a crash is read as "free" once the lock probe says so.

Imports nothing heavy: the CLI takes the lock before it loads anything else."""
import json
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from . import settings

HELD_ENV = "DW_JOB_LOCK_HELD"
WAIT_NOTE = ("Another job holds the job lock ({path}): a scheduled job or another command. "
             "Waiting for it to finish.")
POLL_SECONDS = 0.25

_thread = threading.RLock()
_depth = 0
_owner: int | None = None
_fd: int | None = None


def path():
    return settings.DATA_DIR / "jobs.lock"


def holder_path():
    return settings.DATA_DIR / "jobs.lock.holder"


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


def _wait_lock(fd: int, deadline: float | None = None) -> bool:
    """Wait for the file lock. With a deadline (time.monotonic()), polls and gives up at it."""
    if os.name != "nt" and deadline is None:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX)
        return True
    while not _try_lock(fd):
        if deadline is not None and time.monotonic() >= deadline:
            return False
        time.sleep(POLL_SECONDS)
    return True


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


def _write_holder(job: str | None) -> None:
    try:
        holder_path().write_text(json.dumps({"pid": os.getpid(), "job": job,
                                             "since": datetime.now(timezone.utc).isoformat(timespec="seconds")}),
                                 encoding="utf-8")
    except OSError:
        pass


def _remove_holder() -> None:
    try:
        holder_path().unlink()
    except OSError:
        pass


def is_held() -> bool:
    """Whether this thread holds the job lock (so a child it starts must not take it)."""
    return _depth > 0 and _owner == threading.get_ident()


def acquire(timeout: float | None = None, note=None, job: str | None = None) -> bool:
    """Take the job lock. Re-entrant within a thread. `timeout` in seconds (None waits for as long as it
    takes); returns False when it ran out. `note(text)` is called once if another process holds the
    lock and we have to wait. `job` names the holder in the sidecar."""
    global _depth, _owner, _fd
    deadline = None if timeout is None else time.monotonic() + timeout
    if not _thread.acquire(timeout=-1 if timeout is None else timeout):
        return False
    try:
        if _depth == 0 and not os.environ.get(HELD_ENV):
            fd = _open()
            if not _try_lock(fd):
                if note:
                    note(WAIT_NOTE.format(path=path()))
                try:
                    if not _wait_lock(fd, deadline):
                        os.close(fd)
                        _thread.release()
                        return False
                except BaseException:
                    os.close(fd)
                    raise
            _fd = fd
            _write_holder(job)
        if _depth == 0:
            _owner = threading.get_ident()
        _depth += 1
        return True
    except BaseException:
        _thread.release()
        raise


def release() -> None:
    global _depth, _owner, _fd
    _depth -= 1
    if _depth == 0:
        _owner = None
        if _fd is not None:
            fd, _fd = _fd, None
            _remove_holder()
            _unlock(fd)
    _thread.release()


@contextmanager
def held(note=None, job: str | None = None):
    """Hold the job lock for the block. `note(text)` is called once if another process holds it and
    we have to wait."""
    acquire(note=note, job=job)
    try:
        yield
    finally:
        release()


class JobLock:
    """The job lock as an object with acquire(timeout)/release(), for code written against
    threading.Lock (the AI audit's short writes). A failed acquire leaves nothing to release."""

    def __init__(self, job: str):
        self.job = job

    def acquire(self, timeout: float | None = None) -> bool:
        return acquire(timeout=timeout, job=self.job)

    def release(self) -> None:
        release()


def holder() -> dict | None:
    """Who holds the lock now: {"pid", "job", "since"} (fields None when the sidecar is missing or
    unreadable), or None when the lock is free. Probes the lock itself: a second descriptor is refused
    while any process, this one included, holds it."""
    if is_held():
        info = _read_holder()
        return {"pid": os.getpid(), "job": None, "since": None} | (info or {})
    try:
        fd = _open()
    except OSError:
        return None
    if _try_lock(fd):
        _unlock(fd)
        return None
    os.close(fd)
    return {"pid": None, "job": None, "since": None} | (_read_holder() or {})


def _read_holder() -> dict | None:
    try:
        info = json.loads(holder_path().read_text(encoding="utf-8"))
        return info if isinstance(info, dict) else None
    except (OSError, ValueError):
        return None
