"""Collection drift (A-R2.3) and basis honesty (A-R2.4 b, c): the Sunday re-query of Google News, the
backfilled-baseline flag with its widened interval, a closed outlet's loss shown as a real drop, and
the nightly list of source|outlet pairs that left the comparison."""
import json
import math
import subprocess
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from app import joblock, settings
from app.collectors import EXTRA_HEALTH, STALE_HOURS
from app.ingest import load_rules, store_article
from app.models import BasisDeparture, CellWeek, Item, Outlet, SourceRun
from app.scoring import EVIDENCE_KEYS, backfilled_weeks, comparable_pairs, compute, record_departures, week_start
from tests.conftest import ids, login
from tests.test_rules import GNEWS_RSS, _Resp
from tests.test_scoring import _pageviews


# ---------------------------------------------------------------- the Sunday re-query
def test_settle_windows_are_the_calendar_weeks_that_ended_2_3_and_4_weeks_ago():
    from app.collectors.gnews import settle_windows
    assert settle_windows(date(2026, 11, 1)) == [(date(2026, 10, 12), date(2026, 10, 19)),
                                                (date(2026, 10, 5), date(2026, 10, 12)),
                                                (date(2026, 9, 28), date(2026, 10, 5))]
    assert settle_windows(date(2026, 11, 4), (2,)) == [(date(2026, 10, 19), date(2026, 10, 26))]   # a Wednesday: same weeks


def test_settle_requeries_both_languages_and_updates_without_duplicates(db, monkeypatch):
    from app.collectors import gnews
    asked = []

    def fake_get(client, url, *, params=None, **kw):
        asked.append(params)
        return _Resp(GNEWS_RSS)
    monkeypatch.setattr(gnews, "polite_get", fake_get)
    res = gnews.settle(db, today=date(2026, 11, 1), themes=["security"])
    db.commit()
    assert res.rows == 1 and res.errors == 0
    assert "3 weeks (2026-09-28 to 2026-10-18) searched again" in res.detail and "1 new articles" in res.detail
    windows = {(p["hl"], q.split("after:")[1]) for p in asked for q in [p["q"]]}
    for after in ("2026-10-12 before:2026-10-19", "2026-10-05 before:2026-10-12", "2026-09-28 before:2026-10-05"):
        assert ("ar", after) in windows and ("en-GB", after) in windows
    # the same answer again: the stored article is updated (its query recorded), never stored twice
    n_asked = len(asked)
    res2 = gnews.settle(db, today=date(2026, 11, 1), themes=["security"])
    assert res2.rows == 0 and len(asked) == 2 * n_asked
    assert f"{n_asked} already stored" in res2.detail
    items = db.scalars(select(Item).where(Item.url == "https://news.google.com/rss/articles/zaw1")).all()
    assert len(items) == 1 and items[0].extra["queries"] == {"security": "gnews:security"}
    assert db.scalar(select(Item.id).where(Item.source_key == "gnews", Item.id != items[0].id)) is None


def test_settle_job_runs_as_a_child_under_the_lock_and_records_its_outcome(db, monkeypatch):
    from app import jobs
    calls = []

    def fake_child(source_key, *args, **kw):
        calls.append((source_key, args, joblock.is_held(), joblock.holder()["job"]))
        return {"changed": 3}
    monkeypatch.setattr(jobs, "child_job", fake_child)
    assert jobs.gnews_settle() == {"changed": 3}
    assert calls == [("gnews_settle", ("gnews-settle", "--weeks-ago", "2,3,4"), True, "gnews_settle")]
    assert joblock.holder() is None
    jobs.JOBS["gnews_settle"]()
    assert calls[-1][1] == ("gnews-settle", "--weeks-ago", "2,3,4")
    # the child's own outcome (a collector's partial run and its note) reaches the source_run line
    monkeypatch.undo()
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(
        cmd, 0, stdout='{"changed": 2, "status": "partial", "detail": "3 weeks searched again; security/en: boom"}\n', stderr=""))
    out = jobs.child_job("gnews_settle", "gnews-settle", "--weeks-ago", "2")
    assert out["changed"] == 2
    run = db.scalar(select(SourceRun).where(SourceRun.source_key == "gnews_settle").order_by(SourceRun.id.desc()))
    assert (run.status, run.rows, run.ok) == ("partial", 2, False) and "security/en: boom" in run.error
    assert "gnews_settle" in EXTRA_HEALTH and STALE_HOURS["gnews_settle"] == 8 * 24   # on the health strip, stale after 8 days


def test_cli_gnews_settle_prints_the_line_the_child_job_reads(db, monkeypatch, capsys):
    from app.cli import main
    from app.collectors import gnews
    monkeypatch.setattr(gnews, "polite_get", lambda *a, **k: _Resp(GNEWS_RSS))
    assert main(["gnews-settle", "--weeks-ago", "2"]) == 0
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["status"] == "ok" and line["changed"] == 1 and "1 weeks" in line["detail"]


# ---------------------------------------------------------------- backfilled baselines
def _history(db, country_id, theme_id, today, weeks=30, per_week=5, late_from=None, source="rss"):
    """Steady interest and coverage; weeks `late_from` and older were first seen 30 days after publication
    (searched back for), the rest the next day (collected live)."""
    rules = load_rules(db, country_id)
    for w in range(weeks):
        day = datetime.combine(week_start(today) - timedelta(weeks=w), datetime.min.time()) + timedelta(hours=9)
        _pageviews(db, country_id, theme_id, day.date(), 2000)
        for k in range(per_week):
            it, _ = store_article(db, country_id, rules, url=f"https://ex.com/h/{w}/{k}", title="Hospital shortages in Sabha",
                                  published_at=day + timedelta(hours=k), source_key=source)
            it.created_at = day + timedelta(days=30 if late_from is not None and w >= late_from else 1)
    db.commit()


def test_backfilled_weeks_are_the_ones_whose_median_article_came_in_late(db):
    themes, _ = ids(db)
    country_id = db.scalar(select(Outlet.country_id).limit(1))
    today = date(2026, 10, 12)
    _history(db, country_id, themes["health"], today, weeks=10, late_from=6)
    weeks = backfilled_weeks(db, country_id, week_start(today) - timedelta(weeks=12), today + timedelta(days=7))
    assert weeks == {week_start(today) - timedelta(weeks=w) for w in range(6, 10)}
    # a week with a late minority is not backfilled: the median article of the week decides
    rules = load_rules(db, country_id)
    wk = week_start(today) - timedelta(weeks=2)
    for k in range(2):
        it, _ = store_article(db, country_id, rules, url=f"https://ex.com/late/{k}", title="Hospital shortages in Sabha",
                              published_at=datetime.combine(wk, datetime.min.time()) + timedelta(hours=12 + k), source_key="rss")
        it.created_at = datetime.combine(wk, datetime.min.time()) + timedelta(days=25)
    db.commit()
    assert wk not in backfilled_weeks(db, country_id, wk, wk + timedelta(days=7))


def test_a_backfilled_baseline_widens_the_interval_and_the_flag_expires_on_its_own(db):
    themes, regions = ids(db)
    country_id = db.scalar(select(Outlet.country_id).limit(1))
    today = date(2026, 10, 12)
    nat = regions["national"]

    def cell(wk):
        return db.scalar(select(CellWeek).where(CellWeek.theme_id == themes["health"], CellWeek.region_id == nat,
                                                CellWeek.lens == "audience", CellWeek.week_start == wk))
    # every week collected live: no flag, no widening
    _history(db, country_id, themes["health"], today, weeks=30)
    compute(db, country_id, weeks=14, today=today + timedelta(days=7))   # weeks 12 back to the one in progress
    live = {w: cell(week_start(today) - timedelta(weeks=w)) for w in (0, 12)}
    assert all(c.gap is not None and c.breakdown["baseline_backfilled"] is False and c.breakdown["drift_se"] == 0
               for c in live.values())
    base = {w: (c.breakdown["se_g"], c.breakdown["ratio_lo"], c.breakdown["ratio_hi"], c.verdict) for w, c in live.items()}
    # the weeks 20 and more weeks ago were searched back for: the oldest judged cell's baseline (weeks 16
    # to 27 before it... 4 to 15 before the cell) holds them, the latest cell's baseline is all live
    for it in db.scalars(select(Item).where(Item.kind == "article")):
        if it.published_at < datetime.combine(week_start(today) - timedelta(weeks=19), datetime.min.time()):
            it.created_at = it.published_at + timedelta(days=30)
    db.commit()
    compute(db, country_id, weeks=14, today=today + timedelta(days=7))
    old, new = cell(week_start(today) - timedelta(weeks=12)), cell(week_start(today))
    drift = round(settings.DRIFT_PER_WEEK * settings.DRIFT_LAG_WEEKS, 4)
    assert drift == round(math.log(391 / 182) / 52 * 8, 4) and 0.11 < drift < 0.13   # the measured drift, 8 weeks of it
    assert old.breakdown["baseline_backfilled"] is True and old.breakdown["drift_se"] == drift
    assert old.breakdown["se_g"] == pytest.approx(base[12][0] + drift, abs=2e-4)
    assert old.breakdown["ratio_lo"] < base[12][1] and old.breakdown["ratio_hi"] > base[12][2]
    assert old.breakdown["p_low"] == live[12].breakdown["p_low"] and old.verdict == base[12][3]   # the verdict does not move
    assert new.breakdown["baseline_backfilled"] is False and new.breakdown["drift_se"] == 0
    assert (new.breakdown["se_g"], new.breakdown["ratio_lo"]) == (base[0][0], base[0][1])
    assert "drift_se" in EVIDENCE_KEYS   # cleared with the rest when a search cell loses its judgement


def test_cell_evidence_adds_the_drift_to_the_standard_error_only(db):
    from app.scoring import cell_evidence
    plain = cell_evidence(40, 20, 0.3, [10, 10, 10, 10], [10] * 12)
    wide = cell_evidence(40, 20, 0.3, [10, 10, 10, 10], [10] * 12, drift_se=0.1)
    assert (wide["p_low"], wide["p_high"], wide["chance"], wide["variance"]) == (plain["p_low"], plain["p_high"], plain["chance"], plain["variance"])
    assert wide["se_g"] == pytest.approx(plain["se_g"] + 0.1, abs=1e-4) and wide["drift_se"] == 0.1 and plain["drift_se"] == 0
    assert wide["ratio_lo"] < plain["ratio_lo"] < plain["ratio_hi"] < wide["ratio_hi"]


# ---------------------------------------------------------------- a closed outlet
def _steady_plus_one_that_stops(db, country_id, theme_id, today, stops_at=5, weeks=20):
    """A feed outlet steady all along (4 a week) and a second outlet found by Google News (10 a week)
    until `stops_at` weeks ago, silent since."""
    rules = load_rules(db, country_id)
    for w in range(weeks):
        day = datetime.combine(week_start(today) - timedelta(weeks=w), datetime.min.time()) + timedelta(hours=9)
        _pageviews(db, country_id, theme_id, day.date(), 2000)
        for k in range(4):
            it, _ = store_article(db, country_id, rules, url=f"https://ex.com/f/{w}/{k}", title="Hospital shortages in Sabha",
                                  published_at=day + timedelta(hours=k), source_key="rss")
            it.created_at = day + timedelta(days=1)
        if w >= stops_at:
            for k in range(10):
                it, _ = store_article(db, country_id, rules, url=f"https://news.google.com/rss/articles/gone{w}-{k}",
                                      outlet_domain="gone.ly", title=f"Hospital medicines shortage Libya {k}",
                                      published_at=day + timedelta(hours=k), source_key="gnews")
                it.created_at = day + timedelta(days=1)
    db.commit()
    return db.scalar(select(Outlet).where(Outlet.domain == "gone.ly"))


def test_a_closed_outlet_stays_in_the_basis_so_its_loss_is_a_flagged_drop(db):
    themes, regions = ids(db)
    country_id = db.scalar(select(Outlet.country_id).limit(1))
    today = date(2026, 10, 12)
    gone = _steady_plus_one_that_stops(db, country_id, themes["health"], today)
    nat = regions["national"]

    def cell(w):
        return db.scalar(select(CellWeek).where(CellWeek.theme_id == themes["health"], CellWeek.region_id == nat,
                                                CellWeek.lens == "audience", CellWeek.week_start == week_start(today) - timedelta(weeks=w)))
    # as before: the outlet that stopped leaves the whole basis, its loss never shows (A8)
    compute(db, country_id, weeks=13, today=today + timedelta(days=7))
    quiet = cell(0)
    assert quiet.breakdown["scored_outlets"] == 1 and abs(quiet.gap) < 0.3 and "outlet_closed" not in quiet.flags
    assert "coverage_drop" not in quiet.flags
    # marked closed: its earlier articles still count, so the window is short against them
    gone.closed_on = week_start(today) - timedelta(weeks=5) + timedelta(days=3)
    db.commit()
    compute(db, country_id, weeks=13, today=today + timedelta(days=7))
    last = cell(0)
    assert last.breakdown["articles_4w"] == 16 and last.breakdown["expected_4w"] > 40   # 14 a week expected, 4 found
    assert last.gap > 0.5 and last.verdict == "short"
    assert "outlet_closed" in last.flags and "coverage_drop" in last.flags
    # a cell whose compared span ends before the closure says nothing about it; one 11 weeks after it still does
    assert "outlet_closed" not in cell(8).flags and "outlet_closed" in cell(2).flags
    # the pair is comparable with the closure, not without
    assert ("gnews", gone.id) in comparable_pairs(db, country_id, week_start(today) - timedelta(weeks=15), week_start(today))
    assert ("gnews", gone.id) not in comparable_pairs(db, country_id, week_start(today) - timedelta(weeks=15), week_start(today), closed={})


def test_admin_sets_and_clears_closed_on(client, users, db):
    country_id = db.scalar(select(Outlet.country_id).limit(1))
    o = Outlet(country_id=country_id, name="Gone", domain="gone.ly", languages=["ar"], created_via="auto")
    db.add(o)
    db.commit()
    login(client, "j@example.org", "journo-password-1")
    assert client.patch(f"/api/outlets/{o.id}", json={"closed_on": "2026-09-30"}).status_code == 403
    client.post("/api/auth/logout")
    login(client, "admin@example.org", "admin-password-1")
    assert client.patch(f"/api/outlets/{o.id}", json={"closed_on": "2099-01-01"}).status_code == 400
    assert client.patch(f"/api/outlets/{o.id}", json={"closed_on": "2099-01-01"}, headers={"X-Lang": "ar"}).json()["detail"] == \
        "لا يمكن أن يكون تاريخ الإغلاق في المستقبل."
    assert client.patch(f"/api/outlets/{o.id}", json={"closed_on": "2026-09-30"}).status_code == 200
    assert client.get(f"/api/outlets/{o.id}").json()["closed_on"] == "2026-09-30"
    # an outlet with no counted article in a year is dormant and left out of the list unless asked for
    assert not any(x["id"] == o.id for x in client.get("/api/outlets").json())
    assert next(x for x in client.get("/api/outlets", params={"show_dormant": 1}).json() if x["id"] == o.id)["closed_on"] == "2026-09-30"
    assert client.patch(f"/api/outlets/{o.id}", json={"closed_on": None}).status_code == 200
    assert client.get(f"/api/outlets/{o.id}").json()["closed_on"] is None
    assert client.patch(f"/api/outlets/{o.id}", json={"base_country": "Tunisia"}).status_code == 200   # other fields untouched
    db.expire_all()
    assert db.get(Outlet, o.id).closed_on is None


# ---------------------------------------------------------------- pairs that left the comparison
def test_departures_are_listed_shown_to_admins_and_told_to_the_digest(client, users, db):
    from app import digest
    from app.models import Country
    themes, _ = ids(db)
    country = db.scalar(select(Country))
    today = date(2026, 10, 12)
    gone = _steady_plus_one_that_stops(db, country.id, themes["health"], today, stops_at=4, weeks=60)
    assert record_departures(db, today=today + timedelta(days=7)) == 1
    d = db.scalar(select(BasisDeparture))
    assert (d.source_key, d.outlet_id, d.articles) == ("gnews", gone.id, 560)
    assert d.last_day == week_start(today) - timedelta(weeks=4) and d.first_day == week_start(today) - timedelta(weeks=59)
    login(client, "admin@example.org", "admin-password-1")
    h = client.get("/api/admin/health").json()
    assert h["basis_departures_weeks"] == 4 and h["basis_departures_at"]
    assert [(x["outlet"], x["source"], x["last_day"]) for x in h["basis_departures"]] == \
        [("gone.ly", "gnews", (week_start(today) - timedelta(weeks=4)).isoformat())]
    facts = digest.build_facts(db, country, week_start(today))
    assert any(x.startswith("1 outlet left the comparison in the last 4 weeks") for x in facts["known_limits"])
    # the steady feed is not a departure; a closed outlet is kept in the basis, so it is not one either
    gone.closed_on = week_start(today) - timedelta(weeks=4)
    db.commit()
    assert record_departures(db, today=today + timedelta(days=7)) == 0
    assert client.get("/api/admin/health").json()["basis_departures"] == []
    assert not any("left the comparison" in x for x in digest.build_facts(db, country, week_start(today))["known_limits"])
    # a pair whose last article is older than DEPARTURE_WEEKS past the cut is no longer "recent"
    gone.closed_on = None
    db.commit()
    assert record_departures(db, today=today + timedelta(weeks=8)) == 0


def test_nightly_records_departures_and_the_admin_can_run_it(db, monkeypatch):
    import inspect
    from app import jobs
    seen = []
    monkeypatch.setattr(jobs.scoring, "record_departures", lambda s, *a, **k: seen.append(joblock.is_held()) or 0)
    assert jobs.JOBS["basis_departures"]() == 0 and seen == [True]     # under the lock, like every writing job
    nightly = inspect.getsource(jobs).split("def nightly():", 1)[1].split("\ndef ", 1)[0]
    assert "_record_departures()" in nightly
