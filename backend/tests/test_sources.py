from datetime import timedelta

from sqlalchemy import select

from app.ingest import load_rules, reassign_social, social_outlet, store_article
from app.models import Country, Item, Outlet, OutletCategory, utcnow

from .conftest import login


def test_social_outlet_parsing():
    assert social_outlet("https://www.facebook.com/LibyaAlAhrarTV/posts/123") == ("facebook.com/LibyaAlAhrarTV", "facebook")
    assert social_outlet("https://m.facebook.com/permalink.php?story_fbid=1&id=99887") == ("facebook.com/99887", "facebook")
    assert social_outlet("https://facebook.com/groups/benghazi.news/posts/5") == ("facebook.com/groups/benghazi.news", "facebook")
    assert social_outlet("https://www.facebook.com/reel/555") == ("facebook.com", "facebook")
    assert social_outlet("https://twitter.com/UNSMILibya/status/1") == ("x.com/UNSMILibya", "x")
    assert social_outlet("https://www.instagram.com/p/abc/") == ("instagram.com", "instagram")
    assert social_outlet("https://www.instagram.com/libya_news/p/abc/") == ("instagram.com/libya_news", "instagram")
    assert social_outlet("https://www.tiktok.com/@ly.news/video/1") == ("tiktok.com/@ly.news", "tiktok")
    assert social_outlet("https://www.youtube.com/watch?v=x") == ("youtube.com", "youtube")
    assert social_outlet("https://libyaobserver.ly/a") is None


def test_post_goes_to_existing_page_case_insensitively(db):
    c = db.scalar(select(Country))
    page = Outlet(country_id=c.id, name="LibyaAlAhrarTV", domain="facebook.com/LibyaAlAhrarTV", languages=["ar"],
                  created_via="import", monitored=False)
    db.add(page)
    db.flush()
    it, _ = store_article(db, c.id, load_rules(db, c.id), url="https://www.facebook.com/libyaalahrartv/videos/9",
                          title="فيضانات في طرابلس ليبيا", published_at=utcnow(), source_key="galerts")
    assert it.outlet_id == page.id
    # unknown page: new outlet named after the account, medium = facebook
    it2, _ = store_article(db, c.id, load_rules(db, c.id), url="https://www.facebook.com/SomeLocalPage/posts/1",
                           title="سبها ليبيا", published_at=utcnow(), source_key="galerts")
    o = db.get(Outlet, it2.outlet_id)
    assert (o.domain, o.name) == ("facebook.com/SomeLocalPage", "SomeLocalPage")
    assert db.scalar(select(OutletCategory.value).where(OutletCategory.outlet_id == o.id,
                                                        OutletCategory.dimension == "medium")) == "facebook"


def test_reassign_social_moves_platform_posts(db):
    c = db.scalar(select(Country))
    plat = Outlet(country_id=c.id, name="facebook.com", domain="facebook.com", languages=[], created_via="auto")
    db.add(plat)
    db.flush()
    db.add(Item(country_id=c.id, kind="article", source_key="galerts", dedupe_key="url:x", title="t",
                url="https://www.facebook.com/PageOne/posts/1", published_at=utcnow(), outlet_id=plat.id))
    db.commit()
    assert reassign_social(db) == {"moved": 1, "pages": 1}
    assert db.scalar(select(Outlet.domain).join(Item, Item.outlet_id == Outlet.id)) == "facebook.com/PageOne"


def test_items_source_filter_and_counts(client, users, db):
    c = db.scalar(select(Country))
    rules = load_rules(db, c.id)
    now = utcnow() - timedelta(hours=1)
    for i, src in enumerate(["galerts", "galerts", "rss"]):
        store_article(db, c.id, rules, url=f"https://ex.ly/{i}", title="طرابلس ليبيا", published_at=now, source_key=src)
    db.commit()
    login(client, "admin@example.org", "admin-password-1")
    r = client.get("/api/items", params={"source": "galerts", "days": 7}).json()
    assert r["total"] == 2 and {x["source"] for x in r["items"]} == {"galerts"}
    assert r["by_source"] == {"galerts": 2, "rss": 1}
    r = client.get("/api/items", params={"lang": "en", "days": 7}).json()
    assert r["total"] == 0
