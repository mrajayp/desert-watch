"""The nightly off-site backup of the SQLite database (01:15 UTC, jobs.backup).

VACUUM INTO writes a compact, consistent copy next to the database (under the job lock, so no job
writes meanwhile), PRAGMA quick_check reads the copy back, the copy is gzipped as a stream, the
gzip is uploaded to an S3-compatible bucket (s3put.py) under backups/desert_watch_<day>.db.gz, and
only after a successful upload are older copies pruned to 7 daily, 4 weekly and 3 monthly.

The bucket comes from the environment (settings.AWS_* and BUCKET_NAME, the names Fly's Tigris
integration sets). Until they exist the run is recorded as awaiting_key, like a collector without
its key. The restore path is the existing incoming.db.gz boot hook (db.py, docs/DEPLOY.md)."""
import gzip
import hashlib
import re
import shutil
import sqlite3
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from . import joblock, settings
from .collectors.base import AwaitingKey, RunResult
from .s3put import S3

NAME = re.compile(r"desert_watch_(\d{4}-\d{2}-\d{2})\.db\.gz$")
CHUNK = 1 << 20
AWAITING = ("Set the bucket secrets AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_ENDPOINT_URL_S3 and BUCKET_NAME "
            "(fly storage create writes them) to start the nightly backup.")


def db_path() -> Path:
    if not settings.DATABASE_URL.startswith("sqlite:///"):
        raise RuntimeError("backups are written for the SQLite database only")
    return Path(settings.DATABASE_URL.removeprefix("sqlite:///"))


def snapshot(src: Path, dest: Path) -> None:
    """A compact, consistent copy of the live database (VACUUM INTO), then quick_check on the copy."""
    con = sqlite3.connect(str(src))
    try:
        con.execute("VACUUM INTO ?", (str(dest),))
    finally:
        con.close()
    copy = sqlite3.connect(str(dest))
    try:
        verdict = copy.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        copy.close()
    if verdict != "ok":
        raise RuntimeError(f"quick_check on the copy said: {verdict}")


def compress(src: Path, dest: Path) -> tuple[int, str]:
    """Stream-gzip src into dest. Returns the gzip's size and its SHA-256 (hex)."""
    with open(src, "rb") as fin, gzip.open(dest, "wb", compresslevel=6) as fout:
        shutil.copyfileobj(fin, fout, CHUNK)
    h = hashlib.sha256()
    with open(dest, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return dest.stat().st_size, h.hexdigest()


def chunks(path: Path):
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            yield chunk


def key_for(day: date, prefix: str | None = None) -> str:
    return f"{settings.BACKUP_PREFIX if prefix is None else prefix}desert_watch_{day.isoformat()}.db.gz"


def day_of(key: str) -> date | None:
    m = NAME.search(key)
    return date.fromisoformat(m.group(1)) if m else None


def keep_dates(days, daily: int = 7, weekly: int = 4, monthly: int = 3) -> set[date]:
    """Which copies to keep: the newest `daily`, the newest copy of each of the newest `weekly` ISO
    weeks that have one, and the newest copy of each of the newest `monthly` months that have one."""
    ds = sorted(set(days), reverse=True)
    keep = set(ds[:daily])
    weeks, months = {}, {}
    for d in ds:   # newest first: the first date seen per week or month is its newest
        weeks.setdefault(d.isocalendar()[:2], d)
        months.setdefault((d.year, d.month), d)
    keep.update(list(weeks.values())[:weekly])
    keep.update(list(months.values())[:monthly])
    return keep


def prune(s3: S3, prefix: str | None = None, keep: dict | None = None) -> list[str]:
    """Delete the dated copies under the prefix that the retention does not keep. Other objects are
    never touched. Returns the keys deleted."""
    prefix = settings.BACKUP_PREFIX if prefix is None else prefix
    keep = keep or settings.BACKUP_KEEP
    dated = {o["key"]: day_of(o["key"]) for o in s3.list(prefix)}
    dated = {k: d for k, d in dated.items() if d}
    wanted = keep_dates(dated.values(), keep["daily"], keep["weekly"], keep["monthly"])
    gone = sorted(k for k, d in dated.items() if d not in wanted)
    for k in gone:
        s3.delete(k)
    return gone


def run(s: Session, today: date | None = None, s3: S3 | None = None) -> RunResult:
    """One backup: copy under the job lock, compress and upload outside it, then prune. Raises
    AwaitingKey while the bucket's secrets are missing."""
    s3 = s3 or S3.from_settings()
    if s3 is None:
        raise AwaitingKey(AWAITING)
    today = today or datetime.now(timezone.utc).date()
    src = db_path()
    work = Path(tempfile.mkdtemp(prefix="backup-", dir=settings.DATA_DIR))
    try:
        raw, gz = work / "copy.db", work / "copy.db.gz"
        with joblock.held(job="backup"):
            snapshot(src, raw)
        size, digest = compress(raw, gz)
        raw.unlink()
        key = key_for(today)
        s3.put(key, chunks(gz), size, digest, content_type="application/gzip")
        gone = prune(s3)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return RunResult(rows=1, detail=f"{key} ({size / 1e6:.1f} MB uploaded), {len(gone)} older copies pruned")
