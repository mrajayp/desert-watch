import json
from datetime import date, timedelta

from sqlalchemy import select

from app.imports.backfill_links import _clean_title, _published, run
from app.ingest import load_rules, store_article
from app.models import Country, Item, Outlet, utcnow


def test_published_and_title_helpers():
    cited = date(2026, 10, 13)
    assert _published("2026-10-12T09:30:00+02:00", cited).date() == date(2026, 10, 12)
    assert _published("2025-01-01T00:00:00", cited).date() == date(2026, 10, 12)  # implausible -> day before
    assert _published(None, cited).date() == date(2026, 10, 12)
    assert _clean_title("انقطاع الكهرباء في سبها يستمر لساعات طويلة | الوسط", "الوسط") == "انقطاع الكهرباء في سبها يستمر لساعات طويلة"


def test_backfill_only_under_collected_outlets(db, tmp_path):
    c = db.scalar(select(Country))
    rules = load_rules(db, c.id)
    # we already hold 5 articles from well.ly this year; the file cites it 6 times -> skipped (5 >= 0.2*6)
    for i in range(5):
        store_article(db, c.id, rules, url=f"https://well.ly/{i}", title="طرابلس ليبيا", published_at=utcnow(), source_key="rss")
    db.commit()
    day = (utcnow().date() - timedelta(days=3)).isoformat()
    rows = [{"url": f"https://well.ly/x{i}", "date": day, "outlet": "Well"} for i in range(6)]
    rows += [{"url": f"https://missing.ly/a{i}", "date": day, "outlet": "Missing (Arabic)", "ref": {"section": "Health"}}
             for i in range(3)]
    p = tmp_path / "links.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    calls = []

    def fake_fetch(url):
        calls.append(url)
        if url.endswith("a2"):
            raise ValueError("boom")
        return {"title": "نقص الأدوية في مستشفيات سبها ليبيا", "lang": "ar", "published": None, "site_name": None}

    out = run(db, p, fetch=fake_fetch, per_domain_interval=0)
    assert out["outlets_backfilled"] == 1 and out["to_fetch"] == 3
    assert out["stored"] == 2 and out["failed"] == 1
    assert all("missing.ly" in u for u in calls)
    it = db.scalar(select(Item).where(Item.source_key == "backfill").limit(1))
    assert it.extra["ref"] == {"section": "Health"} and it.relevant
    assert db.get(Outlet, it.outlet_id).name == "Missing (Arabic)"
    # resumable: a second run skips stored links and the link that failed before
    calls.clear()
    out2 = run(db, p, fetch=fake_fetch, per_domain_interval=0)
    assert out2["to_fetch"] == 1 and out2["skipped_failed_before"] == 1 and calls == []
    out3 = run(db, p, fetch=fake_fetch, per_domain_interval=0, retry_failed=True)
    assert len(calls) == 1 and out3["failed"] == 1


def test_junk_titles_rejected():
    for t in ("Contact Support", "Just a moment...", "404", "Access denied", "الرئيسية", "short"):
        assert _clean_title(t, None) is None, t


def test_backfill_survives_expunge_after_200(db, tmp_path):
    day = (utcnow().date() - timedelta(days=3)).isoformat()
    rows = [{"url": f"https://big.ly/a{i}", "date": day, "outlet": None} for i in range(410)]
    p = tmp_path / "links.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    fake = lambda url: {"title": f"اشتباكات في طرابلس ليبيا رقم {url[-4:]}", "lang": "ar"}  # noqa: E731
    out = run(db, p, fetch=fake, per_domain_interval=0)
    assert out["stored"] == 410


def test_prefetched_rows_need_no_network(db, tmp_path):
    day = (utcnow().date() - timedelta(days=3)).isoformat()
    rows = [{"url": "https://pre.ly/1", "date": day, "meta": {"title": "انقطاع الكهرباء في سبها ليبيا", "lang": "ar"}},
            {"url": "https://pre.ly/2", "date": day, "error": "The site answered 403."}]
    p = tmp_path / "pre.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    def boom(url):
        raise AssertionError("network used")
    out = run(db, p, fetch=boom, per_domain_interval=0)
    assert out["stored"] == 1 and out["failed"] == 1
