from sqlalchemy import select

from app.ingest import load_rules, social_outlet, store_article
from app.models import Country, Outlet, utcnow


def test_social_outlet_youtube_forms():
    assert social_outlet("https://www.youtube.com/channel/UCTjGk6smzE1z4P_nI8dUqJw/videos") == (
        "youtube.com/channel/UCTjGk6smzE1z4P_nI8dUqJw", "youtube")
    assert social_outlet("https://www.youtube.com/@WasatTV") == ("youtube.com/@WasatTV", "youtube")
    assert social_outlet("https://m.youtube.com/@WasatTV/shorts") == ("youtube.com/@WasatTV", "youtube")
    assert social_outlet("https://www.youtube.com/feeds/videos.xml?channel_id=UC14j_8A3Q5uRrLTjkiyP-dA") == (
        "youtube.com/channel/UC14j_8A3Q5uRrLTjkiyP-dA", "youtube")
    # a video link names no channel: the bare platform
    assert social_outlet("https://www.youtube.com/watch?v=bactojJI3mQ") == ("youtube.com", "youtube")
    assert social_outlet("https://youtu.be/bactojJI3mQ") == ("youtube.com", "youtube")
    assert social_outlet("https://www.youtube.com/shorts/abc") == ("youtube.com", "youtube")


def test_store_article_keeps_the_collectors_channel(db):
    c = db.scalar(select(Country))
    rules = load_rules(db, c.id)
    ch = Outlet(country_id=c.id, name="Wasat TV", domain="youtube.com/channel/UCTjGk6smzE1z4P_nI8dUqJw", languages=["ar"])
    db.add(ch)
    db.flush()
    it, created = store_article(db, c.id, rules, url="https://www.youtube.com/watch?v=v1", title="انقطاع الكهرباء في سبها",
                                published_at=utcnow(), source_key="youtube", outlet_domain=ch.domain,
                                outlet_cache={ch.domain: ch})
    assert created and it.outlet_id == ch.id
    # a link that names its own account still wins over what the collector passed
    it2, _ = store_article(db, c.id, rules, url="https://www.facebook.com/LibyaAlAhrarTV/posts/1", title="سبها ليبيا",
                           published_at=utcnow(), source_key="galerts", outlet_domain="facebook.com/other")
    assert db.get(Outlet, it2.outlet_id).domain == "facebook.com/LibyaAlAhrarTV"
    # with no account from the collector a video still lands on the platform
    it3, _ = store_article(db, c.id, rules, url="https://www.youtube.com/watch?v=v2", title="سبها ليبيا",
                           published_at=utcnow(), source_key="galerts", outlet_domain="alwasat.ly")
    assert db.get(Outlet, it3.outlet_id).domain == "youtube.com"
