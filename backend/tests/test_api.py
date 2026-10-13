from datetime import date, datetime

from sqlalchemy import select

from app.models import Event, Item, Label, Outlet, OutletCategory
from tests.conftest import ids, login


def test_requires_login(client):
    assert client.get("/api/meta").status_code == 401


def test_invite_flow(client, users):
    login(client, "admin@example.org", "admin-password-1")
    r = client.post("/api/admin/invites", json={"email": "new@example.org"})
    token = r.json()["invite_path"].split("/")[-1]
    client.post("/api/auth/logout")
    r = client.post("/api/auth/accept-invite", json={"token": token, "password": "short", "display_name": "N"})
    assert r.status_code == 400
    r = client.post("/api/auth/accept-invite", json={"token": token, "password": "long-enough-pw", "display_name": "N"})
    assert r.status_code == 200 and r.json()["role"] == "journalist"
    assert client.post("/api/auth/accept-invite", json={"token": token, "password": "long-enough-pw",
                                                        "display_name": "N"}).status_code == 400


def test_journalist_cannot_admin(client, users):
    login(client, "j@example.org", "journo-password-1")
    assert client.post("/api/admin/invites", json={"email": "x@example.org"}).status_code == 403


def test_vote_and_labels(client, users, db):
    themes, regions = ids(db)
    login(client, "j@example.org", "journo-password-1")
    body = {"theme_id": themes["health"], "region_id": regions["fezzan"], "week": "2026-10-05", "lens": "events",
            "vote": "real", "note": "Nobody has been to Ubari hospital"}
    assert client.post("/api/gap/vote", json=body).status_code == 200
    body["vote"] = "not_newsworthy"
    assert client.post("/api/gap/vote", json=body).status_code == 200  # upsert, one vote per user/gap/week
    assert client.post("/api/gap/vote", json={**body, "vote": "covered"}).status_code == 400  # needs link
    from app.learning import build_labels
    assert build_labels(db) >= 1
    assert build_labels(db) == 0  # idempotent
    lab = db.scalars(select(Label).where(Label.label_type == "gap_real")).all()
    assert lab[-1].value["vote"] == "not_newsworthy"


def test_opt_out_drops_implicit_events(client, users, db):
    login(client, "j@example.org", "journo-password-1")
    evs = [{"type": "impression", "object_type": "gap", "object_key": "1:1", "context": {"position": 3}},
           {"type": "dwell", "object_type": "gap", "object_key": "1:1", "context": {"seconds": 30}},
           {"type": "evil", "object_key": "x"}]
    assert client.post("/api/events", json={"events": evs}).json()["stored"] == 2
    client.patch("/api/me", json={"tracking_opt_out": True})
    assert client.post("/api/events", json={"events": evs}).json()["stored"] == 0
    assert client.post("/api/events", json={"events": [{"type": "comment"}]}).json()["stored"] == 1


def test_correction_and_comment(client, users, db):
    themes, regions = ids(db)
    from app.ingest import load_rules, store_article
    country_id = db.scalar(select(Outlet.country_id).limit(1))
    it, _ = store_article(db, country_id, load_rules(db, country_id), url="https://ex.org/a",
                          title="Oil workers strike in Brega", published_at=datetime(2026, 10, 1), source_key="test")
    db.commit()
    login(client, "j@example.org", "journo-password-1")
    r = client.post(f"/api/items/{it.id}/correction", json={"theme_id": themes["economy"], "theme_relevant": False})
    assert themes["economy"] not in r.json()["theme_ids"]
    r = client.post(f"/api/items/{it.id}/correction", json={"region_id": regions["al_wahat"], "region_relevant": True})
    assert regions["al_wahat"] in r.json()["region_ids"]
    assert db.scalar(select(Event).where(Event.type == "correction")) is not None
    c = client.post("/api/comments", json={"object_type": "item", "object_key": str(it.id), "body": "@Admin see this"})
    assert c.json()["mentions"] == ["Admin"]
    reply = client.post("/api/comments", json={"object_type": "item", "object_key": str(it.id), "body": "ok",
                                               "parent_id": c.json()["id"]})
    assert reply.status_code == 200
    assert len(client.get(f"/api/comments?object_type=item&object_key={it.id}").json()) == 2
    r = client.post(f"/api/items/{it.id}/assessment", json={"accuracy": 3, "depth": 2, "local_sourcing": 1})
    assert r.status_code == 200
    assert client.get(f"/api/items/{it.id}").json()["assessments"]["mine"]["accuracy"] == 3


def test_category_requires_evidence_and_keeps_history(client, users, db):
    o = db.scalar(select(Outlet).where(Outlet.domain == "libyaherald.com"))
    login(client, "j@example.org", "journo-password-1")
    bad = {"dimension": "alignment", "value": "independent", "confidence": "reported", "evidence_url": "trust me"}
    assert client.post(f"/api/outlets/{o.id}/categories", json=bad).status_code in (400, 422)
    good = {**bad, "evidence_url": "https://example.org/media-landscape-study"}
    assert client.post(f"/api/outlets/{o.id}/categories", json=good).json()["status"] == "proposed"
    client.post("/api/auth/logout")
    login(client, "admin@example.org", "admin-password-1")
    pid = db.scalar(select(OutletCategory.id).where(OutletCategory.status == "proposed"))
    assert client.post(f"/api/outlets/categories/{pid}/review", json={"approve": True}).status_code == 200
    newer = {**good, "value": "tripoli_gnu_aligned", "confidence": "disputed"}
    assert client.post(f"/api/outlets/{o.id}/categories", json=newer).json()["status"] == "active"
    db.expire_all()
    hist = [c for c in client.get(f"/api/outlets/{o.id}/history").json() if c["dimension"] == "alignment"]
    assert len(hist) == 2 and sum(1 for c in hist if c["valid_to"] is None) == 1


def test_delete_account(client, users, db):
    login(client, "j@example.org", "journo-password-1")
    client.post("/api/events", json={"events": [{"type": "click", "object_key": "x"}]})
    assert client.delete("/api/me").status_code == 200
    assert client.get("/api/me").status_code == 401
    assert db.scalar(select(Event)) is None
