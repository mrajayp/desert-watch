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


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


# Additive columns added after first release: create_all() does not alter existing tables.
ADDED_COLUMNS = {"theme": {"group": "VARCHAR(40)", "cooc": "JSON", "strict": "BOOLEAN DEFAULT 0", "require_country": "BOOLEAN DEFAULT 0"}}


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
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN "{col}" {ddl}'))


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
