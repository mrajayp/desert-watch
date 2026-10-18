from datetime import timedelta

from sqlalchemy import select

from app.ingest import load_rules, store_article
from app.models import Country, utcnow

from .conftest import login


def test_contribute_queues_and_tally(client, users, db):
    c = db.scalar(select(Country))
    rules = load_rules(db, c.id)
    when = utcnow() - timedelta(days=1)
    # no theme -> "untagged"; theme but no place -> "unplaced"
    store_article(db, c.id, rules, url="https://ex.ly/u1", title="خبر عام من ليبيا", published_at=when, source_key="rss")
    store_article(db, c.id, rules, url="https://ex.ly/u2", title="Libya hospital shortage of medicines",
                  published_at=when, source_key="rss")
    db.commit()
    login(client, "j@example.org", "journo-password-1")
    d = client.get("/api/contribute").json()
    assert d["can_contribute"] is True
    assert d["untagged"]["total"] >= 1 and d["unplaced"]["total"] >= 1
    assert d["mine"]["suggestions"] == 0
    r = client.post("/api/suggestions", json={"kind": "source", "payload": {"url": "https://example.ly", "note": "local radio"}})
    assert r.status_code == 200
    d = client.get("/api/contribute").json()
    assert d["mine"]["suggestions"] == 1 and d["my_suggestions"][0]["kind"] == "source"


def test_contribute_gaps_start_at_the_red_threshold_and_carry_the_scored_count(client, users, db):
    from datetime import date
    from app import settings
    from app.api.contribute import GAP_MIN
    from app.models import CellWeek, Region, Theme
    assert GAP_MIN == settings.GAP_RED_FROM == 0.4
    c = db.scalar(select(Country))
    nat = db.scalar(select(Region.id).where(Region.country_id == c.id, Region.level == "national"))
    t1, t2, t3, t4 = db.scalars(select(Theme.id).where(Theme.active.is_(True)).order_by(Theme.id).limit(4)).all()
    wk = date(2026, 10, 5)
    # t1 0.3: fewer than expected, but not red. t2 0.5 with no verdict (scored before verdicts existed):
    # red by the threshold. t3 0.6 judged usual (a shortfall chance would explain): not red. t4 0.45
    # judged short: red, with the evidence its sentence is built from.
    for tid, gap, scored, every, verdict, extra in ((t1, 0.3, 9, 15, None, {}), (t2, 0.5, 7, 12, None, {}),
                                                     (t3, 0.6, 5, 8, "usual", {"expected_4w": 9.0, "chance": None}),
                                                     (t4, 0.45, 12, 20, "short", {"expected_4w": 31.0, "ratio_lo": 1.8, "ratio_hi": 3.6,
                                                                                  "chance": 50, "baseline_backfilled": True})):
        db.add(CellWeek(country_id=c.id, theme_id=tid, region_id=nat, week_start=wk, lens="audience", need=1000,
                        coverage=every, gap=gap, insufficient=False, flags=[], verdict=verdict,
                        breakdown={"articles_4w": scored, "scored_coverage": scored, **extra}))
    db.commit()
    login(client, "j@example.org", "journo-password-1")
    gaps = client.get("/api/contribute").json()["gaps"]
    assert [g["theme_id"] for g in gaps] == [t2, t4]
    assert gaps[0]["articles"] == 7 and gaps[0]["articles_all"] == 12 and gaps[0]["coverage"] == 12
    assert gaps[0]["verdict"] is None and gaps[0]["chance"] is None and gaps[0]["expected_4w"] is None
    short = gaps[1]
    assert short["verdict"] == "short" and short["expected_4w"] == 31.0 and short["chance"] == 50
    assert short["ratio_lo"] == 1.8 and short["ratio_hi"] == 3.6 and short["baseline_backfilled"] is True


def test_old_methods_route_redirects_to_the_content_route(client, users):
    # /api/admin/methods became GET /api/content/how_the_numbers_work; the old path redirects for one release
    login(client, "admin@example.org", "admin-password-1")
    r = client.get("/api/admin/methods", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/api/content/how_the_numbers_work"
    md = client.get("/api/admin/methods").json()["markdown"]
    assert md.startswith("# How the numbers work") and "gap score" in md
