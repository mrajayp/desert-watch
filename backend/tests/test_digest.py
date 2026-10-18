from datetime import date, datetime
from types import SimpleNamespace

from sqlalchemy import select

from app import digest
from app.ingest import load_rules, store_article
from app.models import Country, Digest, Outlet


class FakeMessages:
    def __init__(self, stop_reason="end_turn"):
        self.stop_reason = stop_reason
        self.last = None

    def create(self, **kw):
        self.last = kw
        return SimpleNamespace(
            stop_reason=self.stop_reason, stop_details=SimpleNamespace(category="cyber"),
            usage=SimpleNamespace(input_tokens=1200, output_tokens=300),
            content=[SimpleNamespace(type="thinking", thinking=""),
                     SimpleNamespace(type="text", text="## This week in brief\nFacts only.\n===ARABIC===\n## الأسبوع باختصار\nوقائع فقط.")])


def test_digest_builds_facts_and_stores_text(db, monkeypatch):
    country = db.scalar(select(Country))
    rules = load_rules(db, country.id)
    store_article(db, country.id, rules, url="https://ex.ly/g1", title="مقتل امرأة في سبها",
                  published_at=datetime(2026, 10, 7), source_key="test")
    db.commit()
    fake = FakeMessages()
    monkeypatch.setattr(digest, "_client", lambda: SimpleNamespace(messages=fake))
    d = digest.generate(db, country, week=date(2026, 10, 5))
    assert d.status == "ok" and d.content_md.startswith("## This week in brief")
    assert d.usage == {"input_tokens": 1200, "output_tokens": 300}
    f = d.facts
    assert f["window"].startswith("2026-09-")
    gv = next(c for c in f["coverage_by_theme"] if c["theme"].startswith("Gender: violence"))
    assert gv["articles"] == 1 and gv["arabic"] == 1
    # the week was never scored: the counts are from every source, and the facts say so
    assert gv["articles_all"] == 1 and gv["previous_window"] == 0 and digest.UNSCORED_LIMIT in f["known_limits"]
    assert "Sabha" not in f["districts_with_no_monitored_articles"]
    assert fake.last["model"] == "claude-haiku-5-5" and "Never name any person" in fake.last["system"]
    assert d.content_md == "## This week in brief\nFacts only." and d.content_md_ar == "## الأسبوع باختصار\nوقائع فقط."
    assert "===ARABIC===" in fake.last["system"] and "## الأسبوع باختصار" in fake.last["system"]
    # cached: a second call does not re-run the model
    fake.last = None
    assert digest.generate(db, country, week=date(2026, 10, 5)).id == d.id and fake.last is None


def test_digest_compares_like_with_like_once_the_week_is_scored(db):
    """A feed all along; Google Alerts start two weeks ago and add many articles. The digest's counts
    for this window and the previous one are the scored counts (the same outlets in both), beside the
    all-source counts, and the facts say which is which."""
    from datetime import timedelta
    from app.models import CellWeek
    from app.scoring import compute, week_start
    from tests.conftest import ids
    from tests.test_scoring import _pageviews
    themes, regions = ids(db)
    country = db.scalar(select(Country))
    rules = load_rules(db, country.id)
    today = date(2026, 10, 12)
    vary = ("worsen", "ease", "persist", "return", "spread", "continue", "deepen")
    for w in range(28):
        day = datetime.combine(week_start(today) - timedelta(weeks=w), datetime.min.time())
        _pageviews(db, country.id, themes["health"], day.date(), 2000)
        for k in range(3):
            store_article(db, country.id, rules, url=f"https://ex.ly/h/{w}/{k}", lang="ar" if k else "en",
                          title=f"Hospital shortages in Sabha {vary[(w + k) % 7]} {k}", published_at=day, source_key="rss")
        if w < 2:
            for k in range(20):
                store_article(db, country.id, rules, url=f"https://alert{k}.ly/a/{w}", title=f"Hospital medicines shortage Libya {k}",
                              published_at=day, source_key="galerts")
    db.commit()
    compute(db, country.id, weeks=5, today=today + timedelta(days=7))
    week = week_start(today)
    f = digest.build_facts(db, country, week)
    h = next(c for c in f["coverage_by_theme"] if c["theme"] == "Health")
    cell = db.scalar(select(CellWeek).where(CellWeek.theme_id == themes["health"], CellWeek.region_id == regions["national"],
                                            CellWeek.lens == "audience", CellWeek.week_start == week))
    assert h["articles"] == 12 == cell.breakdown["articles_4w"] and h["articles_all"] == 52 == cell.coverage
    assert h["previous_window"] == 12 and h["previous_window_all"] == 12
    assert h["arabic"] == 8 and h["english"] == 4                                   # the scored stories by language
    top = next(g for g in f["top_gaps"] if g["theme"] == "Health" and g["lens"] == "audience")
    assert top["articles"] == 12 and top["articles_all"] == 52 and abs(top["gap"]) < 0.2
    assert digest.COUNTS_LIMIT in f["known_limits"] and digest.UNSCORED_LIMIT not in f["known_limits"]


def test_digest_refusal_and_error_recorded(db, monkeypatch):
    country = db.scalar(select(Country))
    monkeypatch.setattr(digest, "_client", lambda: SimpleNamespace(messages=FakeMessages("refusal")))
    d = digest.generate(db, country, week=date(2026, 9, 28))
    assert d.status == "refused" and d.content_md is None

    class Boom:
        def create(self, **kw):
            raise RuntimeError("network down")
    monkeypatch.setattr(digest, "_client", lambda: SimpleNamespace(messages=Boom()))
    d2 = digest.generate(db, country, week=date(2026, 9, 21))
    assert d2.status == "error" and "network down" in d2.error
    assert db.scalar(select(Digest).where(Digest.week_start == date(2026, 9, 21))).status == "error"


def test_digest_job_without_key(db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    from app.jobs import weekly_digest
    assert weekly_digest() == "awaiting_key"


def test_digest_page_gets_the_brief_in_the_interface_language(client, users, db, monkeypatch):
    from tests.conftest import login
    country = db.scalar(select(Country))
    monkeypatch.setattr(digest, "_client", lambda: SimpleNamespace(messages=FakeMessages()))
    d = digest.generate(db, country, week=date(2026, 10, 5))
    old = Digest(country_id=country.id, week_start=date(2026, 9, 28), model="m", status="ok", content_md="## Old")
    db.add(old)
    db.commit()
    login(client, "j@example.org", "journo-password-1")
    ar = client.get(f"/api/digests/{d.id}", headers={"X-Lang": "ar"}).json()
    assert ar["lang"] == "ar" and ar["content_md"].startswith("## الأسبوع باختصار")
    assert client.get(f"/api/digests/{d.id}").json()["content_md"].startswith("## This week in brief")
    assert client.get(f"/api/digests/{old.id}", headers={"X-Lang": "ar"}).json()["lang"] == "en"   # written before Arabic briefs
