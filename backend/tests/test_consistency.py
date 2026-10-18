"""One count per cell on every page: /api/cells, /api/cells/trends, the gap detail, the digest facts
and the article lists all count the same stories (A-R1.1, A-R1.2, A-R1.6, A-R1.7)."""
from datetime import date, datetime, timedelta

from sqlalchemy import select

from app import digest, settings
from app.ingest import load_rules, store_article
from app.models import CellWeek, Country
from app.recurring import mark_recurring
from app.scoring import compute, week_start
from tests.conftest import login
from tests.test_dedupe_stable import _two_routes


def test_every_page_shows_the_same_scored_count_for_a_cell(client, users, db):
    today = date(2026, 10, 12)
    themes, regions, cid = _two_routes(db, today)          # 2 stories a week, one of them found by two routes
    rules = load_rules(db, cid)
    for d in range(8):                                     # plus a daily post that must count nowhere
        when = datetime.combine(today + timedelta(days=6 - d), datetime.min.time()) + timedelta(hours=7)
        store_article(db, cid, rules, url=f"https://libyaobserver.ly/daily/{d}",
                      title=f"Sabha hospital daily bulletin {when.strftime('%A')} {when.day} October", published_at=when,
                      source_key="gnews")
    db.commit()
    now = today + timedelta(days=7)
    assert mark_recurring(db, now=datetime.combine(now, datetime.min.time()))["marked"] == 8
    compute(db, cid, weeks=56, today=now)
    wk = week_start(today)
    login(client, "admin@example.org", "admin-password-1")
    # the map / overview cell
    cells = client.get("/api/cells", params={"lens": "audience", "week": wk.isoformat()}).json()["cells"]
    cell = next(c for c in cells if c["theme_id"] == themes["health"] and c["region_id"] == regions["national"])
    assert cell["articles"] == 8 and cell["articles_all"] == 8 and cell["coverage"] == 8
    # the Trends page: the 4-week count and the bars behind it
    rows = client.get("/api/cells/trends", params={"lens": "audience"}).json()["themes"][str(themes["health"])]["rows"]
    i = next(k for k, x in enumerate(rows) if x["week"] == wk.isoformat())
    assert rows[i]["articles_4w"] == cell["articles"] == sum(x["articles"] for x in rows[i - 3:i + 1])
    # the gap panel and its list
    g = client.get("/api/gap", params={"theme_id": themes["health"], "region_id": regions["national"], "lens": "audience",
                                       "week": wk.isoformat()}).json()
    assert g["cell"]["articles"] == cell["articles"] and g["articles"]["total"] == cell["articles_all"]
    # the digest facts: the gap row and the per-theme count, both scored, with the previous window on the same outlets
    facts = digest.build_facts(db, db.get(Country, cid), wk)
    top = next(x for x in facts["top_gaps"] if x["theme"] == "Health" and x["region"] == "Libya")
    assert top["articles"] == cell["articles"] and top["articles_all"] == cell["articles_all"]
    cov = next(x for x in facts["coverage_by_theme"] if x["theme"] == "Health")
    assert cov["articles"] == 8 and cov["articles_all"] == 8 and cov["previous_window"] == 8 and cov["english"] == 8
    assert digest.COUNTS_LIMIT in facts["known_limits"]
    # the stored cell says the same
    stored = db.scalar(select(CellWeek).where(CellWeek.theme_id == themes["health"], CellWeek.region_id == regions["national"],
                                              CellWeek.lens == "audience", CellWeek.week_start == wk))
    assert stored.breakdown["articles_4w"] == 8 and stored.breakdown["prev_scored_coverage"] == 8
    assert stored.breakdown["scored_lang"] == {"en": 8}
    # one red threshold everywhere
    assert client.get("/api/meta").json()["red_from"] == settings.GAP_RED_FROM == 0.4
    from app.api.contribute import GAP_MIN
    assert GAP_MIN == settings.GAP_RED_FROM
