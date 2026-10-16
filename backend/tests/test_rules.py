"""Theme rules: title first, cleaned snippets, co-occurrence window, veto contexts, masks,
search/alert results as a prior, evidence, re-tagging. Includes the owner's two bad examples
from the 2026-10-16 review."""
from datetime import datetime

from sqlalchemy import select

from app.classify import ThemeRule, classify_item, clean_snippet, split_segments, strip_dateline
from app.ingest import add_query_prior, load_rules, passes_guard, store_article
from app.models import Country, Item, ItemRegion, ItemTheme, Outlet, Region, Theme

DAY = datetime(2026, 10, 14)


def themes(db):
    return {t.slug: t.id for t in db.scalars(select(Theme))}


def links(db, item_id):
    return {lk.theme_id: lk for lk in db.scalars(select(ItemTheme).where(ItemTheme.item_id == item_id))}


def active(db, item_id):
    t = {v: k for k, v in themes(db).items()}
    return {t[k] for k, lk in links(db, item_id).items() if lk.active}


# ---------------------------------------------------------------- the owner's examples
EX1_TITLE = "Torrential rains in Libya's Tripoli kill two - SRN News"
EX1_SNIPPET = ("Torrential rains in Libya's Tripoli kill two. Tue, Oct 13, 2026 0 ... Women's Representation . "
               "Other News to Consider. Indian police detain ...")
EX2_TITLE = "Türkiye recovers black box from jet crash that killed Libyan military chief"


def test_example_1_rains_story_is_not_womens_participation(db):
    th = themes(db)
    cid = db.scalar(select(Country.id))
    rules = load_rules(db, cid)
    it, created = store_article(db, cid, rules, url="https://srnnews.com/torrential-rains-libya", title=EX1_TITLE,
                                snippet=EX1_SNIPPET, published_at=DAY, source_key="galerts", lang="en",
                                extra={"alert": "theme:gender_political_participation:en",
                                       "query_themes": ["gender_political_participation"]},
                                forced_theme_ids=(th["gender_political_participation"],),
                                query="theme:gender_political_participation:en")
    db.commit()
    assert created and it.relevant
    lk = links(db, it.id)[th["gender_political_participation"]]
    assert (lk.method, lk.active) == ("query", False)
    assert lk.evidence == {"field": "query", "terms": [], "query": "theme:gender_political_participation:en"}
    assert not active(db, it.id) & {"gender_political_participation", "governance", "security"}
    # the site's "Women's Representation" link list is not part of the cleaned snippet
    assert "Representation" not in clean_snippet("galerts", EX1_TITLE, EX1_SNIPPET)


def test_example_2_jet_crash_has_no_security_or_governance(db):
    th = themes(db)
    cid = db.scalar(select(Country.id))
    rules = load_rules(db, cid)
    url = "https://www.trtafrika.com/africa/turkiye-recovers-black-box"
    it, _ = store_article(db, cid, rules, url=url, title=EX2_TITLE, published_at=datetime(2025, 12, 24),
                          source_key="gnews", lang="en", extra={"query_theme": "security", "query_themes": ["security"]},
                          forced_theme_ids=(th["security"],), query="gnews:security")
    # the same URL comes back from the governance query
    again, created = store_article(db, cid, rules, url=url, title=EX2_TITLE, published_at=datetime(2025, 12, 24),
                                   source_key="gnews", lang="en", extra={"query_theme": "governance"},
                                   forced_theme_ids=(th["governance"],), query="gnews:governance")
    db.commit()
    assert again.id == it.id and not created
    lk = links(db, it.id)
    assert (lk[th["security"]].method, lk[th["security"]].active) == ("query", False)
    assert (lk[th["governance"]].method, lk[th["governance"]].active) == ("query", False)
    assert lk[th["governance"]].evidence["query"] == "gnews:governance"
    assert it.extra["query_themes"] == ["security", "governance"] and it.extra["query_theme"] == "security"
    assert not active(db, it.id) & {"gender_political_participation", "governance", "security"}


def test_owner_examples_old_links_are_cleared_by_retag(db):
    """Production state before the fix: example 1 has an active rule link to gender political
    participation, example 2 an active rule link to security and an active query link to governance."""
    from app.retag import retag_all
    th = themes(db)
    cid = db.scalar(select(Country.id))
    out = db.scalar(select(Outlet.id))
    a = Item(country_id=cid, kind="article", source_key="galerts", dedupe_key="url:a", url="https://a", title=EX1_TITLE,
             snippet=EX1_SNIPPET, lang="en", published_at=DAY, outlet_id=out,
             extra={"alert": "theme:gender_political_participation:en"})
    b = Item(country_id=cid, kind="article", source_key="gnews", dedupe_key="url:b", url="https://b", title=EX2_TITLE,
             lang="en", published_at=DAY, outlet_id=out, extra={"query_theme": "security"})
    db.add_all([a, b])
    db.flush()
    db.add_all([ItemTheme(item_id=a.id, theme_id=th["gender_political_participation"], method="rule"),
                ItemTheme(item_id=b.id, theme_id=th["security"], method="rule"),
                ItemTheme(item_id=b.id, theme_id=th["governance"], method="query")])
    db.commit()
    retag_all(db, out=lambda *_: None)
    assert not active(db, a.id) & {"gender_political_participation", "governance", "security"}
    assert not active(db, b.id) & {"gender_political_participation", "governance", "security"}
    assert links(db, b.id)[th["security"]].evidence is None          # stale rule row, kept inactive
    assert links(db, b.id)[th["governance"]].evidence == {"field": "query", "terms": [], "query": None}


# ---------------------------------------------------------------- snippet cleaning
def test_clean_snippet_galerts_keeps_segments_like_the_title():
    sn = clean_snippet("galerts", EX1_TITLE, EX1_SNIPPET)
    assert sn.startswith("Torrential rains in Libya's Tripoli kill two")
    assert clean_snippet("galerts", "عكاش: التحقيقات قد تكشف حالات تزوير للهوية الوطنية",
                         "... ليبيا ، ولا تقتصر على مرزق ، باعتبار أن القضية تمس الأمن القومي ...") == ""
    # other sources keep every segment
    assert "Representation" in clean_snippet("rss", EX1_TITLE, EX1_SNIPPET)


def test_clean_snippet_wordpress_footer_and_entities():
    raw = ("Officers embarked on a search operation, [&#8230;] \n The post  Libyan Police Free 10 Syrian Nationals  "
           "appeared first on  LibyaReview . ")
    assert clean_snippet("rss", "Libyan Police Free 10 Syrian Nationals", raw) == "Officers embarked on a search operation, […]"
    ar = "موعة &#8230; \n ظهرت المقالة  الدعم والأسعار على المحك  أولاً على  قناة الجماهيرية العظمى . "
    assert clean_snippet("rss", "x", ar) == "موعة …"
    assert clean_snippet("rss", "x", "Libya&#8217;s NOC &amp; Eni") == "Libya’s NOC & Eni"
    assert split_segments("a […] b ... c · d | e") == ["a", "b", "c", "d", "e"]


def test_strip_dateline():
    assert strip_dateline("Tripoli, March 31, 2026 (LANA) – Prime Minister Dbeibah met") == "Prime Minister Dbeibah met"
    assert strip_dateline("طرابلس 31 مارس 2026 م (وال) - استعرض رئيس الحكومة") == "استعرض رئيس الحكومة"
    assert strip_dateline("بنغازي 2 أبريل 2026 ( وال ) –  دعا النائب") == "دعا النائب"
    assert strip_dateline("طرابلس (المشهد) – أكدت البعثة") == "أكدت البعثة"
    assert strip_dateline("Zawiya, Libya (Ports Europe) April 5, 2026 – French broadcaster") == "French broadcaster"
    for keep in ["The Production Department of the National Oil Corporation (NOC) organized a meeting",
                 "In 2023 the National Oil Corporation (NOC) reported",
                 "أعلنت البعثة الأممية توصل اللجنة المصغرة (4+4) خلال اجتماعها"]:
        assert strip_dateline(keep) == keep


def test_dateline_does_not_place_the_story(db):
    cid = db.scalar(select(Country.id))
    rules = load_rules(db, cid)
    tripoli = db.scalar(select(Region.id).where(Region.slug == "tripoli"))
    it, _ = store_article(db, cid, rules, url="https://lana.gov.ly/1", title="رئيس حكومة الوحدة الوطنية يستعرض الميزانية",
                          snippet="طرابلس 31 مارس 2026 م (وال) - استعرض رئيس حكومة الوحدة الوطنية الميزانية",
                          published_at=DAY, source_key="backfill")
    db.commit()
    assert tripoli and not db.get(ItemRegion, (it.id, tripoli))


def test_guard_uses_the_cleaned_snippet_and_possessives(db):
    cid = db.scalar(select(Country.id))
    rules = load_rules(db, cid)
    assert passes_guard(rules, None, "Libya's NOC and Eni launch gas production boost", None)
    # Libya named only in an alert's keyword excerpt that has nothing to do with the title
    assert not passes_guard(rules, None, "Egypt issues dust storm warning for Cairo", "... flights to Libya resume ...",
                            "galerts")
    assert passes_guard(rules, None, "Egypt issues dust storm warning for Cairo", "... flights to Libya resume ...", "rss")


# ---------------------------------------------------------------- matching
def test_title_first_and_two_snippet_terms():
    r = [ThemeRule.build(1, "security", 1, ["armed clashes", "clashes", "gunmen", "militia"], [], [])]
    assert classify_item("Gunmen attack checkpoint", None, r) == {1: ("title", ["gunmen"])}
    assert classify_item("Mayor opens market", "Gunmen were seen nearby.", r) == {}            # one snippet term
    assert classify_item("Mayor opens market", "Armed clashes broke out.", r) == {}           # one phrase, counted once
    assert classify_item("Mayor opens market", "Gunmen and a militia ... more", r) == {1: ("snippet", ["gunmen", "militia"])}


def test_cooc_window():
    w, v = ["women", "woman"], ["killed", "violence"]
    r = [ThemeRule.build(9, "gv", 1, [], [], [], cooc=[w, v], strict=True)]
    assert classify_item("Two women killed in Tripoli shelling", None, r) == {9: ("title", ["women+killed"])}
    far = "Women in Libya hold a long and lively market fair downtown while elsewhere a man was killed"
    assert classify_item(far, None, r) == {}
    # a pair must sit inside one snippet segment
    assert classify_item("Report", "Libyan women take part ... three killed in a clash", r) == {}
    assert classify_item("Report", "News ... violence against women rises", r) == {9: ("snippet", ["women+violence"])}


def test_veto_context():
    veto = [{"terms": ["killed", "مقتل"], "context": ["crash", "accident", "تصادم"]}]
    r = [ThemeRule.build(1, "security", 1, ["killed", "gunmen"], ["مقتل"], [], veto=veto)]
    assert classify_item(EX2_TITLE, None, r) == {}
    assert classify_item("Three killed in Tripoli shelling", None, r) == {1: ("title", ["killed"])}
    assert classify_item("Gunmen killed two after a crash", None, r) == {1: ("title", ["gunmen"])}
    assert classify_item("مقتل شخصين في حادث تصادم", None, r) == {}
    assert classify_item("مقتل شخصين في اشتباكات", None, r) == {1: ("title", ["مقتل"])}


def test_seeded_vetoes(db):
    cid = db.scalar(select(Country.id))
    rules = load_rules(db, cid)
    th = themes(db)
    hits = lambda t: set(classify_item(t, None, rules.themes))  # noqa: E731
    assert th["security"] not in hits("Three women killed in traffic accident southwest of Tripoli")
    assert th["security"] not in hits("مقتل وفقدان 53 مهاجراً إثر انقلاب قارب قبالة سواحل ليبيا")
    assert th["security"] in hits("Three killed in armed clashes in Zawiya")
    assert th["health"] not in hits("انتشار مرض الحمى بين الماشية في الجنوب البيطري")
    assert th["health"] in hits("انتشار مرض غامض في سبها")


def test_masks(db):
    cid = db.scalar(select(Country.id))
    rules = load_rules(db, cid)
    services = themes(db)["services"]
    hits = lambda t: set(classify_item(t, None, rules.themes))  # noqa: E731
    assert services not in hits("خفر السواحل يعترض قاربا في المياه الإقليمية الليبية")
    assert services not in hits("تجمعات المياه تغلق الطرق في بنغازي")
    assert services in hits("انقطاع المياه عن أحياء في طرابلس")
    assert services in hits("أزمة المياه في سبها بعد مياه الأمطار")   # the bare term still counts


def test_term_hygiene(db):
    cid = db.scalar(select(Country.id))
    rules = load_rules(db, cid)
    th = themes(db)
    hits = lambda t: set(classify_item(t, None, rules.themes))  # noqa: E731
    assert th["security"] not in hits("مسيرة سلمية في مصراتة")                 # a march, not a drone
    assert th["security"] in hits("غارة بطائرة مسيرة على قاعدة جوية")
    assert th["governance"] not in hits("US drone strike reported near the border")
    assert th["governance"] in hits("Teachers' strike closes schools")
    assert th["migration"] in hits("IOM returns 171 stranded people")
    assert th["migration"] not in hits("Police seize fuel in smuggling raid")
    assert th["health"] in hits("وصول شحنة من أدوية الأورام")


# ---------------------------------------------------------------- query prior, evidence, re-tagging
def test_query_prior_and_evidence(db):
    th = themes(db)
    cid = db.scalar(select(Country.id))
    rules = load_rules(db, cid)
    # the query's own theme confirmed by the title: an active rule link that names the query
    hit, _ = store_article(db, cid, rules, url="https://x.example/h", title="انقطاع الكهرباء في سبها",
                           published_at=DAY, source_key="gnews", forced_theme_ids=(th["services"],), query="gnews:services")
    miss, _ = store_article(db, cid, rules, url="https://x.example/m", title="Libyan delegation visits Rome",
                            published_at=DAY, source_key="gnews", forced_theme_ids=(th["services"],), query="gnews:services")
    db.commit()
    lk = links(db, hit.id)[th["services"]]
    assert (lk.method, lk.active) == ("rule", True)
    assert lk.evidence == {"field": "title", "terms": ["انقطاع الكهرباء"], "query": "gnews:services"}
    lk = links(db, miss.id)[th["services"]]
    assert (lk.method, lk.active) == ("query", False)
    # a later query adds an inactive row and is recorded; it never activates anything
    add_query_prior(db, miss, rules, (th["health"], th["services"]), "gnews:health")
    db.commit()
    assert (links(db, miss.id)[th["health"]].method, links(db, miss.id)[th["health"]].active) == ("query", False)
    assert miss.extra["query_themes"] == ["health", "services"]


def test_retag_all_is_idempotent_and_leaves_user_and_model_rows(db):
    from app.retag import retag_all
    th = themes(db)
    cid = db.scalar(select(Country.id))
    out = db.scalar(select(Outlet.id))
    it = Item(country_id=cid, kind="article", source_key="gnews", dedupe_key="url:r", url="https://r",
              title="Libya's NOC reports oil output; clashes in Zawiya", lang="en", published_at=DAY, outlet_id=out,
              extra={"query_theme": "health"})
    db.add(it)
    db.flush()
    db.add_all([ItemTheme(item_id=it.id, theme_id=th["health"], method="query", active=True),
                ItemTheme(item_id=it.id, theme_id=th["security"], method="query", active=False),
                ItemTheme(item_id=it.id, theme_id=th["governance"], method="user", active=False),
                ItemTheme(item_id=it.id, theme_id=th["migration"], method="model", active=True, score=0.9)])
    db.commit()
    dry = retag_all(db, dry_run=True, out=lambda *_: None)
    assert dry["links_changed"] > 0
    db.expire_all()
    assert links(db, it.id)[th["health"]].active is True                   # nothing saved
    first = retag_all(db, out=lambda *_: None)
    db.expire_all()
    lk = links(db, it.id)
    assert lk[th["health"]].active is False                                 # own query, not confirmed
    assert lk[th["health"]].evidence == {"field": "query", "terms": [], "query": "gnews:health"}
    assert (lk[th["security"]].method, lk[th["security"]].active) == ("query", True)   # query confirmed by the title
    assert lk[th["security"]].evidence["field"] == "title"
    assert (lk[th["economy"]].method, lk[th["economy"]].active) == ("rule", True)
    assert lk[th["economy"]].evidence == {"field": "title", "terms": ["NOC", "oil output"], "query": None}
    assert (lk[th["governance"]].method, lk[th["governance"]].active) == ("user", False)
    assert (lk[th["migration"]].method, lk[th["migration"]].active) == ("model", True)
    assert first["themes"]["economy"]["after"][0] >= 1
    second = retag_all(db, out=lambda *_: None)
    assert second["links_changed"] == 0 and second["relevance_flipped"] == 0


def test_apply_theme_terms_touches_only_term_fields(db):
    from app.seed import apply_theme_terms
    sec = db.scalar(select(Theme).where(Theme.slug == "security"))
    gov = db.scalar(select(Theme).where(Theme.slug == "governance"))
    v_sec, v_gov, terms_gov = sec.version, gov.version, list(gov.en_terms)
    sec.en_terms, sec.veto, sec.name_en, sec.acled_event_types = ["edited"], [], "Edited name", ["X"]
    gov.en_terms = ["admin term"]
    db.commit()
    assert apply_theme_terms(db, ["security"]) == {"security": ["en_terms", "veto"]}
    db.commit()
    assert "militia" in sec.en_terms and sec.veto and sec.version == v_sec + 1
    assert sec.name_en == "Edited name" and sec.acled_event_types == ["X"]
    assert gov.en_terms == ["admin term"] and gov.version == v_gov and terms_gov != gov.en_terms
    assert apply_theme_terms(db, ["security"]) == {"security": []}       # unchanged: no new version
    assert sec.version == v_sec + 1


def test_admin_theme_edit_keeps_fields_the_form_does_not_send(client, users, db):
    from tests.conftest import login
    gv = db.scalar(select(Theme).where(Theme.slug == "gender_violence"))
    sec = db.scalar(select(Theme).where(Theme.slug == "security"))
    cooc, veto = gv.cooc, sec.veto
    login(client, "admin@example.org", "admin-password-1")
    form = lambda t: {"name_en": t.name_en, "name_ar": t.name_ar, "en_terms": t.en_terms, "ar_terms": t.ar_terms,  # noqa: E731
                      "exclude": t.exclude, "active": True, "acled_event_types": [], "reliefweb_themes": []}
    assert client.put(f"/api/themes/{gv.id}", json=form(gv)).status_code == 200
    assert client.put(f"/api/themes/{sec.id}", json=form(sec)).status_code == 200
    db.expire_all()
    assert gv.cooc == cooc and gv.strict and gv.group == "gender"
    assert sec.veto == veto and veto
