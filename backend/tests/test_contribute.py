from datetime import timedelta

from sqlalchemy import select

from app.ingest import load_rules, store_article
from app.models import Country, utcnow

from .conftest import login


def test_contribute_queues_and_tally(client, users, db):
    c = db.scalar(select(Country))
    rules = load_rules(db, c.id)
    when = utcnow() - timedelta(days=1)
    # no theme -> "untagged"; theme but no place -> "unplaced"
    store_article(db, c.id, rules, url="https://ex.ly/u1", title="خبر عام من ليبيا", published_at=when, source_key="rss")
    store_article(db, c.id, rules, url="https://ex.ly/u2", title="Libya hospital shortage of medicines",
                  published_at=when, source_key="rss")
    db.commit()
    login(client, "j@example.org", "journo-password-1")
    d = client.get("/api/contribute").json()
    assert d["can_contribute"] is True
    assert d["untagged"]["total"] >= 1 and d["unplaced"]["total"] >= 1
    assert d["mine"]["suggestions"] == 0
    r = client.post("/api/suggestions", json={"kind": "source", "payload": {"url": "https://example.ly", "note": "local radio"}})
    assert r.status_code == 200
    d = client.get("/api/contribute").json()
    assert d["mine"]["suggestions"] == 1 and d["my_suggestions"][0]["kind"] == "source"


def test_methods_page_is_admin_only(client, users):
    login(client, "j@example.org", "journo-password-1")
    assert client.get("/api/admin/methods").status_code == 403
    client.post("/api/auth/logout")
    login(client, "admin@example.org", "admin-password-1")
    md = client.get("/api/admin/methods").json()["markdown"]
    assert md.startswith("# How the numbers work") and "gap score" in md
