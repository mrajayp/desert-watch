from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from app.fetch_meta import FetchError, _check_public, parse_meta
from app.ingest import load_rules, store_article
from app.models import Item, NetworkEdgeWeek, Outlet
from app.network import compute, find_syndication
from tests.conftest import ids


def test_syndication_detects_near_duplicates():
    t0 = datetime(2026, 10, 1, 8)
    items = [
        (1, 10, t0, "Clashes erupt in Zawiya between rival armed groups, residents say"),
        (2, 11, t0 + timedelta(hours=3), "Clashes erupt in Zawiya between rival armed groups residents say"),
        (3, 12, t0 + timedelta(hours=1), "Central bank announces new dinar exchange rate"),
        (4, 10, t0 + timedelta(hours=5), "Clashes erupt in Zawiya between rival armed groups, residents say"),  # same outlet
    ]
    pairs = find_syndication(items)
    assert pairs[(10, 11)] >= 1
    assert all(12 not in p for p in pairs)


def test_edge_weights_sum_to_article_counts(db):
    themes, regions = ids(db)
    country_id = db.scalar(select(Outlet.country_id).limit(1))
    rules = load_rules(db, country_id)
    day = datetime(2026, 10, 6, 12)
    for k in range(4):
        store_article(db, country_id, rules, url=f"https://a.ly/{k}", title="Power cut leaves Sabha in darkness, electricity",
                      published_at=day, source_key="test")
    store_article(db, country_id, rules, url="https://b.ly/1", title="Hospital in Derna short of medicines",
                  published_at=day, source_key="test")
    db.commit()
    compute(db, country_id, weeks=2, today=date(2026, 10, 12))
    theme_edges = db.scalar(select(func.sum(NetworkEdgeWeek.weight)).where(NetworkEdgeWeek.kind == "outlet_theme"))
    from app.models import ItemTheme
    links = db.scalar(select(func.count()).select_from(ItemTheme).join(Item, Item.id == ItemTheme.item_id)
                      .where(Item.kind == "article", ItemTheme.active.is_(True)))
    assert theme_edges == links
    region_targets = {e.target_node for e in db.scalars(select(NetworkEdgeWeek).where(NetworkEdgeWeek.kind == "outlet_region"))}
    assert f"r:{regions['sabha']}" in region_targets and f"r:{regions['fezzan']}" in region_targets
    assert f"r:{regions['derna']}" in region_targets


def test_short_rerun_keeps_older_weekly_edges(db):
    country_id = db.scalar(select(Outlet.country_id).limit(1))
    rules = load_rules(db, country_id)
    for k, day in enumerate([datetime(2026, 3, 2, 12), datetime(2026, 10, 6, 12)]):
        store_article(db, country_id, rules, url=f"https://c.ly/{k}", title="Power cut leaves Sabha in darkness, electricity",
                      published_at=day, source_key="test")
    db.commit()
    weekly = lambda: {str(w) for w in db.scalars(select(NetworkEdgeWeek.week_start).where(NetworkEdgeWeek.kind == "outlet_theme"))}  # noqa: E731
    compute(db, country_id, weeks=40, today=date(2026, 10, 12))   # nightly: full history
    assert "2026-03-02" in weekly()
    compute(db, country_id, weeks=2, today=date(2026, 10, 12))    # hourly: recent weeks only
    assert {"2026-03-02", "2026-10-05"} <= weekly()


def test_ssrf_guard_and_meta_parse():
    for bad in ("file:///etc/passwd", "http://127.0.0.1/", "http://169.254.169.254/latest", "http://localhost:8000"):
        try:
            _check_public(bad)
            raise AssertionError(bad)
        except FetchError:
            pass
    m = parse_meta('<html lang="ar"><head><meta property="og:title" content="عنوان &amp; خبر">'
                   '<meta name="description" content="d"><meta property="article:published_time" '
                   'content="2026-10-01T10:00:00Z"></head></html>')
    assert m["title"] == "عنوان & خبر" and m["lang"] == "ar" and m["published"].startswith("2026-10-01")


def test_relevance_guard(db):
    from app.ingest import load_rules, store_article
    country_id = db.scalar(select(Outlet.country_id).limit(1))
    rules = load_rules(db, country_id)
    day = datetime(2026, 10, 6)
    off, _ = store_article(db, country_id, rules, url="https://intl.example/x", title="Pakistan petroleum minister visits Riyadh",
                           published_at=day, source_key="gnews", forced_theme_ids=(1,))
    on, _ = store_article(db, country_id, rules, url="https://intl.example/y", title="انقطاع الكهرباء في سبها",
                          published_at=day, source_key="gnews")
    on2, _ = store_article(db, country_id, rules, url="https://intl.example/z", title="Libyan coast guard intercepts boat",
                           published_at=day, source_key="gnews")
    # a .ly outlet's world news: no Libya mention and no theme match -> filtered
    world, _ = store_article(db, country_id, rules, url="https://news.ly/w", title="الحوثيون يتهمون السعودية",
                             published_at=day, source_key="gnews")
    db.commit()
    assert not off.relevant and off.extra["filtered"] == "no_country_mention"
    assert on.relevant and on2.relevant
    assert not world.relevant


def test_clusters_and_periods_endpoints(client, users, db):
    from tests.conftest import login
    login(client, "j@example.org", "journo-password-1")
    r = client.get("/api/clusters")
    assert r.status_code == 200 and r.json()["clusters"] == []
    r = client.get("/api/clusters/periods")
    assert r.status_code == 200 and r.json()["periods"] == []


def test_strict_theme_query_results_need_confirmation(db):
    from app.ingest import load_rules, store_article
    from app.models import ItemTheme, Theme
    country_id = db.scalar(select(Outlet.country_id).limit(1))
    gv = db.scalar(select(Theme).where(Theme.slug == "gender_violence"))
    assert gv.strict
    rules = load_rules(db, country_id)
    weak, _ = store_article(db, country_id, rules, url="https://x.example/1", title="ICC prosecutor visits Libya",
                            published_at=datetime(2026, 10, 1), source_key="gnews", forced_theme_ids=(gv.id,))
    good, _ = store_article(db, country_id, rules, url="https://x.example/2", title="مقتل امرأة طعناً في طرابلس",
                            published_at=datetime(2026, 10, 1), source_key="gnews", forced_theme_ids=(gv.id,))
    db.commit()
    assert db.get(ItemTheme, (weak.id, gv.id)).active is False
    assert db.get(ItemTheme, (good.id, gv.id)).active is True
