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


def _store(db, url, title="انقطاع الكهرباء في سبها ليبيا", published_at=None, **kw):
    c = db.scalar(select(Country))
    it, _ = store_article(db, c.id, load_rules(db, c.id), url=url, title=title, published_at=published_at or utcnow(),
                          source_key=kw.pop("source_key", "galerts"), **kw)
    db.commit()
    return it


def test_unlisted_social_accounts_and_shorteners_are_not_counted(db, users):
    from app.ingest import apply_relevance_guard
    from app.models import Item, OutletCategory
    c = db.scalar(select(Country))
    person = _store(db, "https://www.facebook.com/some.person/posts/1")
    bare = _store(db, "https://www.facebook.com/reel/555")
    short = _store(db, "https://news.google.com/rss/articles/x1", outlet_domain="t.co")
    register = Outlet(country_id=c.id, name="libyaakhbar", domain="facebook.com/libyaakhbar", monitored=False,
                      external={"social_media_scrape": {"kind": "media"}})
    db.add(register)
    db.flush()
    listed = _store(db, "https://www.facebook.com/libyaakhbar/posts/2")
    site = _store(db, "https://alwasat.ly/news/1")
    assert (person.relevant, person.extra["filtered"]) == (False, "unlisted_social_account")
    assert (bare.relevant, bare.extra["filtered"]) == (False, "unlisted_social_account")
    assert (short.relevant, short.extra["filtered"]) == (False, "shortener")
    assert listed.relevant and site.relevant
    # a user decision and a user-added item are never touched
    kept = _store(db, "https://www.facebook.com/other.person/posts/3")
    kept.relevant, kept.extra = True, {**kept.extra, "user_relevance": True}
    added = _store(db, "https://www.facebook.com/third.person/posts/4", added_by=users[0].id)
    assert added.relevant
    db.commit()
    apply_relevance_guard(db, c.id)
    assert db.get(Item, kept.id).relevant is True and db.get(Item, added.id).relevant is True
    # labelling the account restores its posts on the next guard run
    db.add(OutletCategory(outlet_id=person.outlet_id, dimension="scope", value="libyan", confidence="likely",
                          evidence_url="https://www.facebook.com/some.person"))
    db.commit()
    assert apply_relevance_guard(db, c.id) == 1
    db.refresh(person)
    assert person.relevant and person.extra["filtered"] is None
    db.refresh(bare)
    assert not bare.relevant                         # a whole-platform bucket never counts
    assert apply_relevance_guard(db, c.id) == 0      # idempotent


def test_guard_moves_old_items_on_unlisted_accounts(db):
    """Items stored before the rule (relevant, no filter) are marked on the next guard run."""
    from app.ingest import apply_relevance_guard
    from app.models import Item
    c = db.scalar(select(Country))
    o = Outlet(country_id=c.id, name="x.com/someone", domain="x.com/someone")
    db.add(o)
    db.flush()
    it = Item(country_id=c.id, kind="article", source_key="galerts", dedupe_key="url:old", url="https://x.com/someone/status/1",
              title="سبها ليبيا", published_at=utcnow(), outlet_id=o.id, extra={}, relevant=True)
    db.add(it)
    db.commit()
    assert apply_relevance_guard(db, c.id) == 1
    db.refresh(it)
    assert (it.relevant, it.extra["filtered"]) == (False, "unlisted_social_account")


def test_page_name_ending_in_ly_is_not_a_libyan_domain(db):
    from app.models import OutletCategory
    it = _store(db, "https://www.facebook.com/someone.ly/posts/1")
    assert not db.scalar(select(OutletCategory.id).where(OutletCategory.outlet_id == it.outlet_id,
                                                         OutletCategory.dimension == "scope"))
    assert it.extra["filtered"] == "unlisted_social_account"


def test_page_post_and_website_story_count_once(db):
    from datetime import datetime, timedelta
    from app.dedupe import mark_duplicates
    c = db.scalar(select(Country))
    page = Outlet(country_id=c.id, name="alwasatnewsly", domain="facebook.com/alwasatnewsly",
                  external={"parent": "alwasat.ly", "social_media_scrape": {"kind": "media"}})
    other = Outlet(country_id=c.id, name="libyaakhbar", domain="facebook.com/libyaakhbar",
                   external={"social_media_scrape": {"kind": "media"}})
    db.add_all([page, other])
    db.flush()
    t = datetime(2026, 10, 6, 9)
    head = "انقطاع الكهرباء في سبها لساعات طويلة"
    post = _store(db, "https://news.google.com/rss/articles/p1", title=head, outlet_domain=page.domain,
                  source_key="gnews_social", published_at=t)
    site = _store(db, "https://alwasat.ly/news/1", title=head, source_key="rss", published_at=t + timedelta(hours=20))
    elsewhere = _store(db, "https://news.google.com/rss/articles/p2", title=head, outlet_domain=other.domain,
                       source_key="gnews_social", published_at=t)
    assert post.outlet_id == page.id and site.outlet_id != page.id
    assert mark_duplicates(db) == 1
    db.refresh(post)
    db.refresh(elsewhere)
    assert post.duplicate_of == site.id         # the website copy is kept
    assert elsewhere.duplicate_of is None       # a page outside the family stays
    assert mark_duplicates(db) == 0
