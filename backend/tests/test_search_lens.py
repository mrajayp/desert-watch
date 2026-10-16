"""Search lens: importing Google Trends rows, scoring against own history, the gap panel's words."""
import json
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from app import settings
from app.collectors import gtrends as gt_collector
from app.collectors.base import AwaitingKey
from app.gtrends import build_rows, config, flag_missing_weeks, parse_points
from app.imports.search_trends import import_rows, run as run_import
from app.ingest import load_rules, store_article
from app.models import CellWeek, Country, Item, ItemTheme
from app.scoring import compute, week_start
from tests.conftest import ids, login

SUN = date(2026, 5, 3)  # a Sunday


def _ts(d: date) -> str:
    return str(int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp()))


def _point(d, values, has=None):
    return {"time": _ts(d), "value": values, "hasData": has or [True] * len(values)}


def _cfg(db):
    return config(db.scalar(select(Country)).config)


def _rows(g, slugs, weeks=20, *, start=SUN, value=lambda slug, i: 10, anchor=20, has=lambda slug, i: True,
          rid="r1", fetched="2026-10-16T06:00:00+00:00", basket=None, anchor_term=None):
    slots = [(sl, basket or g["baskets"][sl]) for sl in slugs]
    tl = [_point(start + timedelta(weeks=i), [value(sl, i) for sl, _ in slots] + [anchor],
                 [has(sl, i) for sl, _ in slots] + [True]) for i in range(weeks)]
    return build_rows(parse_points(tl), slots, anchor_term or g["anchor"], resolution="week", request_id=rid,
                      fetched_at=fetched)


def test_import_creates_one_item_per_theme_week_and_is_idempotent(db, tmp_path):
    g = _cfg(db)
    rows = _rows(g, ["services", "health"], value=lambda sl, i: 30 if sl == "services" else 10)
    p = tmp_path / "gt.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    out = run_import(db, p)
    assert out["created"] == 40 and out.get("updated", 0) == 0
    monday = (SUN + timedelta(days=1)).isoformat()
    it = db.scalar(select(Item).where(Item.dedupe_key == f"gt:services:v{g['version']}:{monday}"))
    assert it.kind == "search" and it.source_key == "gtrends" and it.published_at.weekday() == 0
    assert it.value == 150.0  # 100 * 30 / 20: anchor units
    assert it.extra["terms"] == g["baskets"]["services"] and it.extra["anchor"] == g["anchor"]
    assert {"provisional", "has_data", "fetched_at"} <= set(it.extra)
    link = db.scalar(select(ItemTheme).where(ItemTheme.item_id == it.id))
    assert link.method == "query" and link.active
    again = run_import(db, p)
    assert again.get("created", 0) == 0 and again["unchanged"] == 40
    assert db.query(Item).filter(Item.kind == "search").count() == 40
    (tmp_path / "gtrends-20261009T060000Z.jsonl").write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "gtrends-20261002T060000Z.jsonl").write_text("", encoding="utf-8")
    assert run_import(db, tmp_path)["file"] == "gtrends-20261009T060000Z.jsonl"  # a folder: its newest file


def test_reimport_replaces_revised_weeks(db):
    g = _cfg(db)
    import_rows(db, _rows(g, ["economy"]))
    last = (SUN + timedelta(weeks=19, days=1)).isoformat()
    item = db.scalar(select(Item).where(Item.dedupe_key == f"gt:economy:v1:{last}"))
    assert item.extra["provisional"] and item.value == 50.0
    revised = _rows(g, ["economy"], weeks=22, value=lambda sl, i: 16 if i >= 18 else 10, rid="r2",
                    fetched="2026-10-23T06:00:00+00:00")
    out = import_rows(db, revised)
    assert out["created"] == 2 and out["updated"] == 20  # newer fetch on every week
    db.refresh(item)
    assert item.value == 80.0 and not item.extra["provisional"]
    assert import_rows(db, revised)["unchanged"] == 22


def test_import_skips_other_lists_and_weeks_before_the_data_break(db):
    g = _cfg(db)
    rows = _rows(g, ["services"], basket=["الكهرباء"])                          # a trial list
    rows += _rows(g, ["services"], anchor_term="translate", rid="r3")           # another anchor
    rows += _rows(g, ["services"], start=date(2021, 11, 7), weeks=12, rid="r4")  # straddles 1 Jan 2022
    rows += _rows(g, ["migration"], basket=["مهاجرين"], rid="r5")              # no list for this theme
    out = import_rows(db, rows)
    assert out["other_list"] == 60 and out["before_since"] == 8 and out["created"] == 4
    first = min(i.published_at.date() for i in db.scalars(select(Item).where(Item.kind == "search")))
    assert first >= date(2022, 1, 3)


def test_daily_beats_weekly_and_data_beats_no_data(db):
    g = _cfg(db)
    weekly = _rows(g, ["health"], weeks=3, has=lambda sl, i: i != 1)
    days = [SUN + timedelta(days=1 + k) for k in range(21)]
    daily = build_rows(parse_points([_point(d, [3, 4]) for d in days]), [("health", g["baskets"]["health"])],
                       g["anchor"], resolution="day", request_id="d1", fetched_at="2026-10-16T06:10:00+00:00")
    daily[2]["has_data"] = False  # Google held back the third week of the daily pull
    import_rows(db, weekly + daily)
    items = {i.published_at.date(): i for i in db.scalars(select(Item).where(Item.kind == "search"))}
    w = sorted(items)
    assert items[w[0]].extra["resolution"] == "day" and items[w[0]].value == 75.0
    assert items[w[1]].extra["resolution"] == "day"     # the weekly pull had no data that week
    assert items[w[2]].extra["resolution"] == "week"    # the daily pull had no data that week


def test_new_list_version_retires_old_items(db):
    g = _cfg(db)
    import_rows(db, _rows(g, ["services"], weeks=4))
    c = db.scalar(select(Country))
    c.config = {**c.config, "gtrends": {**g, "version": g["version"] + 1}}
    db.commit()
    out = import_rows(db, _rows(g, ["services"], weeks=4))
    assert out["created"] == 4 and out["retired"] == 4
    live = db.scalars(select(Item).where(Item.kind == "search", Item.relevant.is_(True))).all()
    assert len(live) == 4 and all(":v2:" in i.dedupe_key for i in live)


TODAY = date(2026, 10, 14)                          # a Wednesday: no search data for this week yet
LAST_FULL = week_start(TODAY) - timedelta(weeks=1)
START = LAST_FULL - timedelta(weeks=29, days=1)     # the Sunday 30 weeks back
HOLE_WEEK = START + timedelta(weeks=10, days=1)     # Google held this week back


def _scored_health(db):
    """30 weeks of health searches with one hole, steady coverage that stops in the last five weeks."""
    g = _cfg(db)
    cid = db.scalar(select(Country.id))
    rules = load_rules(db, cid)
    import_rows(db, _rows(g, ["health"], weeks=30, start=START, has=lambda sl, i: i != 10))
    for w in range(31):
        day = week_start(TODAY) - timedelta(weeks=w)
        if w >= 5:  # coverage stops in the last five weeks
            for k in range(5):
                store_article(db, cid, rules, url=f"https://ex.com/s/{w}/{k}", title="Hospital shortages in Sabha",
                              published_at=datetime.combine(day, datetime.min.time()), source_key="test")
    db.commit()
    compute(db, cid, weeks=24, today=TODAY, lenses=("search",))
    return cid


def test_search_lens_scores_against_own_history_and_needs_every_week(db):
    themes, regions = ids(db)
    today, last_full, hole_week = TODAY, LAST_FULL, HOLE_WEEK
    cid = _scored_health(db)
    assert flag_missing_weeks(db, cid) > 0
    nat = regions["national"]

    def cell(t, wk):
        return db.scalar(select(CellWeek).where(CellWeek.theme_id == themes[t], CellWeek.region_id == nat,
                                                CellWeek.lens == "search", CellWeek.week_start == wk))
    now = cell("health", week_start(today))
    assert now.insufficient and now.gap is None
    assert now.breakdown["search_missing_weeks"] == [week_start(today).isoformat()]
    hole = cell("health", hole_week + timedelta(weeks=2))
    assert hole.insufficient and hole_week.isoformat() in hole.breakdown["search_missing_weeks"]
    scored = cell("health", last_full)
    assert not scored.insufficient and scored.gap > 0.5   # searches held while coverage stopped
    steady = cell("health", hole_week + timedelta(weeks=4))
    assert not steady.insufficient and abs(steady.gap) < 0.3
    assert cell("migration", last_full).insufficient       # no word list: never scored
    assert flag_missing_weeks(db, cid) == 0                # nothing left to mark
    # the hole week counts as its neighbours in later baselines, not as zero need
    after = cell("health", hole_week + timedelta(weeks=5))
    assert not after.insufficient and abs(after.gap) < 0.05


def test_a_theme_edit_keeps_the_missing_week_rule(db, monkeypatch):
    from app import scoring
    from app.api import admin
    themes, regions = ids(db)
    cid = _scored_health(db)
    # Admin -> Themes re-tags and rescores straight away, outside jobs.recompute
    monkeypatch.setattr(scoring, "compute_all",
                        lambda s, **kw: compute(s, cid, weeks=24, today=TODAY, lenses=("search",)))
    admin._retag_theme(themes["health"])
    db.expire_all()
    now = db.scalar(select(CellWeek).where(CellWeek.theme_id == themes["health"], CellWeek.lens == "search",
                                           CellWeek.region_id == regions["national"],
                                           CellWeek.week_start == week_start(TODAY)))
    assert now.insufficient and now.gap is None    # three weeks of data out of four: still unscored


def test_digest_explains_search_gaps(db):
    from app import digest
    cid = _scored_health(db)
    flag_missing_weeks(db, cid)
    country = db.get(Country, cid)
    f = digest.build_facts(db, country, LAST_FULL)
    assert any(g["lens"] == "search" for g in f["top_gaps"])
    assert digest.SEARCH_LIMIT in f["known_limits"]
    assert digest.SEARCH_LIMIT not in digest.build_facts(db, country, week_start(TODAY))["known_limits"]


def test_meta_opens_search_on_its_latest_scored_week_and_trends_skip_missing_weeks(client, users, db):
    themes, regions = ids(db)
    cid = _scored_health(db)
    flag_missing_weeks(db, cid)
    login(client, "j@example.org", "journo-password-1")
    m = client.get("/api/meta").json()
    search = next(x for x in m["lenses"] if x["key"] == "search")
    assert m["latest_week"] == week_start(TODAY).isoformat()
    assert search["available"] and search["latest_scored_week"] == LAST_FULL.isoformat()
    assert next(x for x in m["lenses"] if x["key"] == "audience")["latest_scored_week"] is None
    rows = client.get("/api/cells/trends", params={"lens": "search"}).json()["series"][str(themes["health"])]
    weeks = {r["week"] for r in rows}
    assert week_start(TODAY).isoformat() not in weeks and LAST_FULL.isoformat() in weeks
    assert (HOLE_WEEK + timedelta(weeks=2)).isoformat() not in weeks
    assert not any(r["breakdown"].get("search_missing_weeks") for r in rows)


def test_week_without_data_gets_the_median_of_the_weeks_around_it(db):
    g = _cfg(db)
    out = import_rows(db, iter(_rows(g, ["services"], weeks=12, value=lambda sl, i: 0 if i == 5 else 10 + (i % 3),
                                     has=lambda sl, i: i != 5)))  # a generator is read once
    assert out["created"] == 12 and out["weeks_filled"] == 1
    items = sorted(db.scalars(select(Item).where(Item.kind == "search")), key=lambda i: i.published_at)
    hole = items[5]
    assert not hole.extra["has_data"] and hole.extra["filled"] and hole.extra["value_raw"] == 0
    near = sorted(i.value for i in items[1:10] if i is not hole)
    assert hole.value == (near[3] + near[4]) / 2 and hole.value > 0
    assert "no data" in hole.title


def test_reimport_keeps_a_users_relevance_decision(db):
    g = _cfg(db)
    import_rows(db, _rows(g, ["economy"], weeks=4))
    items = sorted(db.scalars(select(Item).where(Item.kind == "search")), key=lambda i: i.published_at)

    def mark_irrelevant(it):  # what /items/{id}/correction does
        it.relevant = False
        it.extra = {**it.extra, "user_relevance": False}
    mark_irrelevant(items[0])
    db.commit()
    import_rows(db, _rows(g, ["economy"], weeks=4, value=lambda sl, i: 12, fetched="2026-10-23T06:00:00+00:00"))
    db.refresh(items[0])
    assert items[0].extra["user_relevance"] is False and not items[0].relevant and items[0].value == 60.0
    c = db.scalar(select(Country))
    c.config = {**c.config, "gtrends": {**g, "version": 2}}
    db.commit()
    assert import_rows(db, _rows(g, ["economy"], weeks=4))["retired"] == 3   # the three still counting
    mark_irrelevant(items[1])                                               # marked while retired
    c.config = {**c.config, "gtrends": g}
    db.commit()
    import_rows(db, _rows(g, ["economy"], weeks=4))                         # back to version 1
    for it in items:
        db.refresh(it)
    assert [it.relevant for it in items] == [False, False, True, True]
    assert items[0].extra["user_relevance"] is False and items[1].extra["user_relevance"] is False


def test_source_health_shows_when_search_data_goes_stale(client, users, db):
    from app.models import SourceRun

    login(client, "j@example.org", "journo-password-1")

    def health():
        return next(r for r in client.get("/api/sources/health").json() if r["key"] == "gtrends")
    assert health()["status"] == "never_run" and health()["stale"]
    import_rows(db, _rows(_cfg(db), ["services"], weeks=4))
    h = health()
    assert h["status"] == "ok" and not h["stale"] and "latest week with data" in h["error"]
    run = db.scalar(select(SourceRun).where(SourceRun.source_key == "gtrends"))
    run.finished_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=9)  # a weekly import, a bit late
    db.commit()
    assert not health()["stale"]
    run.finished_at -= timedelta(days=2)                                                  # 11 days: a week was missed
    db.commit()
    assert health()["stale"]


def test_gap_panel_lists_search_words_with_glosses(client, users, db):
    themes, regions = ids(db)
    login(client, "j@example.org", "journo-password-1")
    assert "search" in [x["key"] for x in client.get("/api/meta").json()["lenses"]]
    q = {"region_id": regions["national"], "lens": "search"}
    r = client.get("/api/gap", params={**q, "theme_id": themes["services"]}).json()
    assert r["search"]["measured"] and r["search"]["anchor"]["ar"] == "مطعم"
    assert {"ar": "الكهرباء", "en": "electricity"} in r["search"]["terms"]
    r = client.get("/api/gap", params={**q, "theme_id": themes["gender_violence"]}).json()
    assert not r["search"]["measured"] and r["search"]["unmeasured_reason"]
    r = client.get("/api/gap", params={"theme_id": themes["services"], "region_id": regions["national"]}).json()
    assert "search" not in r


SERPAPI_BODY = {"interest_over_time": {"timeline_data": [
    {"timestamp": _ts(SUN + timedelta(weeks=i)), "partial_data": i == 3,
     "values": [{"query": "q", "value": "0" if i == 1 else str(10 + i), "extracted_value": 0 if i == 1 else 10 + i},
                {"query": "a", "value": "20", "extracted_value": 20}]} for i in range(4)]}}


def test_keyed_providers_stay_off_without_keys(db, monkeypatch):
    g = _cfg(db)
    monkeypatch.setattr(settings, "SERPAPI_KEY", None)
    monkeypatch.setattr(settings, "GOOGLE_TRENDS_API_KEY", None)
    with pytest.raises(AwaitingKey):
        gt_collector.serpapi(g)
    with pytest.raises(AwaitingKey):
        gt_collector.official(g)
    assert "awaiting_key" in gt_collector.collect_and_import(db, provider="serpapi")
    monkeypatch.setattr(settings, "GOOGLE_TRENDS_API_KEY", "alpha-key")
    assert "error" in gt_collector.collect_and_import(db, provider="official")  # the stub, not a crash


def test_serpapi_rows_match_the_local_fetcher(db, monkeypatch):
    g = {**_cfg(db), "baskets": {"services": _cfg(db)["baskets"]["services"]}, "groups": []}
    monkeypatch.setattr(settings, "SERPAPI_KEY", "test-key")
    seen = []

    def handler(request):
        seen.append(request.url.params)
        return httpx.Response(200, json=SERPAPI_BODY)
    rows = gt_collector.serpapi(g, transport=httpx.MockTransport(handler))
    assert seen[0]["engine"] == "google_trends" and seen[0]["geo"] == "LY" and seen[0]["date"] == "today 5-y"
    assert seen[0]["q"].endswith(",مطعم") and " + " in seen[0]["q"]
    assert [r["week"] for r in rows] == [(SUN + timedelta(weeks=i, days=1)).isoformat() for i in range(3)]
    assert [r["has_data"] for r in rows] == [True, False, True] and rows[0]["provider"] == "serpapi"
    out = import_rows(db, rows, provider="serpapi")
    assert out["created"] == 3
