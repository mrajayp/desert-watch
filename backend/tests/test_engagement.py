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
