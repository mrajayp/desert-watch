from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str | None = None):
    url = url or settings.DATABASE_URL
    if url.startswith("sqlite:///"):
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _pragmas(conn, _):
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=10000")
            cur.close()
    return engine


def _swap_in_uploaded_db():
    """Boot-time data load: if `incoming.db.gz` was uploaded to the data dir (fly ssh sftp),
    replace the database with it before anything connects, then delete the upload."""
    import gzip
    import logging
    import os
    import shutil
    src = settings.DATA_DIR / "incoming.db.gz"
    if not src.exists() or not settings.DATABASE_URL.startswith("sqlite:///"):
        return
    target = settings.DATABASE_URL.removeprefix("sqlite:///")
    tmp = target + ".incoming"
    with gzip.open(src, "rb") as fin, open(tmp, "wb") as fout:
        shutil.copyfileobj(fin, fout)
    for suffix in ("-wal", "-shm"):
        if os.path.exists(target + suffix):
            os.remove(target + suffix)
    os.replace(tmp, target)
    os.remove(src)
    logging.getLogger("desert_watch").warning("Loaded uploaded database from %s", src)


_swap_in_uploaded_db()
engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


# Additive columns added after first release: create_all() does not alter existing tables.
ADDED_COLUMNS = {
    "theme": {"group": "VARCHAR(40)", "cooc": "JSON", "strict": "BOOLEAN DEFAULT 0", "require_country": "BOOLEAN DEFAULT 0",
              "veto": "JSON", "mask": "JSON"},
    "outlet": {"monitored": "BOOLEAN DEFAULT 1", "external": "JSON"},
    "item": {"duplicate_of": "INTEGER"},
    "item_theme": {"evidence": "JSON", "score": "FLOAT", "model_version": "VARCHAR(40)"},
    "user": {"status": "VARCHAR(10) DEFAULT 'active'", "organisation": "VARCHAR(200)", "signup_note": "TEXT",
             "approved_by": "INTEGER"},
}


def init_db(bind=None):
    from sqlalchemy import inspect, text
    from . import models  # noqa: F401  (register tables)
    eng = bind or engine
    Base.metadata.create_all(eng)
    insp = inspect(eng)
    with eng.begin() as conn:
        for table, cols in ADDED_COLUMNS.items():
            have = {c["name"] for c in insp.get_columns(table)}
            for col, ddl in cols.items():
                if col not in have:
                    conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{col}" {ddl}'))


@contextmanager
def session_scope():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
