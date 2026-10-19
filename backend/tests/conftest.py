import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="dw-test-"))
os.environ["DW_DATABASE_URL"] = f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["DW_DATA_DIR"] = str(_tmp)
os.environ["DW_SCHEDULER"] = "0"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db import Base, SessionLocal, engine, init_db  # noqa: E402
from app.seed import seed_all  # noqa: E402


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    init_db()
    with SessionLocal() as s:
        seed_all(s)
        s.commit()
        yield s


@pytest.fixture()
def client(db):
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def users(db):
    from app.auth import create_user
    admin = create_user(db, "admin@example.org", "admin-password-1", "Admin", "admin")
    j = create_user(db, "j@example.org", "journo-password-1", "Journo")
    db.commit()
    return admin, j


def login(client, email, pw):
    r = client.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r


def ids(db):
    from app.models import Region, Theme
    themes = {t.slug: t.id for t in db.scalars(select(Theme))}
    regions = {r.slug: r.id for r in db.scalars(select(Region))}
    return themes, regions


def offer_lens(db, week, lens="audience", weeks=4):
    """Make a lens one the site offers (api.gaps.available_lenses): a judged national cell on every active
    theme for the `weeks` weeks before `week`, where none exists. The digest and the Contribute gap list
    report gaps only on offered lenses, and one judged theme is not a lens."""
    from datetime import timedelta
    from app.models import CellWeek, Country, Region, Theme
    c = db.scalar(select(Country))
    nat = db.scalar(select(Region.id).where(Region.country_id == c.id, Region.level == "national"))
    have = {(x.theme_id, x.week_start): x for x in db.scalars(select(CellWeek).where(CellWeek.lens == lens, CellWeek.region_id == nat))}
    for tid in db.scalars(select(Theme.id).where(Theme.active.is_(True))):
        for w in range(1, weeks + 1):
            cell = have.get((tid, week - timedelta(weeks=w)))
            if cell is None:
                db.add(CellWeek(country_id=c.id, theme_id=tid, region_id=nat, week_start=week - timedelta(weeks=w), lens=lens,
                                need=100, coverage=50, gap=0.0, insufficient=False, flags=[], verdict="usual", breakdown={}))
            elif cell.insufficient:   # a cell a recompute wrote as "not judged" (no need data): judged now
                cell.insufficient, cell.gap, cell.verdict = False, 0.0, "usual"
                cell.breakdown = {k: v for k, v in (cell.breakdown or {}).items() if k not in ("in_progress", "reason")}
    db.commit()
