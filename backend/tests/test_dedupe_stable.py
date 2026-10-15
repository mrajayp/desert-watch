from datetime import date, datetime, timedelta

from sqlalchemy import select

from app.dedupe import mark_duplicates
from app.ingest import load_rules, store_article
from app.models import CellWeek, Item, Outlet
from app.scoring import compute, week_start
from tests.conftest import ids, login
from tests.test_scoring import _pageviews


def test_same_story_from_google_news_and_feed_counts_once(client, users, db):
    country_id = db.scalar(select(Outlet.country_id).limit(1))
    rules = load_rules(db, country_id)
    t = datetime(2026, 10, 6, 9)
    # Google News link and the outlet's own feed: same outlet (domain), same day, same headline
    g, _ = store_article(db, country_id, rules, url="https://news.google.com/rss/articles/abc", outlet_domain="alwasat.ly",
                         title="انقطاع الكهرباء في سبها لساعات طويلة - الوسط", published_at=t, source_key="gnews")
    r, _ = store_article(db, country_id, rules, url="https://alwasat.ly/news/1", title="انقطاع الكهرباء في سبها لساعات طويلة",
                         published_at=t + timedelta(hours=20), source_key="rss")
    other, _ = store_article(db, country_id, rules, url="https://alwasat.ly/news/2", title="المصرف المركزي يعلن سعر صرف الدينار",
                             published_at=t, source_key="rss")
    elsewhere, _ = store_article(db, country_id, rules, url="https://libyaobserver.ly/x", title="انقطاع الكهرباء في سبها لساعات طويلة",
                                 published_at=t, source_key="rss")
    db.commit()
    assert mark_duplicates(db) == 1
    db.refresh(g)
    assert g.duplicate_of == r.id                       # the Google copy points at the outlet's own link
    assert other.duplicate_of is None and elsewhere.duplicate_of is None  # different story / different outlet
    assert mark_duplicates(db) == 0                     # idempotent
    login(client, "admin@example.org", "admin-password-1")
    urls = {x["url"] for x in client.get("/api/items", params={"start": "2026-10-01", "end": "2026-10-12"}).json()["items"]}
    assert "https://news.google.com/rss/articles/abc" not in urls and "https://alwasat.ly/news/1" in urls


def test_audience_gap_ignores_a_newly_added_source(db):
    """Steady interest and steady coverage from one source; a new source starts in the last two
    weeks. The gap must not swing negative just because we started collecting more."""
    themes, regions = ids(db)
    country_id = db.scalar(select(Outlet.country_id).limit(1))
    rules = load_rules(db, country_id)
    today = date(2026, 10, 12)
    for w in range(28):
        day = datetime.combine(week_start(today) - timedelta(weeks=w), datetime.min.time())
        _pageviews(db, country_id, themes["health"], day.date(), 2000)
        for k in range(5):
            store_article(db, country_id, rules, url=f"https://ex.com/s/{w}/{k}", title="Hospital shortages in Sabha",
                          published_at=day, source_key="rss")
        if w < 2:   # a new collector starts two weeks ago and adds lots of articles
            for k in range(30):
                store_article(db, country_id, rules, url=f"https://new.com/n/{w}/{k}", title=f"Hospital medicines shortage Libya {k}",
                              published_at=day, source_key="galerts")
    db.commit()
    compute(db, country_id, weeks=4, today=today)
    last = db.scalar(select(CellWeek).where(CellWeek.theme_id == themes["health"], CellWeek.region_id == regions["national"],
                                            CellWeek.lens == "audience", CellWeek.week_start == week_start(today)))
    assert last.coverage > last.breakdown["scored_coverage"]       # shown coverage includes the new source
    assert last.breakdown["scored_sources"] == ["rss"]
    assert last.gap is not None and abs(last.gap) < 0.3              # ... but the score does not swing
    assert "coverage_drop" not in last.flags


def test_source_ending_is_not_a_coverage_drop(db):
    """A one-off source (the backfill) stops; steady sources carry on. No 'coverage dropped' flag."""
    themes, regions = ids(db)
    country_id = db.scalar(select(Outlet.country_id).limit(1))
    rules = load_rules(db, country_id)
    today = date(2026, 10, 12)
    for w in range(20):
        day = datetime.combine(week_start(today) - timedelta(weeks=w), datetime.min.time())
        _pageviews(db, country_id, themes["health"], day.date(), 2000)
        for k in range(4):
            store_article(db, country_id, rules, url=f"https://ex.com/f/{w}/{k}", title="Hospital shortages in Sabha",
                          published_at=day, source_key="rss")
        if w >= 5:
            for k in range(20):
                store_article(db, country_id, rules, url=f"https://bf.com/b/{w}/{k}", title=f"Hospital medicines shortage Libya {k}",
                              published_at=day, source_key="backfill")
    db.commit()
    compute(db, country_id, weeks=2, today=today)
    last = db.scalar(select(CellWeek).where(CellWeek.theme_id == themes["health"], CellWeek.region_id == regions["national"],
                                            CellWeek.lens == "audience", CellWeek.week_start == week_start(today)))
    assert "coverage_drop" not in last.flags
    assert last.gap is not None and abs(last.gap) < 0.3


def test_backfill_density_does_not_move_the_gap(db):
    """Steady interest and steady feed coverage; the backfill triples in the last month (the review
    cited more). The audience gap must stay put."""
    themes, regions = ids(db)
    country_id = db.scalar(select(Outlet.country_id).limit(1))
    rules = load_rules(db, country_id)
    today = date(2026, 10, 12)
    for w in range(24):
        day = datetime.combine(week_start(today) - timedelta(weeks=w), datetime.min.time())
        _pageviews(db, country_id, themes["health"], day.date(), 2000)
        for k in range(5):
            store_article(db, country_id, rules, url=f"https://ex.com/d/{w}/{k}", title="Hospital shortages in Sabha",
                          published_at=day, source_key="rss")
        for k in range(15 if w < 4 else 5):
            store_article(db, country_id, rules, url=f"https://bf.com/d/{w}/{k}", title=f"Hospital medicines shortage Libya {k}",
                          published_at=day, source_key="backfill")
    db.commit()
    compute(db, country_id, weeks=2, today=today)
    last = db.scalar(select(CellWeek).where(CellWeek.theme_id == themes["health"], CellWeek.region_id == regions["national"],
                                            CellWeek.lens == "audience", CellWeek.week_start == week_start(today)))
    assert last.breakdown["scored_sources"] == ["rss"]
    assert abs(last.gap) < 0.3


def test_new_outlets_inside_an_existing_source_do_not_move_the_gap(db):
    """Same collector ('rss'), but 25 new outlet feeds start two weeks ago."""
    themes, regions = ids(db)
    country_id = db.scalar(select(Outlet.country_id).limit(1))
    rules = load_rules(db, country_id)
    today = date(2026, 10, 12)
    for w in range(24):
        day = datetime.combine(week_start(today) - timedelta(weeks=w), datetime.min.time())
        _pageviews(db, country_id, themes["health"], day.date(), 2000)
        for k in range(5):
            store_article(db, country_id, rules, url=f"https://old.ly/o/{w}/{k}", title="Hospital shortages in Sabha",
                          published_at=day, source_key="rss")
        if w < 2:
            for k in range(25):
                store_article(db, country_id, rules, url=f"https://new{k}.ly/n/{w}", title=f"Hospital medicines shortage Libya {k}",
                              published_at=day, source_key="rss")
    db.commit()
    compute(db, country_id, weeks=2, today=today)
    last = db.scalar(select(CellWeek).where(CellWeek.theme_id == themes["health"], CellWeek.region_id == regions["national"],
                                            CellWeek.lens == "audience", CellWeek.week_start == week_start(today)))
    assert last.coverage > 3 * last.breakdown["scored_coverage"] and last.breakdown["scored_outlets"] == 1
    assert abs(last.gap) < 0.3


def test_trends_api_counts_only_outlets_present_all_year(client, users, db):
    themes, regions = ids(db)
    country_id = db.scalar(select(Outlet.country_id).limit(1))
    rules = load_rules(db, country_id)
    today = date(2026, 10, 12)
    for w in range(60):
        day = datetime.combine(week_start(today) - timedelta(weeks=w), datetime.min.time())
        _pageviews(db, country_id, themes["health"], day.date(), 2000)
        store_article(db, country_id, rules, url=f"https://old.ly/t/{w}", title="Hospital shortages in Sabha",
                      published_at=day, source_key="rss")
        if w < 3:
            for k in range(10):
                store_article(db, country_id, rules, url=f"https://new{k}.ly/t/{w}", title=f"Hospital medicines shortage Libya {k}",
                              published_at=day, source_key="rss")
    db.commit()
    compute(db, country_id, weeks=56, today=today)
    login(client, "admin@example.org", "admin-password-1")
    r = client.get("/api/cells/trends", params={"lens": "audience"}).json()
    rows = [x for x in r["series"][str(themes["health"])] if "trend_coverage" in x]
    assert r["trend_basis"]["outlets"] == 1
    assert rows[-1]["coverage"] > rows[-1]["trend_coverage"] == 4    # 4 weeks x 1 steady article
