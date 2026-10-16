"""Integration fixes for the lenses: the search lens on the Trends page before the weekly import (X1),
and the pooled lenses' need floor, reference and availability (B1)."""
import math
from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from app import settings
from app.api.gaps import _lens_status
from app.gtrends import flag_missing_weeks
from app.imports.search_trends import import_rows
from app.ingest import load_rules, store_article
from app.models import CellWeek, Item, ItemTheme, Outlet, Theme
from app.scoring import compute, score_cell, week_start
from tests.conftest import ids, login
from tests.test_search_lens import _cfg, _rows


def _country(db):
    return db.scalar(select(Outlet.country_id).limit(1))


def _at(d: date, hour=9):
    return datetime.combine(d, datetime.min.time()) + timedelta(hours=hour)


# ---------------------------------------------------------------- X1: search lens before the import
MONDAY = date(2026, 10, 19)                       # last week has ended, the weekly import has not run
LAST_FULL = week_start(MONDAY) - timedelta(weeks=1)
IMPORTED_TO = LAST_FULL - timedelta(weeks=1)      # the last week the import brought
START = IMPORTED_TO - timedelta(weeks=29, days=1)  # the Sunday 30 weeks back
HOLE = START + timedelta(weeks=20, days=1)        # a week Google held back for health


def _search_before_import(db):
    cid = _country(db)
    rules = load_rules(db, cid)
    import_rows(db, _rows(_cfg(db), ["health", "services"], weeks=30, start=START,
                          has=lambda sl, i: not (sl == "health" and i == 20)))
    for w in range(32):
        mon = week_start(MONDAY) - timedelta(weeks=w)
        for k in range(4):
            store_article(db, cid, rules, url=f"https://old.ly/h/{w}/{k}", title=f"Libya hospital medicines shortage report {k}",
                          published_at=_at(mon + timedelta(days=k)), source_key="rss")
            store_article(db, cid, rules, url=f"https://old.ly/s/{w}/{k}", title=f"Libya power cuts and electricity blackout {k}",
                          published_at=_at(mon + timedelta(days=k)), source_key="rss")
    db.commit()
    compute(db, cid, weeks=24, today=MONDAY, lenses=("search",))
    flag_missing_weeks(db, cid)
    return cid


def test_search_week_ended_but_not_imported_has_no_usual_level(client, users, db):
    themes, regions = ids(db)
    _search_before_import(db)

    def cell(slug, wk):
        return db.scalar(select(CellWeek).where(CellWeek.theme_id == themes[slug], CellWeek.region_id == regions["national"],
                                                CellWeek.lens == "search", CellWeek.week_start == wk))
    gone = cell("health", LAST_FULL)
    assert gone.insufficient and gone.gap is None and not gone.breakdown["in_progress"]
    assert gone.breakdown["search_missing_weeks"] == [LAST_FULL.isoformat()]
    assert gone.breakdown["reason"] == "no_search_data"
    # the week still coming in keeps its reason, and a theme we do not measure keeps no_need_data
    assert cell("health", week_start(MONDAY)).breakdown["reason"] == "in_progress"
    assert cell("migration", LAST_FULL).breakdown["reason"] == "no_need_data"

    login(client, "j@example.org", "journo-password-1")
    r = client.get("/api/cells/trends", params={"lens": "search"}).json()
    rows = {x["week"]: x for x in r["themes"][str(themes["health"])]["rows"]}
    last = rows[LAST_FULL.isoformat()]
    # no usual level of 0 for the week that has ended but has not been imported
    assert not last["in_progress"] and last["need_week"] is None
    assert last["expected_week"] is None and last["ref"] is None and last["expected_4w"] is None
    assert last["gap"] is None and last["insufficient"] and last["reason"] == "no_search_data"
    scored = rows[IMPORTED_TO.isoformat()]
    assert scored["gap"] is not None and scored["expected_week"] > 0 and scored["ref"] and scored["expected_4w"] > 0
    # a week Google held back: no need or usual level that week (the import filled its need with
    # the weeks around it), and the windows holding it quote no 4-week usual level
    filled = db.scalar(select(CellWeek).where(CellWeek.theme_id == themes["health"], CellWeek.lens == "search",
                                              CellWeek.region_id == regions["national"], CellWeek.week_start == HOLE))
    assert filled.breakdown["need_week"] > 0
    hole = rows[HOLE.isoformat()]
    assert hole["need_week"] is None and hole["expected_week"] is None and hole["ref"] is None
    after = rows[(HOLE + timedelta(weeks=2)).isoformat()]
    assert after["expected_week"] is not None and after["expected_4w"] is None and after["reason"] == "no_search_data"
    # the page opens the search lens on its latest scored week
    m = client.get("/api/meta").json()
    search = next(x for x in m["lenses"] if x["key"] == "search")
    assert search["latest_scored_week"] == IMPORTED_TO.isoformat() and m["latest_week"] == LAST_FULL.isoformat()
    assert search["min_need"] == 0


# ---------------------------------------------------------------- B1: pooled lenses
NOW = date(2026, 10, 14)                          # a Wednesday
FULL = week_start(NOW) - timedelta(weeks=1)


def _coverage(db, cid, rules, weeks=30):
    """Steady coverage of three themes: 4 economy, 3 health and 1 migration articles a week."""
    for w in range(weeks):
        mon = week_start(NOW) - timedelta(weeks=w)
        for k, title in enumerate(["Libya central bank dinar liquidity", "Libya oil exports from the oilfield", "Libya fuel budget salaries",
                                   "Libya refinery crude output"]):
            store_article(db, cid, rules, url=f"https://old.ly/e/{w}/{k}", title=title, published_at=_at(mon + timedelta(days=k)),
                          source_key="rss")
        for k, title in enumerate(["Libya hospital medicines shortage", "Libya cholera vaccination campaign", "Libya doctors and nurses unpaid"]):
            store_article(db, cid, rules, url=f"https://old.ly/h/{w}/{k}", title=title, published_at=_at(mon + timedelta(days=k)),
                          source_key="rss")
        store_article(db, cid, rules, url=f"https://old.ly/m/{w}", title="Migrants rescued at sea off Libya",
                      published_at=_at(mon + timedelta(days=1)), source_key="rss")


def _report(db, cid, theme_id, day, n=1):
    for i in range(n):
        it = Item(country_id=cid, kind="report", source_key="official", dedupe_key=f"rw:{theme_id}:{day}:{i}",
                  title="ReliefWeb update", published_at=_at(day, 10 + i), value=1.0)
        db.add(it)
        db.flush()
        db.add(ItemTheme(item_id=it.id, theme_id=theme_id, method="rule"))


def _hum(db, themes, regions, slug, wk):
    return db.scalar(select(CellWeek).where(CellWeek.theme_id == themes[slug], CellWeek.region_id == regions["national"],
                                            CellWeek.lens == "humanitarian", CellWeek.week_start == wk))


def _available(db, cid):
    latest = db.scalar(select(func.max(CellWeek.week_start)).where(CellWeek.country_id == cid))
    themes = db.scalars(select(Theme).where(Theme.active.is_(True)).order_by(Theme.id)).all()
    return _lens_status(db, cid, latest, themes)[0]


def test_one_report_is_not_a_humanitarian_gap(db):
    themes, regions = ids(db)
    cid = _country(db)
    _coverage(db, cid, load_rules(db, cid))
    _report(db, cid, themes["migration"], FULL + timedelta(days=1))
    db.commit()
    compute(db, cid, weeks=16, today=NOW, lenses=("humanitarian",))
    cells = db.scalars(select(CellWeek).where(CellWeek.lens == "humanitarian")).all()
    assert cells and not any(c.gap is not None or not c.insufficient for c in cells)
    mig = _hum(db, themes, regions, "migration", FULL)
    assert mig.need == 1 and mig.breakdown["reason"] == "too_little_need"
    # the reference pools only the themes with reports: migration's own articles, not 13 themes' over one report
    assert math.isclose(mig.breakdown["expected_4w"], mig.breakdown["articles_4w"])
    assert "humanitarian" not in _available(db, cid)
    assert score_cell(10, 1, 50.0, min_need=settings.MIN_NEED_UNITS["humanitarian"]).reason == "too_little_need"


def test_pooled_reference_and_availability_need_more_than_two_themes(db):
    themes, regions = ids(db)
    cid = _country(db)
    _coverage(db, cid, load_rules(db, cid))
    for w in range(1, 9):                         # 2 reports a week on migration and health for 8 weeks
        for slug in ("migration", "health"):
            _report(db, cid, themes[slug], week_start(NOW) - timedelta(weeks=w, days=-2), n=2)
    db.commit()
    compute(db, cid, weeks=16, today=NOW, lenses=("humanitarian",))
    mig, health = _hum(db, themes, regions, "migration", FULL), _hum(db, themes, regions, "health", FULL)
    assert not mig.insufficient and not health.insufficient
    # economy has no reports, so its articles stay out of the reference: the two themes balance out
    ref = (mig.breakdown["articles_4w"] + health.breakdown["articles_4w"]) / (mig.need + health.need)
    assert math.isclose(mig.ref_ratio, ref) and math.isclose(health.ref_ratio, ref)
    assert mig.gap > 0 > health.gap                                # 1 against 3 articles a week, same reports
    A = settings.PRIOR_ARTICLES
    assert math.isclose(mig.gap, math.log((ref * mig.need + A) / (mig.breakdown["articles_4w"] + A)))
    assert _hum(db, themes, regions, "economy", FULL).breakdown["reason"] == "no_need_data"
    # judged in 4 or more of the last 12 weeks, but 2 themes of 13 are not a pooled lens
    assert "humanitarian" not in _available(db, cid)
    for slug in ("economy", "security", "services"):
        for w in range(1, 9):
            _report(db, cid, themes[slug], week_start(NOW) - timedelta(weeks=w, days=-2), n=2)
    db.commit()
    compute(db, cid, weeks=16, today=NOW, lenses=("humanitarian",))
    assert "humanitarian" in _available(db, cid)                   # 5 of 13 themes: a third
