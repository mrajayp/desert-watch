from types import SimpleNamespace

from sqlalchemy import select

from app.alerts import attach_feeds, sync_specs
from app.collectors import galerts
from app.models import AlertFeed, Item, ItemRegion, Region

ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Google Alert - سبها</title>
  <entry>
    <id>tag:google.com,2013:googlealerts/feed:1</id>
    <title type="html">انقطاع &lt;b&gt;الكهرباء&lt;/b&gt; في &lt;b&gt;سبها&lt;/b&gt; لليوم الثالث</title>
    <link href="https://www.google.com/url?rct=j&amp;sa=t&amp;url=https://example.ly/news/123&amp;ct=ga&amp;cd=x&amp;usg=y"/>
    <published>2026-10-11T08:00:00Z</published>
    <updated>2026-10-11T08:00:00Z</updated>
    <content type="html">سكان &lt;b&gt;سبها&lt;/b&gt; يشكون</content>
  </entry>
</feed>"""


def test_unwrap():
    assert galerts.unwrap("https://www.google.com/url?rct=j&sa=t&url=https://a.ly/x%3Fy%3D1&ct=ga") == "https://a.ly/x?y=1"
    assert galerts.unwrap("https://a.ly/x") == "https://a.ly/x"


def test_specs_and_attach(db):
    rows = db.scalars(select(AlertFeed)).all()
    assert len(rows) >= 22 * 2 + 12  # districts x2 + themes x2 (+ extras)
    sabha = db.scalar(select(AlertFeed).where(AlertFeed.key == "district:sabha:ar"))
    assert "سبها" in sabha.query and "ليبيا" in sabha.query and sabha.region_id
    r = attach_feeds(db, "district:sabha:ar https://www.google.com/alerts/feeds/123/456\n"
                         "district:sabha:en http://evil.example/feed\nnope:key https://www.google.com/alerts/feeds/1/2")
    assert r["attached"] == 1 and len(r["problems"]) == 2
    assert sync_specs(db) == 0  # idempotent, keeps feed url
    assert db.scalar(select(AlertFeed.feed_url).where(AlertFeed.key == "district:sabha:ar")).endswith("/456")


def test_collect_parses_feed_and_tags_district(db, monkeypatch):
    attach_feeds(db, "district:sabha:ar https://www.google.com/alerts/feeds/123/456")
    monkeypatch.setattr(galerts, "polite_get", lambda *a, **k: SimpleNamespace(content=ATOM.encode(), raise_for_status=lambda: None))
    res = galerts.collect(db)
    assert res.rows == 1 and res.errors == 0
    it = db.scalar(select(Item).where(Item.source_key == "galerts"))
    assert it.url == "https://example.ly/news/123" and "<b>" not in it.title and it.relevant
    sabha = db.scalar(select(Region.id).where(Region.slug == "sabha"))
    assert db.get(ItemRegion, (it.id, sabha)) is not None
