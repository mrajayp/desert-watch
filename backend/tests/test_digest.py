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
                     SimpleNamespace(type="text", text="## This week in brief\nFacts only.")])


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
    assert "Sabha" not in f["districts_with_no_monitored_articles"]
    assert fake.last["model"] == "claude-haiku-5-5" and "Never name private individuals" in fake.last["system"]
    # cached: a second call does not re-run the model
    fake.last = None
    assert digest.generate(db, country, week=date(2026, 10, 5)).id == d.id and fake.last is None


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
