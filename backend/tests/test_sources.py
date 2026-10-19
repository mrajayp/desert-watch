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


def test_items_date_range(client, users, db):
    c = db.scalar(select(Country))
    rules = load_rules(db, c.id)
    from datetime import datetime
    store_article(db, c.id, rules, url="https://ex.ly/mar", title="طرابلس ليبيا", published_at=datetime(2026, 3, 15, 10), source_key="rss")
    store_article(db, c.id, rules, url="https://ex.ly/apr", title="طرابلس ليبيا", published_at=datetime(2026, 4, 1, 0, 5), source_key="rss")
    db.commit()
    login(client, "admin@example.org", "admin-password-1")
    r = client.get("/api/items", params={"start": "2026-03-01", "end": "2026-03-31"}).json()
    assert [x["url"] for x in r["items"]] == ["https://ex.ly/mar"]


# ---------------------------------------------------------------- the register programme (register.py, plan C-R2.1)
def _outlet(db, domain, created_via="auto", **kw):
    c = db.scalar(select(Country))
    o = Outlet(country_id=c.id, name=domain, domain=domain, languages=["ar"], created_via=created_via, **kw)
    db.add(o)
    db.flush()
    return o


def _articles(db, o, n=1, days_ago=10, source_key="rss", extra=None):
    c = db.scalar(select(Country))
    for i in range(n):
        db.add(Item(country_id=c.id, kind="article", source_key=source_key, dedupe_key=f"url:{o.domain}/{days_ago}/{i}/{source_key}",
                    url=f"https://{o.domain}/{i}", title="ليبيا خبر", published_at=utcnow() - timedelta(days=days_ago),
                    outlet_id=o.id, relevant=True, extra=dict(extra or {})))
    db.commit()


def _scope(db, o):
    from app.api.common import outlet_categories
    return outlet_categories(db, [o.id]).get(o.id, {}).get("scope")


def test_foreign_country_code_domain_becomes_international_unverified(db, users):
    from app import register
    c = db.scalar(select(Country))
    egypt = _outlet(db, "akhbar-masr.eg")
    home = _outlet(db, "some-site.ly")             # the home ccTLD is ingest.infer_scope's, not this rule's
    labelled = _outlet(db, "radio.tn")
    db.add(OutletCategory(outlet_id=labelled.id, dimension="scope", value="libyan", confidence="reported",
                          evidence_url="https://example.org/study", set_by=users[0].id))
    db.commit()
    p = register.plan(db, c)
    rows = {r["domain"]: r for r in p["cctld"]}
    assert set(rows) == {"akhbar-masr.eg"}
    assert (rows["akhbar-masr.eg"]["scope"], rows["akhbar-masr.eg"]["base_country"], rows["akhbar-masr.eg"]["confidence"],
            rows["akhbar-masr.eg"]["evidence"]) == ("international", "Egypt", "unverified", "https://akhbar-masr.eg/")
    assert register.apply(db, p) == {"cctld": 1}
    db.expire_all()
    assert _scope(db, egypt) == {"value": "international", "confidence": "unverified", "evidence_url": "https://akhbar-masr.eg/",
                                 "id": _scope(db, egypt)["id"]}
    assert db.get(Outlet, egypt.id).base_country == "Egypt" and _scope(db, home) is None
    assert _scope(db, labelled)["value"] == "libyan"                       # a person's label is never touched
    assert register.plan(db, c)["cctld"] == []                               # done once
    assert "DRY RUN" in register.report(register.plan(db, c)) and "cctld: 0" in register.report(register.plan(db, c))


def test_vanity_ly_domains_are_never_libyan(db, users):
    from app import register
    from app.api.common import outlet_categories
    c = db.scalar(select(Country))
    rules = load_rules(db, c.id)
    it, _ = store_article(db, c.id, rules, url="https://cutt.ly/abc", title="ليبيا طرابلس", published_at=utcnow(), source_key="galerts")
    vanity = db.get(Outlet, it.outlet_id)
    assert vanity.domain == "cutt.ly" and _scope(db, vanity) is None       # the .ly rule skips the denylist
    real = _outlet(db, "news-site.ly")
    assert _scope(db, real) is None
    from app.ingest import infer_scopes
    infer_scopes(db)
    assert _scope(db, real)["value"] == "libyan" and _scope(db, vanity) is None
    # a Libyan label a rule gave a vanity domain earlier is closed; a person's stays
    old = _outlet(db, "ow.ly")
    db.add(OutletCategory(outlet_id=old.id, dimension="scope", value="libyan", confidence="unverified",
                          evidence_url="https://ow.ly/", note="Inferred from the .ly domain."))
    person = _outlet(db, "buff.ly")
    db.add(OutletCategory(outlet_id=person.id, dimension="scope", value="libyan", confidence="reported",
                          evidence_url="https://example.org/", set_by=users[0].id))
    db.commit()
    p = register.plan(db, c)
    assert [v["domain"] for v in p["vanity"]] == ["ow.ly"]
    assert register.apply(db, p) == {"vanity": 1}
    db.expire_all()
    assert old.id not in outlet_categories(db, [old.id]) and _scope(db, person)["value"] == "libyan"
    closed = db.scalar(select(OutletCategory).where(OutletCategory.outlet_id == old.id))
    assert closed.valid_to is not None and "vanity" in closed.note
    assert register.plan(db, c)["vanity"] == []


def test_gdelt_source_country_votes_set_a_likely_scope(db):
    from app import register
    c = db.scalar(select(Country))
    egy = _outlet(db, "masr-news.com")
    few = _outlet(db, "two-votes.com")
    split = _outlet(db, "split-votes.com")
    home = _outlet(db, "libyan-site.com")
    _articles(db, egy, 3, source_key="gdelt", extra={"sourcecountry": "Egypt"})
    _articles(db, few, 2, source_key="gdelt", extra={"sourcecountry": "Egypt"})
    _articles(db, split, 3, source_key="gdelt", extra={"sourcecountry": "Egypt"})
    _articles(db, split, 2, days_ago=20, source_key="gdelt", extra={"sourcecountry": "Libya"})
    _articles(db, home, 4, source_key="gdelt", extra={"sourcecountry": "Libya"})
    votes = register.gdelt_votes(db, c.id)
    assert votes[egy.id] == {"Egypt": 3} and votes[split.id] == {"Egypt": 3, "Libya": 2}
    p = register.plan(db, c)
    rows = {r["domain"]: r for r in p["gdelt"]}
    assert set(rows) == {"masr-news.com", "libyan-site.com"}      # 2 votes: too few; 3 of 5: no agreement
    assert (rows["masr-news.com"]["scope"], rows["masr-news.com"]["base_country"], rows["masr-news.com"]["confidence"]) == \
        ("international", "Egypt", "likely")
    assert rows["libyan-site.com"]["scope"] == "libyan" and rows["libyan-site.com"]["base_country"] is None
    assert "domain:masr-news.com" in rows["masr-news.com"]["evidence"] and "3 of 3" in rows["masr-news.com"]["note"]
    assert register.apply(db, p) == {"gdelt": 2}
    db.expire_all()
    assert _scope(db, egy)["confidence"] == "likely" and db.get(Outlet, egy.id).base_country == "Egypt"
    assert _scope(db, home)["value"] == "libyan" and _scope(db, few) is None and _scope(db, split) is None


HOME_AR = ("<!doctype html><html lang='ar' dir='rtl'><head><meta property='og:locale' content='ar_EG'>"
           "<title>أخبار ليبيا الآن</title></head><body><nav><a href='/'>الرئيسية</a><a>ليبيا</a><a>العالم</a></nav></body></html>")
HOME_UK = ("<html lang=\"en-GB\"><head><meta property=\"og:locale\" content=\"en_GB\"><title>World news</title></head>"
           "<body><header><a>Home</a><a>Politics</a></header></body></html>")
HOME_NONE = "<html><head><title>Daily</title></head><body><nav><a>Home</a></nav></body></html>"


def test_homepage_signals_are_suggestions_never_labels(client, users, db):
    from app import register
    from app.api.common import outlet_categories
    c = db.scalar(select(Country))
    sig = register.homepage_signals(HOME_AR, c)
    assert sig == {"lang": "ar", "locale": "ar_EG", "title_mentions": 1, "nav_mentions": 1}
    ar = _outlet(db, "libya-now.com")
    uk = _outlet(db, "worldnews.com")
    none = _outlet(db, "daily.com")
    # the country in the title outranks a theme's og:locale; a foreign locale alone is international
    assert register.store_suggestion(ar, HOME_AR, "https://libya-now.com/", c)["scope"] == "libyan"
    assert register.store_suggestion(uk, HOME_UK, "https://worldnews.com/", c) == {
        "rule": "homepage", "scope": "international", "base_country": "United Kingdom", "confidence": "unverified",
        "evidence": "https://worldnews.com/", "note": "The homepage says og:locale en_GB."}
    assert register.store_suggestion(none, HOME_NONE, "https://daily.com/", c) is None
    db.commit()
    assert ar.external["scope_suggestion"]["signals"]["title_mentions"] == 1 and "scope_suggestion" not in none.external
    for o in (ar, uk):
        _articles(db, o, 6)
    p = register.plan(db, c)
    assert p["suggestions"] == 2 and p["cctld"] == [] and p["gdelt"] == []
    register.apply(db, p)
    assert not outlet_categories(db, [ar.id, uk.id])                        # a suggestion is never applied by a machine
    # the Contribute review queue shows it prefilled, busiest first, paged
    login(client, "j@example.org", "journo-password-1")
    q = client.get("/api/contribute", params={"outlets_size": 1}).json()["outlets"]
    assert q["total"] == 2 and q["page"] == 1 and q["pages"] == 2 and len(q["items"]) == 1
    row = q["items"][0]
    assert row["domain"] in ("libya-now.com", "worldnews.com") and row["articles"] == 6 and row["missing"] == ["scope", "alignment"]
    assert row["suggestion"]["confidence"] == "unverified" and row["suggestion"]["rule"] == "homepage"
    q2 = client.get("/api/contribute", params={"outlets_size": 1, "outlets_page": 2}).json()["outlets"]
    assert q2["page"] == 2 and q2["items"][0]["domain"] != row["domain"]
    # a rule's proposal is prefilled where the outlet has no scope yet, before any homepage suggestion
    egy = _outlet(db, "cairo-times.eg")
    _articles(db, egy, 9)
    q = client.get("/api/contribute").json()["outlets"]
    first = q["items"][0]
    assert first["domain"] == "cairo-times.eg" and first["suggestion"] == {
        "scope": "international", "base_country": "Egypt", "confidence": "unverified", "evidence": "https://cairo-times.eg/",
        "rule": "cctld", "note": "Based in Egypt (.eg domain)."}
    # journalists propose, admins apply: the endpoint is unchanged
    sug = first["suggestion"]
    r = client.post(f"/api/outlets/{egy.id}/categories", json={"dimension": "scope", "value": sug["scope"],
                                                                  "confidence": sug["confidence"], "evidence_url": sug["evidence"]})
    assert r.json()["status"] == "proposed"


def test_dormant_outlets_are_hidden_unless_asked_for(client, users, db):
    quiet = _outlet(db, "quiet.com")
    busy = _outlet(db, "busy.com")
    _articles(db, quiet, 3, days_ago=400)
    _articles(db, busy, 2, days_ago=100)
    login(client, "j@example.org", "journo-password-1")
    ids = {o["domain"] for o in client.get("/api/outlets").json()}
    assert "busy.com" in ids and "quiet.com" not in ids
    ids = {o["domain"] for o in client.get("/api/outlets", params={"show_dormant": 1}).json()}
    assert {"busy.com", "quiet.com"} <= ids
    # the single-outlet route gives the full row whatever its state
    row = client.get(f"/api/outlets/{quiet.id}").json()
    assert row["domain"] == "quiet.com" and row["articles"] == 0 and row["closed_on"] is None and "ai_cited_4w" in row
    assert set(row) >= {"lang_mix", "categories", "pending_changes", "quality", "external", "rss", "monitored", "languages"}
    assert client.get(f"/api/outlets/{busy.id}", params={"days": 365}).json()["articles"] == 2
