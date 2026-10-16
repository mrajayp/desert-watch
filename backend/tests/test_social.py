from sqlalchemy import func, select

from app.ingest import load_rules, social_outlet, store_article, url_key
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
    ch = Outlet(country_id=c.id, name="Some TV", domain="youtube.com/channel/UCxxxxxxxxxxxxxxxxxxxxxx", languages=["ar"])
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


def _cats(db, oid):
    from app.models import OutletCategory
    return {c.dimension: (c.value, c.evidence_url) for c in db.scalars(select(OutletCategory).where(
        OutletCategory.outlet_id == oid, OutletCategory.status == "active", OutletCategory.valid_to.is_(None)))}


def test_seed_creates_youtube_channels_with_parent_labels(db):
    from app.models import OutletCategory
    from app.seed import seed_all
    wasat = db.scalar(select(Outlet).where(Outlet.domain == "youtube.com/channel/UCTjGk6smzE1z4P_nI8dUqJw"))
    assert wasat.rss_url == "https://www.youtube.com/feeds/videos.xml?channel_id=UCTjGk6smzE1z4P_nI8dUqJw"
    assert wasat.external["parent"] == "alwasat.ly"
    cats = _cats(db, wasat.id)
    assert cats["medium"][0] == "youtube"
    assert cats["scope"] == ("libyan", "https://alwasat.ly/")          # copied from the website
    assert "alignment" not in cats
    hnec = db.scalar(select(Outlet).where(Outlet.domain == "youtube.com/channel/UCnygNoGcbVM8AY4fIa3Nm8w"))
    assert _cats(db, hnec.id)["scope"] == ("libyan", "https://hnec.ly/")   # no website outlet: config fallback
    assert _cats(db, hnec.id)["type"][0] == "state"
    n = db.scalar(select(func.count(OutletCategory.id)))
    seed_all(db)
    db.commit()
    assert db.scalar(select(func.count(OutletCategory.id))) == n          # idempotent
    assert db.scalar(select(func.count(Outlet.id)).where(Outlet.domain.like("youtube.com/channel/%"))) == 9


def test_seed_links_existing_social_accounts_to_their_website(db):
    from app.seed import seed_all
    c = db.scalar(select(Country))
    page = Outlet(country_id=c.id, name="lyobserver", domain="facebook.com/lyobserver")
    stranger = Outlet(country_id=c.id, name="someone", domain="facebook.com/someone")
    db.add_all([page, stranger])
    db.commit()
    seed_all(db)
    db.commit()
    assert page.external["parent"] == "libyaobserver.ly"
    assert _cats(db, page.id)["scope"] == ("libyan", "https://libyaobserver.ly/")
    assert not (stranger.external or {}).get("parent") and "scope" not in _cats(db, stranger.id)


def test_youtube_feed_retries_and_files_videos_on_the_channel(db, monkeypatch):
    from types import SimpleNamespace
    from app.collectors import rss
    from app.models import Item
    monkeypatch.setattr(rss, "YOUTUBE_BACKOFF", 0)
    db.query(Outlet).filter(Outlet.rss_url.is_not(None), ~Outlet.domain.like("youtube.com/channel/UCTj%")).update(
        {"rss_url": None}, synchronize_session=False)
    db.commit()
    feed = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/">
      <entry><title>انقطاع الكهرباء في سبها لساعات</title><link rel="alternate" href="https://www.youtube.com/watch?v=abc"/>
      <published>2026-10-15T10:00:00+00:00</published><media:group><media:description>تقرير</media:description></media:group></entry>
    </feed>"""
    calls = []

    def fake_get(client, url, **kw):
        calls.append(url)
        ok = len(calls) % 2 == 0      # every other request fails, as YouTube does
        return SimpleNamespace(content=feed.encode(), status_code=200 if ok else 404,
                               raise_for_status=(lambda: None) if ok else (lambda: (_ for _ in ()).throw(RuntimeError("404"))))
    monkeypatch.setattr(rss, "polite_get", fake_get)
    res = rss.collect(db)
    assert len(calls) == 2 and res.errors == 0 and res.rows == 1
    it = db.scalar(select(Item).where(Item.source_key == "youtube"))
    assert db.get(Outlet, it.outlet_id).domain == "youtube.com/channel/UCTjGk6smzE1z4P_nI8dUqJw" and it.relevant

    # a run where every try fails is noted, not an error, until it happens three runs in a row
    monkeypatch.setattr(rss, "polite_get", lambda *a, **k: SimpleNamespace(
        content=b"", status_code=500, raise_for_status=lambda: (_ for _ in ()).throw(RuntimeError("500"))))
    assert [rss.collect(db).errors for _ in range(3)] == [0, 0, 1]


def test_gnews_social_post_text():
    from app.collectors.gnews_social import post_text
    names = set()
    assert post_text("Libya Alahrar TV - قناة ليبيا الأحرار. . قصيدة ساخرة للشاعر الراحل عبدالمولى البغدادي بسبب الغلاء - Facebook",
                     names) == "قصيدة ساخرة للشاعر الراحل عبدالمولى البغدادي بسبب الغلاء"
    assert "Libya Alahrar TV - قناة ليبيا الأحرار" in names
    assert post_text("Libya Alahrar TV - قناة ليبيا الأحرار. . - Facebook", names) is None        # nothing after the name
    assert post_text("Libya Alahrar TV - قناة ليب - Facebook", names) is None                     # the name, cut short
    assert post_text("الدبيبة لطلاب الشهادة: ثقتي فيكم كبيرة جدا - Facebook") == "الدبيبة لطلاب الشهادة: ثقتي فيكم كبيرة جدا"
    assert post_text('Libya Observer on X: "Heavy rain floods streets in Benghazi tonight" - X') == \
        "Heavy rain floods streets in Benghazi tonight"
    assert post_text("بلدية بنغازي - Facebook") is None                                           # too short to be a post
    assert post_text("Al Menassa (@almenassa_libya) • Instagram photos and videos") is None


RSS = """<?xml version="1.0"?><rss version="2.0"><channel>{}</channel></rss>"""
ITEM = """<item><title>{t}</title><link>https://news.google.com/rss/articles/{k}?oc=5</link>
<pubDate>Wed, 15 Oct 2026 10:00:00 GMT</pubDate><source url="https://www.facebook.com">Facebook</source></item>"""


def _fake_google(monkeypatch, answers):
    from types import SimpleNamespace
    from app.collectors import gnews_social
    calls = []

    def fake(client, url, params=None, **kw):
        calls.append(params)
        status, body = answers(params) if callable(answers) else answers.pop(0)
        return SimpleNamespace(status_code=status, content=body.encode())
    monkeypatch.setattr(gnews_social, "polite_get", fake)
    return calls


def test_gnews_social_one_fixed_day_per_window(db, monkeypatch):
    from datetime import date
    from app.collectors import gnews_social
    from app.models import Item
    c = db.scalar(select(Country))
    page = Outlet(country_id=c.id, name="libyaakhbar", domain="facebook.com/libyaakhbar", monitored=False,
                  external={"social_media_scrape": {"kind": "media", "posts": 32480}})
    person = Outlet(country_id=c.id, name="some.person", domain="facebook.com/some.person")
    numeric = Outlet(country_id=c.id, name="100044172232412", domain="facebook.com/100044172232412",
                     external={"social_media_scrape": {"kind": "media"}})
    group = Outlet(country_id=c.id, name="groups/benghazi", domain="facebook.com/groups/benghazi",
                   external={"social_media_scrape": {"kind": "media"}})
    plat = Outlet(country_id=c.id, name="facebook.com", domain="facebook.com")
    db.add_all([page, person, numeric, group, plat])
    db.flush()
    old = Item(country_id=c.id, kind="article", source_key="gnews", dedupe_key=url_key("https://news.google.com/rss/articles/k2?oc=5"),
               url="https://news.google.com/rss/articles/k2?oc=5", title="x", published_at=utcnow(), outlet_id=plat.id, extra={})
    db.add(old)
    db.commit()
    body = RSS.format("".join([
        ITEM.format(t="ليبيا أخبار. . انقطاع الكهرباء في سبها لساعات طويلة اليوم - Facebook", k="k1"),
        ITEM.format(t="ليبيا أخبار. . المصرف المركزي يعلن سعر صرف الدينار الليبي - Facebook", k="k2"),
        ITEM.format(t="ليبيا أخبار - Facebook", k="k3"),
        ITEM.format(t="ليبيا أخبار. . صورة اليوم من الشاطئ الجميل في الصيف - Facebook", k="k4")]))
    calls = _fake_google(monkeypatch, lambda p: (200, body if "after:2026-10-15" in p["q"] else RSS.format("")))
    res = gnews_social.collect(db, today=date(2026, 10, 16))
    # only the register page; one fixed 1-day window for yesterday and one for the day before
    assert [p["q"] for p in calls] == ["site:facebook.com/libyaakhbar after:2026-10-15 before:2026-10-16",
                                       "site:facebook.com/libyaakhbar after:2026-10-14 before:2026-10-15"]
    assert {p["gl"] for p in calls} == {"EG"} and {p["ceid"] for p in calls} == {"EG:ar"}
    assert res.rows == 1 and res.errors == 0
    stored = db.scalar(select(Item).where(Item.source_key == "gnews_social"))
    assert (stored.outlet_id, stored.title, stored.relevant) == (page.id, "انقطاع الكهرباء في سبها لساعات طويلة اليوم", True)
    db.refresh(old)
    assert old.outlet_id == page.id                      # moved off the whole-platform outlet
    assert "'capped': 0" in res.detail and "'no_theme': 1" in res.detail


def test_gnews_social_stops_after_three_refusals(db, monkeypatch):
    from app.collectors import gnews_social
    c = db.scalar(select(Country))
    db.add_all([Outlet(country_id=c.id, name=f"p{i}", domain=f"facebook.com/page{i}",
                       external={"social_media_scrape": {"kind": "media"}}) for i in range(4)])
    db.commit()
    calls = _fake_google(monkeypatch, lambda p: (429, ""))
    res = gnews_social.collect(db)
    assert len(calls) == 3 and "stopped after 3 refusals" in res.detail
