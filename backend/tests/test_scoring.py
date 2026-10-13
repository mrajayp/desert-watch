from collections import Counter
from datetime import date, datetime, timedelta

from sqlalchemy import select

from app.ingest import load_rules, store_article
from app.models import CellWeek, Item, ItemTheme, Outlet, OutletCategory
from app.scoring import CoverageAgg, compute, coverage_flags, score_cell, week_start
from tests.conftest import ids


def test_score_cell_known_gap_and_covered():
    # reference: 1 article per 100 need units
    gap = score_cell(coverage=2, need=1000, ref_ratio=0.01, min_need=10, shrink=10)
    ok = score_cell(coverage=10, need=1000, ref_ratio=0.01, min_need=10, shrink=10)
    over = score_cell(coverage=40, need=1000, ref_ratio=0.01, min_need=10, shrink=10)
    assert gap.gap > 1.0
    assert abs(ok.gap) < 0.05
    assert over.gap < 0
    assert not gap.insufficient


def test_small_counts_insufficient():
    s = score_cell(coverage=0, need=2, ref_ratio=0.01, min_need=3, shrink=10)
    assert s.insufficient and s.gap is None


def test_shrinkage_pulls_small_cells_to_reference():
    small = score_cell(coverage=0, need=5, ref_ratio=0.5, min_need=3, shrink=10)
    big = score_cell(coverage=0, need=500, ref_ratio=0.5, min_need=3, shrink=10)
    assert 0 < small.gap < big.gap


def test_flags():
    cur = CoverageAgg(total=6, lang=Counter(en=6), scope=Counter(international=6),
                      alignment=Counter(east_lna_aligned=4, unknown=2))
    f = coverage_flags(cur, prev_cov=20, need=100, prev_need=100)
    assert "coverage_drop" in f and "little_arabic" in f and "outside_only" in f
    assert "partisan_only:east_lna_aligned" in f
    cur.alignment["independent"] = 1
    assert not any(x.startswith("partisan_only") for x in coverage_flags(cur, 0, 0, 0))


def _pageviews(db, country_id, theme_id, day, views):
    it = Item(country_id=country_id, kind="pageview", source_key="wikipedia",
              dedupe_key=f"wiki:test:{theme_id}:{day}", title="t", published_at=datetime.combine(day, datetime.min.time()),
              value=views)
    db.add(it)
    db.flush()
    db.add(ItemTheme(item_id=it.id, theme_id=theme_id, method="query"))


def test_compute_end_to_end_audience_and_partisan(db):
    themes, regions = ids(db)
    country_id = db.scalar(select(Outlet.country_id).limit(1))
    rules = load_rules(db, country_id)
    today = date(2026, 10, 12)
    # 16 weeks of steady interest + coverage for health, then coverage collapses in the last 4 weeks
    for w in range(28):
        day = week_start(today) - timedelta(weeks=w)
        _pageviews(db, country_id, themes["health"], day, 2000)
        if w >= 4:
            for k in range(5):
                store_article(db, country_id, rules, url=f"https://ex.com/h/{w}/{k}", title="Hospital shortages in Sabha",
                              published_at=datetime.combine(day, datetime.min.time()), source_key="test")
    out = db.scalar(select(Outlet).where(Outlet.domain == "ex.com"))
    db.add(OutletCategory(outlet_id=out.id, dimension="alignment", value="east_lna_aligned", confidence="reported",
                          evidence_url="https://example.org/study"))
    db.commit()
    n = compute(db, country_id, weeks=12, today=today)
    assert n > 0
    nat = regions["national"]
    last = db.scalar(select(CellWeek).where(CellWeek.theme_id == themes["health"], CellWeek.region_id == nat,
                                            CellWeek.lens == "audience", CellWeek.week_start == week_start(today)))
    mid = db.scalar(select(CellWeek).where(CellWeek.theme_id == themes["health"], CellWeek.region_id == nat,
                                           CellWeek.lens == "audience", CellWeek.week_start == week_start(today) - timedelta(weeks=8)))
    assert last.gap is not None and last.gap > 0.5          # coverage collapsed vs its own history
    assert mid.gap is not None and abs(mid.gap) < 0.3        # steady state
    assert "coverage_drop" in last.flags
    # 'Sabha' in titles puts coverage on the district, but no lens has regional need data yet,
    # and the audience lens is national-only: so regional cells exist but are all insufficient.
    sabha_cells = db.scalars(select(CellWeek).where(CellWeek.region_id == regions["sabha"])).all()
    assert sabha_cells and all(c.insufficient and c.lens != "audience" for c in sabha_cells)
    assert any(f.startswith("partisan_only") for f in mid.flags)


def test_cold_start_baseline_never_predates_collection(db):
    """Articles only for the last 6 weeks, pageviews for 30: the audience baseline must not
    count pre-collection weeks as 'zero coverage' (which would make every theme look over-covered)."""
    themes, regions = ids(db)
    country_id = db.scalar(select(Outlet.country_id).limit(1))
    rules = load_rules(db, country_id)
    today = date(2026, 10, 12)
    for w in range(30):
        day = week_start(today) - timedelta(weeks=w)
        _pageviews(db, country_id, themes["economy"], day, 3000)
        if w < 6:
            for k in range(6):
                store_article(db, country_id, rules, url=f"https://ex.com/e/{w}/{k}", title="Oil exports and the central bank",
                              published_at=datetime.combine(day, datetime.min.time()), source_key="test")
    db.commit()
    compute(db, country_id, weeks=12, today=today)
    rows = db.scalars(select(CellWeek).where(CellWeek.theme_id == themes["economy"], CellWeek.region_id == regions["national"],
                                             CellWeek.lens == "audience")).all()
    assert rows and all(r.insufficient and r.breakdown["building_baseline"] for r in rows)
    assert not any("coverage_drop" in r.flags for r in rows)
