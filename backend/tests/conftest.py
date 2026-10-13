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
