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
from app.models import CellWeek, CoverageSeries, Item, ItemTheme, Outlet, Region, Theme
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
def _fake_wiki(views, calls=None):
    def get(client, url, **kw):
        if calls is not None:
            calls.append(url)
        days = [date(2026, 10, 1) + timedelta(days=i) for i in range(3)]
        return SimpleNamespace(status_code=200, text="", json=lambda: {"items": [
            {"timestamp": d.strftime("%Y%m%d00"), "views": views} for d in days]})
    return get


def test_shared_wikipedia_title_counts_for_each_theme(db, monkeypatch):
    themes, _ = ids(db)
    calls = []
    monkeypatch.setattr(wikipedia, "polite_get", _fake_wiki(10, calls))
    res = wikipedia.collect(db)
    assert res.errors == 0
    # each title is fetched once, however many themes list it
    shared = [u for u in calls if "/en.wikipedia/" in u and "/Women_in_Libya/" in u]
    assert len(shared) == 1 and len(calls) == len(set(calls))
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


def _refusing(calls):
    def get(client, url, **kw):
        calls.append(kw.get("retries"))
        return httpx.Response(429)
    return get


def test_collectors_stop_after_three_refusals_in_a_row(db, monkeypatch):
    calls = []
    monkeypatch.setattr(wikipedia, "polite_get", _refusing(calls))
    res = wikipedia.collect(db)
    assert len(calls) == base.STOP_AFTER and res.rows == 0 and res.detail.startswith("stopped after 3 refusals")
    # GDELT: the six-hourly article run keeps the short backoff, only the long-run line retries 4 times
    calls.clear()
    monkeypatch.setattr(gdelt, "polite_get", _refusing(calls))
    res = gdelt.collect(db)
    assert calls == [gdelt.RETRIES] * 3 and gdelt.RETRIES == 2 and "stopped after 3" in res.detail
    calls.clear()
    res = gdelt.collect_timeline(db)
    assert calls == [gdelt.TIMELINE_RETRIES] * 3 and "stopped after 3" in res.detail
    # an answer that is not a refusal (a bad query) resets the count
    answers = iter([429, 429, 200, 429, 429, 429, 429])
    calls.clear()

    def mixed(client, url, **kw):
        calls.append(1)
        return httpx.Response(next(answers), text="Your search contained an illegal character")
    monkeypatch.setattr(gdelt, "polite_get", mixed)
    gdelt.collect(db)
    assert len(calls) == 6


def test_gdelt_quotes_hyphenated_terms():
    q = gdelt.theme_query("Libya", ["LGBT", "same-sex", "gender identity"])
    assert q == 'Libya (LGBT OR "same-sex" OR "gender identity")'


def _query_terms(q: str) -> list[str]:
    """The OR list inside a GDELT query, one quoted term per entry."""
    return q[q.index("(") + 1:q.rindex(")")].split(" OR ")


def test_gdelt_asks_every_term_in_chunks_and_merges_the_answers(db, monkeypatch):
    """A-R2.9: a theme with more than MAX_TERMS terms is asked in several queries, every term in exactly one
    of them; an article two chunks return is stored once; requests stay at least 5 s apart; the run
    detail says how many queries ran (the health strip shows it)."""
    asked, sleeps = [], []
    monkeypatch.setattr(base.time, "sleep", sleeps.append)
    monkeypatch.setattr(base.time, "monotonic", lambda: 1e6)   # a frozen clock: every wait is the whole interval

    def handler(request):
        asked.append(request.url.params["query"])
        n = len(asked)
        return httpx.Response(200, json={"articles": [
            {"url": "https://gd.example/shared", "title": "Libya clashes", "seendate": "20261013T100000Z",
             "domain": "gd.example", "language": "English"},
            {"url": f"https://gd.example/{n}", "title": f"Libya story {n}", "seendate": "20261013T110000Z",
             "domain": "gd.example", "language": "French"}]})
    monkeypatch.setattr(gdelt, "http_client", lambda **kw: httpx.Client(transport=httpx.MockTransport(handler)))
    res = gdelt.collect(db)
    themes = db.scalars(select(Theme).where(Theme.active.is_(True))).all()
    assert asked == [q for t in themes for q in gdelt.theme_queries("Libya", t.en_terms)]
    assert len(asked) > len(themes)   # the long lists were chunked
    for t in themes:
        mine = gdelt.theme_queries("Libya", t.en_terms)
        assert len(mine) == -(-len(t.en_terms) // gdelt.MAX_TERMS)
        assert all(len(_query_terms(q)) <= gdelt.MAX_TERMS for q in mine)
        for term in t.en_terms:
            quoted = f'"{term}"' if " " in term or "-" in term else term
            assert sum(quoted in _query_terms(q) for q in mine) == 1, term
    assert res.errors == 0 and res.detail == f"{len(asked)} queries for {len(themes)} themes over 1 day, 0 refused by GDELT"
    assert len(db.scalars(select(Item).where(Item.url == "https://gd.example/shared")).all()) == 1
    assert res.rows == 1 + len(asked)
    assert db.scalar(select(Item.lang).where(Item.url == "https://gd.example/1")) == "fr"   # GDELT's own language label
    assert len(sleeps) == len(asked) - 1 and all(w >= 5.0 for w in sleeps)   # paced: one request per 5 s or slower
    assert gdelt.INTERVAL >= 5.0


def test_gdelt_history_adds_the_chunks_and_skips_a_cut_line(db, monkeypatch):
    """The long-run line adds the chunks' daily counts; a line whose chunk GDELT refused is not written,
    so a stored line always counts the whole term list."""
    sec = db.scalar(select(Theme).where(Theme.slug == "security"))
    chunks = gdelt.theme_queries("Libya", sec.en_terms)
    assert len(chunks) == 3
    second = _query_terms(chunks[1])[0]   # a term of the second chunk

    def handler(request):
        q = request.url.params["query"]
        if "sourcecountry:" in q and second in _query_terms(q):
            return httpx.Response(429)   # the second chunk of the sourcecountry line, refused every time
        return httpx.Response(200, json={"timeline": [{"data": [{"date": "20261001T000000Z", "value": 10},
                                                                {"date": "20261002T000000Z", "value": 1}]}]})
    monkeypatch.setattr(gdelt, "http_client", lambda **kw: httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(base.time, "sleep", lambda w: None)
    res = gdelt.collect_timeline(db, themes=["security"])
    rows = {(r.series, r.day.isoformat()): r.value
            for r in db.scalars(select(CoverageSeries).where(CoverageSeries.theme_id == sec.id))}
    assert rows == {("all", "2026-10-01"): 30, ("all", "2026-10-02"): 3}
    assert res.rows == 2 and res.errors == 1
    assert res.detail.startswith("5 queries for 1 themes x 2 series, 1 refused by GDELT; security/sourcecountry: HTTP 429")


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


def test_digest_waits_for_sundays_page_views(db, monkeypatch):
    from app import digest
    from app.models import Country
    from tests.test_digest import FakeMessages
    cid = _country(db)
    rules = load_rules(db, cid)
    monday = date(2026, 10, 12)
    _steady_health(db, cid, rules, monday, 30, pageviews_until=date(2026, 10, 10))   # Sunday's views not in yet
    compute(db, cid, weeks=3, today=monday, lenses=("audience",))
    # last week is still coming in: the digest covers the week before, or on Thursday goes ahead anyway
    assert digest.digest_week(db, cid, today=monday) == date(2026, 9, 28)
    assert digest.digest_week(db, cid, today=date(2026, 10, 15)) == date(2026, 10, 5)
    fake = FakeMessages()
    monkeypatch.setattr(digest, "_client", lambda: SimpleNamespace(messages=fake))
    country = db.get(Country, cid)
    assert digest.generate(db, country, today=monday).week_start == date(2026, 9, 28)
    # Sunday's views arrive overnight: Tuesday's run writes last week's digest with its audience gaps
    _pageviews(db, cid, themes_id(db, "health"), date(2026, 10, 11), 100, days=1)
    db.commit()
    tuesday = monday + timedelta(days=1)
    compute(db, cid, weeks=3, today=tuesday, lenses=("audience",))
    assert digest.digest_week(db, cid, today=tuesday) == date(2026, 10, 5)
    from tests.conftest import offer_lens
    offer_lens(db, date(2026, 10, 5))   # the digest reports gaps only on lenses the site offers: one theme is not a lens
    d = digest.generate(db, country, today=tuesday)
    assert d.week_start == date(2026, 10, 5) and "audience" in d.facts["lenses_with_data"]


def test_stalled_need_is_judged_after_a_week_on_the_days_we_have(db):
    from app.scoring import latest_complete_week
    themes, regions = ids(db)
    cid = _country(db)
    rules = load_rules(db, cid)
    now = date(2026, 10, 14)                                # a Wednesday
    _steady_health(db, cid, rules, now, 30, pageviews_until=date(2026, 9, 30))   # page views stopped on a Wednesday
    compute(db, cid, weeks=4, today=now, lenses=("audience",))
    cells = {c.week_start: c for c in db.scalars(select(CellWeek).where(
        CellWeek.theme_id == themes["health"], CellWeek.region_id == regions["national"], CellWeek.lens == "audience"))}
    stalled = cells[date(2026, 9, 28)]                      # ended 4 Oct, more than a week ago: judged
    assert not stalled.breakdown["in_progress"] and stalled.gap is not None
    assert "need_incomplete" in stalled.flags and stalled.breakdown["need_through"] == "2026-09-30"
    assert abs(stalled.gap) < 0.2                           # both sides cut at the same day
    assert cells[date(2026, 10, 5)].breakdown["in_progress"]    # ended 11 Oct: still waiting
    assert "need_incomplete" not in cells[date(2026, 9, 21)].flags
    assert latest_complete_week(db, cid) == date(2026, 9, 28)


def test_need_ends_on_the_day_most_titles_reached(db):
    from app.scoring import need_end_day
    themes, _ = ids(db)
    cid = _country(db)
    for slug, until in (("health", date(2026, 10, 11)), ("security", date(2026, 10, 10)), ("economy", date(2026, 10, 10))):
        for i in range(14):
            d = until - timedelta(days=i)
            _pageviews(db, cid, themes[slug], d, 50, days=1)
    db.commit()
    assert need_end_day(db, cid, date(2026, 10, 13)) == date(2026, 10, 10)   # one title of three has Sunday
    _pageviews(db, cid, themes["security"], date(2026, 10, 11), 50, days=1)
    db.commit()
    assert need_end_day(db, cid, date(2026, 10, 13)) == date(2026, 10, 11)   # two of three
    # after a long stall (no title read in 28 days) the last day we have still counts
    assert need_end_day(db, cid, date(2026, 12, 1)) == date(2026, 10, 11)


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
    # one theme fewer and the audience lens is no longer offered (no page views here: all themes count)
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
            # the chart draws a verdict's 4 weeks at its cell's baseline: they add up to the usual it quotes
            assert math.isclose(sum(y["need_week"] for y in rows[i - 3:i + 1]) * x["ref"], x["expected_4w"])
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


def test_a_story_whose_other_copy_came_through_a_new_route_is_not_counted_twice(client, users, db):
    """The reverse of the dedupe->scoring twin in test_dedupe_stable: the kept feed copy's pair is the
    comparable one and Google News (new this month, not comparable) finds the same stories. The bars,
    the 4-week count and the bar's article list all count each story once."""
    from app.dedupe import mark_duplicates
    themes, regions = ids(db)
    cid = _country(db)
    rules = load_rules(db, cid)
    today = date(2026, 10, 12)
    vary = ("worsen", "ease", "persist", "return", "spread", "continue", "deepen")
    for w in range(60):
        mon = week_start(today) - timedelta(weeks=w)
        _pageviews(db, cid, themes["health"], mon, 2000)
        store_article(db, cid, rules, url=f"https://old.ly/s/{w}", title=f"Hospital shortages in Sabha leave patients waiting as they {vary[w % 7]}",
                      published_at=_at(mon), source_key="rss")
        if w < 3:
            store_article(db, cid, rules, url=f"https://news.google.com/rss/articles/s{w}", outlet_domain="old.ly",
                          title=f"Hospital shortages in Sabha leave patients waiting as they {vary[w % 7]} - Old",
                          published_at=_at(mon, 11), source_key="gnews")
    db.commit()
    assert mark_duplicates(db) == 3
    compute(db, cid, weeks=56, today=today + timedelta(days=7))
    cell = db.scalar(select(CellWeek).where(CellWeek.theme_id == themes["health"], CellWeek.region_id == regions["national"],
                                            CellWeek.lens == "audience", CellWeek.week_start == week_start(today)))
    assert cell.coverage == 4 and cell.breakdown["articles_4w"] == 4 and cell.breakdown["scored_sources"] == ["rss"]
    assert abs(cell.gap) < 0.2
    login(client, "admin@example.org", "admin-password-1")
    r = client.get("/api/cells/trends", params={"lens": "audience"}).json()
    assert r["basis"]["sources"] == ["rss"] and r["basis"]["outlets"] == 1
    rows = r["themes"][str(themes["health"])]["rows"]
    for x in rows[-4:-1]:
        assert x["articles"] == 1 and x["articles_all"] == 1
        wk = date.fromisoformat(x["week"])
        params = {"theme_id": themes["health"], "start": wk.isoformat(), "end": (wk + timedelta(days=6)).isoformat()}
        assert client.get("/api/items", params={**params, "basis": "trend"}).json()["total"] == 1
    # the comparable set still reads the copies: the Google News pair spans only its three weeks
    spans = pair_spans(db, cid)
    assert spans[("gnews", cell_outlet(db, "old.ly"))][0] == week_start(today) - timedelta(weeks=2)


def cell_outlet(db, domain):
    return db.scalar(select(Outlet.id).where(Outlet.domain == domain))


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
