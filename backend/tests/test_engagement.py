from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from app.ingest import load_rules, store_article
from app.models import ItemEngagement, NetworkEdgeWeek, Outlet
from app.network import compute, find_syndication, story_pickup

T0 = datetime(2026, 10, 6, 8)
STORY = "Clashes erupt in Zawiya between rival armed groups, residents say"


def test_find_syndication_returns_stories():
    items = [
        (1, 10, T0, STORY),
        (2, 11, T0 + timedelta(hours=3), STORY),
        (3, 12, T0 + timedelta(hours=30), STORY + "."),
        (4, 10, T0 + timedelta(hours=5), STORY),                      # same outlet again
        (5, 13, T0 + timedelta(hours=80), STORY),                     # outside the 48 h window of all others
        (6, 14, T0, "Central bank announces new dinar exchange rate"),
    ]
    pairs, stories = find_syndication(items, clusters=True)
    assert pairs == find_syndication(items)                           # old call unchanged
    by_item = {i: sorted(m) for m in stories for i in m}
    assert by_item[1] == [1, 2, 3, 4] and by_item[5] == [5] and by_item[6] == [6]
    pick = story_pickup(items, stories)
    assert pick[1]["total"] == 3 and pick[4]["total"] == 3            # outlets 10, 11, 12
    assert pick[5]["total"] == 1 and pick[6] == {"total": 1.0, "raw": {}}
    assert pick[2]["raw"]["story"] == 1


def _store(db, cid, rules, url, title, when):
    item, _ = store_article(db, cid, rules, url=url, title=title, published_at=when, source_key="rss",
                            forced_theme_ids=(1,))
    return item


def test_compute_writes_pickup_and_skips_shorteners(db):
    cid = db.scalar(select(Outlet.country_id).limit(1))
    rules = load_rules(db, cid)
    title = "Libya: " + STORY
    a = _store(db, cid, rules, "https://a.ly/1", title, T0)
    b = _store(db, cid, rules, "https://b.ly/1", title, T0 + timedelta(hours=2))
    t = _store(db, cid, rules, "https://t.co/xyz", title, T0 + timedelta(hours=1))
    lone = _store(db, cid, rules, "https://c.ly/1", "Libya: hospital in Derna short of medicines", T0)
    db.commit()
    compute(db, cid, weeks=2, today=date(2026, 10, 12))
    got = {r.item_id: r for r in db.scalars(select(ItemEngagement).where(ItemEngagement.source == "pickup"))}
    assert got[a.id].total == 2 and got[b.id].total == 2 and got[a.id].age_bucket == "now"
    assert got[lone.id].total == 1
    assert t.id not in got                                            # t.co is not an outlet
    tco = db.scalar(select(Outlet.id).where(Outlet.domain == "t.co"))
    syn = db.scalars(select(NetworkEdgeWeek).where(NetworkEdgeWeek.kind == "syndication")).all()
    assert syn and all(f"o:{tco}" not in (e.source_node, e.target_node) for e in syn)

    # a third outlet picks the story up: the reading is updated in place, never duplicated
    first_measured = got[lone.id].measured_at
    _store(db, cid, rules, "https://d.ly/1", title, T0 + timedelta(hours=20))
    db.commit()
    compute(db, cid, weeks=2, today=date(2026, 10, 12))
    db.expire_all()
    rows = db.scalars(select(ItemEngagement).where(ItemEngagement.source == "pickup")).all()
    assert len(rows) == len({r.item_id for r in rows}) == 4
    assert {r.item_id: r.total for r in rows}[a.id] == 3
    assert {r.item_id: r for r in rows}[lone.id].measured_at == first_measured   # unchanged rows not rewritten


def test_items_api_engagement_sort_and_outlet_reach(client, users, db):
    from app.models import utcnow
    from tests.conftest import login
    cid = db.scalar(select(Outlet.country_id).limit(1))
    rules = load_rules(db, cid)
    now = utcnow()
    a = _store(db, cid, rules, "https://a.ly/2", "Libya: " + STORY, now - timedelta(days=3))
    b = _store(db, cid, rules, "https://b.ly/2", "Libya: hospital in Derna short of medicines", now - timedelta(days=1))
    c = _store(db, cid, rules, "https://c.ly/2", "Libya: water cuts across Sabha", now - timedelta(days=2))
    db.add_all([ItemEngagement(item_id=a.id, source="pickup", age_bucket="now", total=4),
                ItemEngagement(item_id=b.id, source="pickup", age_bucket="now", total=1),
                ItemEngagement(item_id=a.id, source="fb_url", age_bucket="48h", reactions=5, comments=1, shares=0, total=6),
                ItemEngagement(item_id=a.id, source="fb_url", age_bucket="7d", reactions=900, comments=200, shares=100,
                               total=1200)])
    outlet = db.get(Outlet, a.outlet_id)
    outlet.external = {"reach": {"tranco": {"value": 174512, "as_of": "2026-10-15", "method": "tranco-list.eu api",
                                            "history": []}},
                       "social_media_scrape": {"source": "Social Media scraped data", "articles": 790,
                                               "fb_posts": 1974, "fb_engagement": 6565,
                                               "period": {"from": "2023-10-01", "to": "2024-08-10"}}}
    db.commit()
    login(client, "j@example.org", "journo-password-1")

    items = {i["id"]: i for i in client.get("/api/items", params={"days": 10}).json()["items"]}
    assert items[a.id]["engagement"]["pickup"] == 4
    fb = items[a.id]["engagement"]["fb"]
    assert (fb["total"], fb["reactions"], fb["comments"], fb["shares"], fb["age_bucket"]) == (1200, 900, 200, 100, "7d")
    assert items[c.id]["engagement"] == {"pickup": None, "fb": None}

    newest = [i["id"] for i in client.get("/api/items", params={"days": 10}).json()["items"]]
    picked = [i["id"] for i in client.get("/api/items", params={"days": 10, "sort": "pickup"}).json()["items"]]
    assert newest.index(b.id) < newest.index(c.id) < newest.index(a.id)
    assert picked.index(a.id) < picked.index(b.id) < picked.index(c.id)   # 4 outlets, 1 outlet, no reading

    r = client.get(f"/api/outlets/{a.outlet_id}/reach").json()
    assert r["tranco"]["value"] == 174512 and r["tranco"]["as_of"] == "2026-10-15"
    h = r["facebook_historical"]
    assert h["historical"] is True and h["per_article"] == 8.3 and h["period"]["to"] == "2024-08-10"
    assert r["facebook_recent"] is None                                  # fewer than 20 readings
    assert client.get("/api/outlets/999999/reach").status_code == 404
