"""Trends data and score fixes: shared Wikipedia titles, lens availability, weeks still coming in,
the prior in articles, comparable outlets, and the /cells/trends payload against the article lists."""
import math
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import httpx
from sqlalchemy import select

from app import settings
from app.collectors import base, gdelt, wikipedia
from app.ingest import load_rules, store_article
from app.models import CellWeek, Item, ItemTheme, Outlet, Region, Theme
from app.scoring import (comparable_pairs, compute, compute_chunked, coverage_start, pair_spans, score_cell,
                         week_start)
from tests.conftest import ids, login
from tests.test_scoring import _pageviews

A = settings.PRIOR_ARTICLES


def _country(db):
    return db.scalar(select(Outlet.country_id).limit(1))


def _at(d: date, hour=9):
    return datetime.combine(d, datetime.min.time()) + timedelta(hours=hour)


# ---------------------------------------------------------------- Wikipedia
def _fake_wiki(views):
    def get(client, url, **kw):
        days = [date(2026, 10, 1) + timedelta(days=i) for i in range(3)]
        return SimpleNamespace(status_code=200, json=lambda: {"items": [
            {"timestamp": d.strftime("%Y%m%d00"), "views": views} for d in days]})
    return get


def test_shared_wikipedia_title_counts_for_each_theme(db, monkeypatch):
    themes, _ = ids(db)
    monkeypatch.setattr(wikipedia, "polite_get", _fake_wiki(10))
    res = wikipedia.collect(db)
    assert res.errors == 0
    # Women_in_Libya is listed under gender_violence AND gender_legal_status: one item per day, two themes
    rows = db.scalars(select(Item).where(Item.dedupe_key.like("wiki:en:Women\\_in\\_Libya:%", escape="\\"))).all()
    assert len(rows) == 3
    for it in rows:
        linked = set(db.scalars(select(ItemTheme.theme_id).where(ItemTheme.item_id == it.id)))
        assert linked == {themes["gender_violence"], themes["gender_legal_status"]}
    # a second run re-fetches and updates, adding nothing
    monkeypatch.setattr(wikipedia, "polite_get", _fake_wiki(25))
    n_links = len(db.scalars(select(ItemTheme)).all())
    assert wikipedia.collect(db).rows == 0
    assert len(db.scalars(select(ItemTheme)).all()) == n_links
    assert {it.value for it in db.scalars(select(Item).where(Item.kind == "pageview"))} == {25}


def test_repair_wiki_themes_adds_missing_links_once(db):
    themes, _ = ids(db)
    cid = _country(db)
    for d in range(4):
        day = date(2026, 9, 1) + timedelta(days=d)
        it = Item(country_id=cid, kind="pageview", source_key="wikipedia", lang="en", value=5,
                  dedupe_key=f"wiki:en:Human_trafficking_in_Libya:{day}", title="Human trafficking in Libya",
                  published_at=_at(day, 0))
        db.add(it)
        db.flush()
        db.add(ItemTheme(item_id=it.id, theme_id=themes["migration"], method="query"))
    # an underscore in the title must not act as a LIKE wildcard
    other = Item(country_id=cid, kind="pageview", source_key="wikipedia", lang="en", value=5,
                 dedupe_key="wiki:en:Human-trafficking-in-Libya:2026-09-01", title="x", published_at=_at(date(2026, 9, 1)))
    db.add(other)
    db.commit()
    assert wikipedia.repair_themes(db) == 4
    assert wikipedia.repair_themes(db) == 0
    migrant = set(db.scalars(select(ItemTheme.item_id).where(ItemTheme.theme_id == themes["gender_migrant_detained_women"])))
    assert len(migrant) == 4 and other.id not in migrant


def test_user_agent_has_contact_url():
    assert "https://" in settings.USER_AGENT


def test_polite_get_backs_off_on_429_and_honours_retry_after(monkeypatch):
    calls, sleeps = [], []
    monkeypatch.setattr(base.time, "sleep", sleeps.append)

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "30"})
        if len(calls) == 2:
            return httpx.Response(429)
        return httpx.Response(200, json={"ok": True})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    r = base.polite_get(client, "https://backoff.test/x", min_interval=0, retries=4, backoff=2.0, state={})
    assert r.status_code == 200 and len(calls) == 3
    assert sleeps == [30.0, 8.0]          # Retry-After wins over 4 s, then 2 x 2^2


def test_gdelt_quotes_hyphenated_terms():
    q = gdelt.theme_query("Libya", ["LGBT", "same-sex", "gender identity"])
    assert q == 'Libya (LGBT OR "same-sex" OR "gender identity")'


# ---------------------------------------------------------------- score
def test_prior_is_in_articles_and_reasons():
    # E = ref * need = 0.01 * 1000 = 10 expected articles, C = 2
    sc = score_cell(coverage=2, need=1000, ref_ratio=0.01)
    assert sc.expected == 10 and math.isclose(sc.gap, math.log((10 + A) / (2 + A)))
    shrunk = (2 + A) / (1000 + A / 0.01)                 # same thing written as shrinkage
    assert math.isclose(sc.gap, math.log(0.01 / shrunk))
    # the same expected articles give the same gap whatever the need unit
    assert math.isclose(score_cell(2, 10, 1.0).gap, sc.gap)
    assert score_cell(0, 0, None).reason == "no_need_data"
    assert score_cell(0, 100, None).reason == "no_need_data"
    low = score_cell(0, 250, 0.01)                         # 2.5 expected articles
    assert low.insufficient and low.gap is None and low.reason == "too_few_expected"
    assert not score_cell(0, 300, 0.01).insufficient       # 3 expected: judged


def test_small_themes_can_reach_red():
    # 8 expected articles and none published: about 2.6 times fewer, whatever the pageview count
    assert score_cell(0, 80, 0.1).gap > settings.GAP_RED_FROM


def test_comparable_pairs_tolerate_a_quiet_fortnight():
    end = date(2026, 10, 5)
    spans = {("gnews", 1): (date(2025, 1, 1), end - timedelta(days=10)),    # quiet for 10 days: kept
             ("gnews", 2): (date(2025, 1, 1), end - timedelta(days=20)),    # stopped: dropped
             ("rss", 3): (date(2025, 9, 1), end + timedelta(days=3)),       # started after the span: dropped
             ("rss", 4): (date(2025, 6, 2), end)}                           # exactly the span start: kept
    assert comparable_pairs(None, None, date(2025, 6, 2), end, spans=spans) == {("gnews", 1), ("rss", 4)}


def test_pair_spans_never_use_backfill_and_cold_start_skips_old_irrelevant(db):
    cid = _country(db)
    rules = load_rules(db, cid)
    old, _ = store_article(db, cid, rules, url="https://gov.ly/2014", title="Hospital shortages in Sabha",
                           published_at=datetime(2014, 5, 26), source_key="official")
    old.relevant = False
    store_article(db, cid, rules, url="https://bf.ly/2015", title="Hospital shortages in Sabha",
                  published_at=datetime(2015, 3, 3), source_key="backfill")
    store_article(db, cid, rules, url="https://news.ly/2019", title="Hospital shortages in Sabha",
                  published_at=datetime(2019, 1, 1, 8), source_key="gnews")
    db.commit()
    assert coverage_start(db, cid) == date(2019, 1, 7)
    assert {src for src, _ in pair_spans(db, cid)} == {"gnews"}


def test_pageview_spikes_are_capped_where_need_is_summed(db):
    themes, regions = ids(db)
    cid = _country(db)
    start = date(2026, 8, 3)
    spike_day = date(2026, 9, 16)
    for i in range(70):
        d = start + timedelta(days=i)
        it = Item(country_id=cid, kind="pageview", source_key="wikipedia", lang="en",
                  value=3000 if d == spike_day else 100, dedupe_key=f"wiki:en:Health_in_Libya:{d}",
                  title="Health in Libya", published_at=_at(d, 0))
        db.add(it)
        db.flush()
        db.add(ItemTheme(item_id=it.id, theme_id=themes["health"], method="query"))
    db.commit()
    compute(db, cid, weeks=2, today=week_start(spike_day) + timedelta(days=7), lenses=("audience",))
    cell = db.scalar(select(CellWeek).where(CellWeek.theme_id == themes["health"], CellWeek.region_id == regions["national"],
                                            CellWeek.lens == "audience", CellWeek.week_start == week_start(spike_day)))
    assert cell.breakdown["need_week"] == 6 * 100 + 500        # the spike day counts 5 x its 28-day median
    assert cell.breakdown["need_week_raw"] == 6 * 100 + 3000
    assert db.scalar(select(Item.value).where(Item.dedupe_key == f"wiki:en:Health_in_Libya:{spike_day}")) == 3000


# ---------------------------------------------------------------- weeks still coming in
def _steady_health(db, cid, rules, today, weeks, pageviews_until):
    """3 articles a week from one feed, 700 views a week read daily (up to `pageviews_until`)."""
    for w in range(weeks):
        mon = week_start(today) - timedelta(weeks=w)
        for k, off in enumerate((0, 3, 6)):
            store_article(db, cid, rules, url=f"https://old.ly/h/{w}/{k}", title="Hospital shortages in Sabha",
                          published_at=_at(mon + timedelta(days=off)), source_key="rss")
        for i in range(7):
            d = mon + timedelta(days=i)
            if d <= pageviews_until:
                _pageviews(db, cid, themes_id(db, "health"), d, 100, days=1)
    db.commit()


def themes_id(db, slug):
    return db.scalar(select(Theme.id).where(Theme.slug == slug))


def test_current_week_and_unfinished_need_are_in_progress(db):
    themes, regions = ids(db)
    cid = _country(db)
    rules = load_rules(db, cid)
    now = date(2026, 10, 14)                              # a Wednesday
    _steady_health(db, cid, rules, now, 30, pageviews_until=date(2026, 10, 10))   # need ends on Saturday
    compute(db, cid, weeks=3, today=now, lenses=("audience",))
    cells = {c.week_start: c for c in db.scalars(select(CellWeek).where(
        CellWeek.theme_id == themes["health"], CellWeek.region_id == regions["national"], CellWeek.lens == "audience"))}
    cur, last, before = cells[date(2026, 10, 12)], cells[date(2026, 10, 5)], cells[date(2026, 9, 28)]
    for c in (cur, last):
        assert c.breakdown["in_progress"] and c.breakdown["reason"] == "in_progress"
        assert c.gap is None and c.insufficient and "coverage_drop" not in c.flags
    assert not before.breakdown["in_progress"] and before.gap is not None and abs(before.gap) < 0.2
    # the week whose need stops on Saturday counts coverage up to Saturday too (the Sunday article is cut)
    assert last.breakdown["need_through"] == "2026-10-10"
    assert last.breakdown["articles_4w"] == before.breakdown["articles_4w"] - 1


def test_week_is_complete_once_need_reaches_its_last_day(db):
    themes, regions = ids(db)
    cid = _country(db)
    rules = load_rules(db, cid)
    now = date(2026, 10, 14)
    _steady_health(db, cid, rules, now, 30, pageviews_until=date(2026, 10, 12))
    compute(db, cid, weeks=2, today=now, lenses=("audience",))
    last = db.scalar(select(CellWeek).where(CellWeek.theme_id == themes["health"], CellWeek.region_id == regions["national"],
                                            CellWeek.lens == "audience", CellWeek.week_start == date(2026, 10, 5)))
    assert not last.breakdown["in_progress"] and last.gap is not None and last.breakdown["reason"] is None


def test_too_few_expected_and_no_need_reasons(db):
    themes, regions = ids(db)
    cid = _country(db)
    rules = load_rules(db, cid)
    now = date(2026, 10, 14)
    for w in range(30):
        mon = week_start(now) - timedelta(weeks=w)
        # one gender-violence article every other week against steady reading: E is about 2 per window
        if w % 2 == 0:
            store_article(db, cid, rules, url=f"https://old.ly/gv/{w}", title="Libya: woman killed by her husband in Tripoli, domestic violence",
                          published_at=_at(mon), source_key="rss")
        _pageviews(db, cid, themes["gender_violence"], mon, 700)
        store_article(db, cid, rules, url=f"https://old.ly/ec/{w}", title="Central bank and oil exports",
                      published_at=_at(mon), source_key="rss")
    db.commit()
    compute(db, cid, weeks=2, today=now, lenses=("audience",))
    q = select(CellWeek).where(CellWeek.region_id == regions["national"], CellWeek.lens == "audience",
                               CellWeek.week_start == date(2026, 10, 5))
    cells = {c.theme_id: c for c in db.scalars(q)}
    gv, econ = cells[themes["gender_violence"]], cells[themes["economy"]]
    assert gv.insufficient and gv.breakdown["reason"] == "too_few_expected" and gv.breakdown["expected_4w"] < 3
    assert econ.insufficient and econ.breakdown["reason"] == "no_need_data" and econ.breakdown["expected_week"] is None


# ---------------------------------------------------------------- lens availability
def _cell(db, cid, tid, rid, wk, lens, judged, **b):
    db.add(CellWeek(country_id=cid, theme_id=tid, region_id=rid, week_start=wk, lens=lens, need=1, coverage=1,
                    gap=0.1 if judged else None, insufficient=not judged, breakdown=b))


def test_lens_available_only_with_recent_judged_cells_across_themes(client, users, db):
    themes, regions = ids(db)
    cid = _country(db)
    nat = regions["national"]
    active = db.scalars(select(Theme.id).where(Theme.active.is_(True)).order_by(Theme.id)).all()
    need = math.ceil(len(active) / 3)
    latest = date(2026, 10, 12)
    for tid in active:
        _cell(db, cid, tid, nat, latest, "audience", False, in_progress=True, reason="in_progress")
        _cell(db, cid, tid, nat, latest, "humanitarian", False, in_progress=True, reason="in_progress")
    for k, tid in enumerate(active):
        for w in range(1, 13):
            wk = latest - timedelta(weeks=w)
            # audience: a third of themes judged in 4 of the last 12 complete weeks
            _cell(db, cid, tid, nat, wk, "audience", k < need and w <= 4)
            # humanitarian: one theme judged recently, others only long ago
            _cell(db, cid, tid, nat, wk, "humanitarian", k == 0 and w <= 6)
        if k < need:
            _cell(db, cid, tid, nat, latest - timedelta(weeks=60), "humanitarian", True)
    # need items: theme 2 has a report this year, theme 3 only one from 2 years ago
    for tid, when in ((active[1], datetime(2026, 6, 1)), (active[2], datetime(2024, 6, 1))):
        it = Item(country_id=cid, kind="report", source_key="official", dedupe_key=f"r:{tid}", title="r",
                  published_at=when)
        db.add(it)
        db.flush()
        db.add(ItemTheme(item_id=it.id, theme_id=tid, method="rule"))
    db.commit()
    login(client, "admin@example.org", "admin-password-1")
    lenses = {x["key"]: x for x in client.get("/api/meta").json()["lenses"]}
    assert lenses["audience"]["available"] and not lenses["humanitarian"]["available"]
    assert lenses["humanitarian"]["themes_with_need"] == [active[1]]
    assert not lenses["events"]["available"] and lenses["events"]["themes_with_need"] == []
    # one theme fewer and the audience lens is no longer offered
    db.query(CellWeek).filter(CellWeek.theme_id == active[need - 1], CellWeek.lens == "audience").delete()
    db.commit()
    assert not {x["key"]: x for x in client.get("/api/meta").json()["lenses"]}["audience"]["available"]


# ---------------------------------------------------------------- the Trends payload
def test_trends_payload_matches_scores_and_article_lists(client, users, db):
    themes, regions = ids(db)
    cid = _country(db)
    rules = load_rules(db, cid)
    now = date(2026, 10, 14)                            # Wednesday, need data up to Monday
    cur = week_start(now)
    for w in range(72):
        mon = cur - timedelta(weeks=w)
        n = 2 if w % 5 else 4                            # some weeks busier than others
        for k in range(n):
            store_article(db, cid, rules, url=f"https://old.ly/t/{w}/{k}", title=f"Hospital shortages in Sabha {k}",
                          published_at=_at(mon + timedelta(days=k)), source_key="rss")
        if w < 10:                                       # a new outlet: never comparable
            store_article(db, cid, rules, url=f"https://new.ly/t/{w}", title="Hospital medicines shortage Libya",
                          published_at=_at(mon + timedelta(days=1)), source_key="rss")
        if 20 <= w < 40:                                 # the backfill: never comparable
            store_article(db, cid, rules, url=f"https://bf.ly/t/{w}", title="Hospital medicines shortage Libya",
                          published_at=_at(mon + timedelta(days=2)), source_key="backfill")
        store_article(db, cid, rules, url=f"https://old.ly/e/{w}", title="Central bank and oil exports",
                      published_at=_at(mon + timedelta(days=1)), source_key="rss")
        for i in range(7):
            if mon + timedelta(days=i) <= cur:
                _pageviews(db, cid, themes["health"], mon + timedelta(days=i), 300 + 40 * (w % 3), days=1)
    db.commit()
    compute_chunked(db, cid, weeks=60, today=now)
    login(client, "admin@example.org", "admin-password-1")
    r = client.get("/api/cells/trends", params={"lens": "audience"}).json()
    assert r["unit"] == "pageviews" and r["red_from"] == settings.GAP_RED_FROM
    assert len(r["weeks"]) == 53 and r["weeks"][-1] == cur.isoformat()
    assert r["basis"]["outlets"] == 1 and r["basis"]["sources"] == ["rss"]
    health, econ = r["themes"][str(themes["health"])], r["themes"][str(themes["economy"])]
    assert health["has_need"] and not econ["has_need"]
    assert all(x["expected_week"] is None and x["reason"] in ("no_need_data", "in_progress") for x in econ["rows"])
    rows = health["rows"]
    assert [x["in_progress"] for x in rows] == [False] * 52 + [True]
    cells = {c.week_start.isoformat(): c for c in db.scalars(select(CellWeek).where(
        CellWeek.theme_id == themes["health"], CellWeek.region_id == regions["national"], CellWeek.lens == "audience"))}
    judged = 0
    for i, x in enumerate(rows):
        c = cells[x["week"]]
        assert x["articles"] <= x["articles_all"]
        if x["expected_week"] is not None:
            assert math.isclose(x["expected_week"], x["need_week"] * c.ref_ratio)
        if x["gap"] is None:
            continue
        judged += 1
        # the 4-week sums reproduce ref * need before shrinkage, and the gap follows from them
        assert math.isclose(x["expected_4w"], c.ref_ratio * c.need)
        assert math.isclose(x["gap"], math.log((x["expected_4w"] + A) / (x["articles_4w"] + A)))
        if i >= 3:
            assert x["articles_4w"] == sum(y["articles"] for y in rows[i - 3:i + 1])
    assert judged >= 40
    # each bar's click-through list adds up to the bar; without the basis it lists every source
    for x in rows[-12:]:
        wk = date.fromisoformat(x["week"])
        params = {"theme_id": themes["health"], "start": wk.isoformat(), "end": (wk + timedelta(days=6)).isoformat()}
        assert client.get("/api/items", params={**params, "basis": "trend"}).json()["total"] == x["articles"]
        assert client.get("/api/items", params=params).json()["total"] == x["articles_all"]
    assert any(x["articles_all"] > x["articles"] for x in rows[-10:])
    assert client.get("/api/items", params={"basis": "nope"}).status_code == 400
    # pages open on the latest week that has ended, never the one still coming in
    m = client.get("/api/meta").json()
    assert m["latest_week"] == rows[-2]["week"] and m["current_week"] == cur.isoformat()
    assert client.get("/api/cells", params={"lens": "audience"}).json()["week"] == rows[-2]["week"]


def test_coverage_monthly_by_source_and_partial_month(client, users, db):
    themes, _ = ids(db)
    cid = _country(db)
    rules = load_rules(db, cid)
    from app.models import utcnow
    this = utcnow().replace(day=1, hour=9)
    last = (this - timedelta(days=2)).replace(day=1)
    for i, src in enumerate(("gnews", "rss", "backfill", "galerts", "user")):
        for when in (this, last):
            store_article(db, cid, rules, url=f"https://m{i}.ly/{when:%Y%m}", title="Hospital shortages in Sabha",
                          published_at=when, source_key=src)
    db.commit()
    login(client, "admin@example.org", "admin-password-1")
    months = client.get("/api/coverage-monthly", params={"theme_id": themes["health"]}).json()
    assert [m["partial"] for m in months[-2:]] == [False, True]
    assert months[-1]["sources"] == {"gnews": 1, "rss": 1, "backfill": 1, "galerts": 1, "other": 1}
    assert months[-1]["total"] == 5
