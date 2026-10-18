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
    compute(db, country_id, weeks=5, today=today + timedelta(days=7))   # the week of `today` is complete
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
    compute(db, country_id, weeks=3, today=today + timedelta(days=7))
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
    compute(db, country_id, weeks=3, today=today + timedelta(days=7))
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
    compute(db, country_id, weeks=3, today=today + timedelta(days=7))
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
    rows = r["themes"][str(themes["health"])]["rows"]
    assert r["basis"]["outlets"] == 1 and "series" not in r and "trend_basis" not in r
    assert rows[-1]["in_progress"] and rows[-1]["articles_all"] == 11 and rows[-1]["articles"] == 1
    assert rows[-2]["articles_all"] == 11 and rows[-2]["articles_4w"] == 4   # 4 weeks x 1 steady article


VARY = ("worsen", "ease", "persist", "return", "spread", "continue", "deepen")   # a new headline each week


def _two_routes(db, today, feed_weeks=3):
    """Two outlets found by Google News every week all year. One of them gets a feed `feed_weeks` weeks
    ago that catches every story from then on, so each of its recent stories reaches us twice: the feed
    copy is kept and the Google News copy becomes the duplicate."""
    themes, regions = ids(db)
    country_id = db.scalar(select(Outlet.country_id).limit(1))
    rules = load_rules(db, country_id)
    for w in range(60):
        day = datetime.combine(week_start(today) - timedelta(weeks=w), datetime.min.time()) + timedelta(hours=9)
        _pageviews(db, country_id, themes["health"], day.date(), 2000)
        store_article(db, country_id, rules, url=f"https://news.google.com/rss/articles/obs{w}", outlet_domain="libyaobserver.ly",
                      title=f"Sabha hospital medicine shortages {VARY[w % 7]}", published_at=day, source_key="gnews")
        store_article(db, country_id, rules, url=f"https://news.google.com/rss/articles/was{w}", outlet_domain="alwasat.ly",
                      title=f"Hospital shortages in Sabha leave patients waiting as they {VARY[w % 7]} - الوسط",
                      published_at=day, source_key="gnews")
        if w < feed_weeks:
            store_article(db, country_id, rules, url=f"https://alwasat.ly/news/{w}",
                          title=f"Hospital shortages in Sabha leave patients waiting as they {VARY[w % 7]}",
                          published_at=day + timedelta(hours=2), source_key="rss")
    db.commit()
    assert mark_duplicates(db) == feed_weeks
    return themes, regions, country_id


def test_story_found_by_two_routes_counts_once_and_keeps_the_gnews_pair_in_the_basis(client, users, db):
    """A1: the feed copy is kept but its pair started this month, so it is not comparable; the Google
    News copy's pair is comparable but it is the duplicate. The story must still count, once, and the
    Google News pair must not drop out of the basis because its recent copies are all duplicates."""
    today = date(2026, 10, 12)
    themes, regions, country_id = _two_routes(db, today)
    compute(db, country_id, weeks=56, today=today + timedelta(days=7))      # the week of `today` is complete
    cell = db.scalar(select(CellWeek).where(CellWeek.theme_id == themes["health"], CellWeek.region_id == regions["national"],
                                            CellWeek.lens == "audience", CellWeek.week_start == week_start(today)))
    assert cell.coverage == 8                                   # 2 stories a week, each counted once whichever copy is kept
    assert cell.breakdown["articles_4w"] == 8                   # ... and scored: the story's other copy is comparable
    assert cell.breakdown["scored_outlets"] == 2 and cell.breakdown["scored_sources"] == ["gnews"]
    assert cell.breakdown["prev_scored_coverage"] == 8 and cell.breakdown["prev_coverage"] == 8
    assert cell.gap is not None and abs(cell.gap) < 0.2 and "coverage_drop" not in cell.flags
    # the Trends page and the bar's article list count the same stories
    login(client, "admin@example.org", "admin-password-1")
    r = client.get("/api/cells/trends", params={"lens": "audience"}).json()
    assert r["basis"]["outlets"] == 2 and r["basis"]["sources"] == ["gnews"]
    rows = r["themes"][str(themes["health"])]["rows"]
    last = next(x for x in rows if x["week"] == week_start(today).isoformat())
    assert last["articles"] == 2 and last["articles_all"] == 2 and last["articles_4w"] == 8
    wk = week_start(today)
    params = {"theme_id": themes["health"], "start": wk.isoformat(), "end": (wk + timedelta(days=6)).isoformat()}
    listed = client.get("/api/items", params={**params, "basis": "trend"}).json()
    assert listed["total"] == 2 and {x["source"] for x in listed["items"]} == {"gnews", "rss"}
    assert client.get("/api/items", params=params).json()["total"] == 2
