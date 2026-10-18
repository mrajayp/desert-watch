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
    # rule rows the rules no longer confirm, on the item's own alert or search theme, become query priors
    lk = links(db, a.id)[th["gender_political_participation"]]
    assert (lk.method, lk.active) == ("query", False)
    assert lk.evidence == {"field": "query", "terms": [], "query": "theme:gender_political_participation:en"}
    assert links(db, b.id)[th["security"]].method == "query"
    assert links(db, b.id)[th["security"]].evidence["query"] == "gnews:security"
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


def test_place_homonyms_do_not_pass_the_guard_or_tag_districts(db):
    """A-R1.4: الخمس / Tripoli (Lebanon) / برقة / البيضاء (Yemen) on their own are not Libya."""
    cid = db.scalar(select(Country.id))
    rules = load_rules(db, cid)
    reg = {r.slug: r.id for r in db.scalars(select(Region))}
    assert not passes_guard(rules, None, "خمس نصائح لتوفير الكهرباء في الصيف", None)
    assert not passes_guard(rules, None, "Clashes in Tripoli, Lebanon, leave two dead", None)
    assert not passes_guard(rules, None, "اشتباكات في طرابلس شمال لبنان", None)
    assert not passes_guard(rules, None, "تحدث الوزير برقة عن الأزمة", None)
    assert not passes_guard(rules, None, "Flooding hits Bayda, Yemen", None)
    assert passes_guard(rules, None, "Clashes in Tripoli leave two dead", None)
    assert passes_guard(rules, None, "اشتباكات في الخمس غرب ليبيا", None)
    assert rules.places_in("اشتباكات في طرابلس شمال لبنان") == []
    assert rules.places_in("السنوات الخمس الماضية") == []
    assert reg["murqub"] in rules.places_in("حريق في مصنع بالخمس غرب ليبيا")
    assert reg["murqub"] in rules.places_in("الطريق الساحلي بين الخمس وزليتن")
    assert reg["cyrenaica"] in rules.places_in("قبائل برقة تطالب الحكومة الليبية")
    assert reg["jabal_al_akhdar"] not in rules.places_in("Flooding hits Bayda, Yemen")
    assert reg["jabal_al_akhdar"] in rules.places_in("Flooding hits Bayda in eastern Libya")
    assert reg["jabal_al_akhdar"] not in rules.places_in("ضبط أسلحة بيضاء في طرابلس")      # "bladed weapons"
    # a stored search result: filtered out, and no district tag
    it, _ = store_article(db, cid, rules, url="https://ex.example/five", title="خمس نصائح لتوفير الكهرباء في الصيف",
                          published_at=DAY, source_key="gnews")
    db.commit()
    assert not it.relevant and it.extra["filtered"] == "no_country_mention"
    assert db.get(ItemRegion, (it.id, reg["murqub"])) is None


def test_alert_region_tag_follows_the_text_after_retag(db):
    """A district alert's tag (method 'query') is a prior: active only while the text places the story there."""
    from app.retag import retag_all
    reg = {r.slug: r.id for r in db.scalars(select(Region))}
    five = _article(db, "five", "خمس نصائح لتوفير الكهرباء في ليبيا", source="galerts", extra={"alert": "district:murqub:ar"})
    real = _article(db, "real", "اشتباكات في الخمس غرب ليبيا", source="galerts", extra={"alert": "district:murqub:ar"})
    db.add_all([ItemRegion(item_id=five.id, region_id=reg["murqub"], method="query", active=True),
                ItemRegion(item_id=real.id, region_id=reg["murqub"], method="query", active=False)])
    db.commit()
    dry = retag_all(db, dry_run=True, out=lambda *_: None)
    real_run = retag_all(db, out=lambda *_: None)
    assert {**dry, "dry_run": False} == real_run
    db.expire_all()
    off, on = db.get(ItemRegion, (five.id, reg["murqub"])), db.get(ItemRegion, (real.id, reg["murqub"]))
    assert (off.method, off.active) == ("query", False)      # "five tips": the alert was a hint
    assert (on.method, on.active) == ("query", True)         # the text itself names the district
    assert retag_all(db, dry_run=True, out=lambda *_: None)["links_changed"] == 0


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
    assert miss.extra["query_themes"] == ["services", "health"]
    # each theme keeps the query that first asked for it
    assert miss.extra["queries"] == {"services": "gnews:services", "health": "gnews:health"}


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
                ItemTheme(item_id=it.id, theme_id=th["migration"], method="model", active=True, score=0.9),
                ItemTheme(item_id=it.id, theme_id=th["services"], method="rule", active=True)])
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
    assert (lk[th["services"]].method, lk[th["services"]].active, lk[th["services"]].evidence) == ("rule", False, None)
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


# ---------------------------------------------------------------- fix round (review of 2026-10-16)
def test_rss_storage_gate_stays_permissive(db):
    """One theme word in the cleaned summary is still enough to store an outlet feed item. The
    item gets no active link until the rules (or the model) confirm a theme."""
    cid = db.scalar(select(Country.id))
    rules = load_rules(db, cid)
    kw = dict(published_at=DAY, source_key="rss", require_theme=True)
    it, created = store_article(db, cid, rules, url="https://feed.example/1", title="Book fair opens in the old city",
                                snippet="Fans celebrated late. Gunmen were seen nearby.", **kw)
    assert created and not active(db, it.id)
    skipped, created = store_article(db, cid, rules, url="https://feed.example/2", title="Book fair opens in the old city",
                                     snippet="Fans celebrated late.", **kw)
    assert skipped is None and not created


# ---------------------------------------------------------------- fix round 2 (review_rules.md)
def _article(db, key, title, snippet=None, source="gnews", extra=None, relevant=True, published=DAY):
    it = Item(country_id=db.scalar(select(Country.id)), kind="article", source_key=source, dedupe_key=f"url:{key}",
              url=f"https://{key}.example", title=title, snippet=snippet, lang="en", published_at=published,
              outlet_id=db.scalar(select(Outlet.id)), extra=extra or {}, relevant=relevant)
    db.add(it)
    db.flush()
    return it


def _retag_fixture(db):
    """Articles that move every number in the retag report: new and stale links, place tags,
    relevance flips both ways, a duplicate copy, and user and alert place tags."""
    th = themes(db)
    reg = {r.slug: r.id for r in db.scalars(select(Region))}
    a = _article(db, "a", "Armed clashes in Zawiya leave three dead", relevant=False,
                 extra={"filtered": "no_country_mention"})
    b = _article(db, "b", "Armed clashes in Zawiya leave three dead")
    c = _article(db, "c", "Egypt issues dust storm warning for Cairo")
    d = _article(db, "d", "Mayor opens market in Misrata", relevant=False, extra={"user_relevance": False})
    b.duplicate_of = a.id
    db.add_all([ItemTheme(item_id=b.id, theme_id=th["health"], method="rule", active=True),
                ItemTheme(item_id=c.id, theme_id=th["security"], method="rule", active=True),
                ItemRegion(item_id=c.id, region_id=reg["tripoli"], method="rule", active=True),
                ItemRegion(item_id=d.id, region_id=reg["tripoli"], method="user", active=True),
                ItemRegion(item_id=d.id, region_id=reg["benghazi"], method="query", active=True)])
    db.commit()
    return reg, a, b, c, d


def test_retag_dry_run_reports_what_the_real_run_does(db):
    from app.retag import retag_all
    reg, a, b, c, d = _retag_fixture(db)
    dry = retag_all(db, dry_run=True, batch=2, out=lambda *_: None)
    real = retag_all(db, batch=2, out=lambda *_: None)
    assert dry["relevance_flipped"] == 2 and dry["links_changed"] > 0
    assert {**dry, "dry_run": False} == real
    assert real["items"]["after"]["relevant"] == real["items"]["before"]["relevant"]   # one on, one off
    db.expire_all()
    assert db.get(Item, a.id).relevant and not db.get(Item, c.id).relevant and not db.get(Item, d.id).relevant
    # place tags: the stale rule tag goes, user tags stay, an alert's tag follows the text (the story
    # never named Benghazi: the alert was a hint), new rule tags are added
    assert db.get(ItemRegion, (c.id, reg["tripoli"])).active is False
    user_tag = db.get(ItemRegion, (d.id, reg["tripoli"]))
    assert (user_tag.method, user_tag.active) == ("user", True)
    alert_tag = db.get(ItemRegion, (d.id, reg["benghazi"]))
    assert (alert_tag.method, alert_tag.active) == ("query", False)
    assert db.get(ItemRegion, (a.id, reg["zawiya"])).active and db.get(ItemRegion, (d.id, reg["misrata"])).active
    assert retag_all(db, dry_run=True, out=lambda *_: None)["links_changed"] == 0


def test_retag_dry_run_never_takes_the_write_lock(db, monkeypatch):
    import sqlite3

    import app.retag as rt
    from app.db import engine
    _retag_fixture(db)
    free = []

    def probe(*_):
        con = sqlite3.connect(engine.url.database, timeout=0)
        try:
            con.execute("BEGIN IMMEDIATE")
            con.rollback()
            free.append(True)
        except sqlite3.OperationalError:
            free.append(False)
        finally:
            con.close()

    plan = rt.plan_item

    def planning(*a, **k):
        probe()
        return plan(*a, **k)

    monkeypatch.setattr(rt, "plan_item", planning)
    rt.retag_all(db, dry_run=True, batch=2, out=probe)
    assert len(free) > 4 and all(free)


def test_retag_never_writes_over_a_user_correction_made_mid_batch(db, monkeypatch):
    from sqlalchemy import update

    import app.retag as rt
    from app.db import engine
    th = themes(db)
    stale = _article(db, "stale", "Mayor opens market in Misrata")
    new = _article(db, "new", "Armed clashes in Zawiya leave three dead")
    db.add(ItemTheme(item_id=stale.id, theme_id=th["security"], method="rule", active=True))
    db.commit()
    stale_id, new_id = stale.id, new.id
    plan = rt.plan_item

    def racing(item, *a, **k):
        p = plan(item, *a, **k)
        if item.id == stale_id:   # a user confirms the link the rules no longer support
            with engine.begin() as con:
                con.execute(update(ItemTheme).where(ItemTheme.item_id == stale_id, ItemTheme.theme_id == th["security"])
                            .values(method="user"))
        if item.id == new_id:     # a user says this one is not about security, before the rule link is written
            with engine.begin() as con:
                con.execute(ItemTheme.__table__.insert().values(item_id=new_id, theme_id=th["security"], method="user",
                                                                active=False, theme_version=1))
        return p

    monkeypatch.setattr(rt, "plan_item", racing)
    rt.retag_all(db, out=lambda *_: None)
    db.expire_all()
    assert (links(db, stale_id)[th["security"]].method, links(db, stale_id)[th["security"]].active) == ("user", True)
    assert (links(db, new_id)[th["security"]].method, links(db, new_id)[th["security"]].active) == ("user", False)


def test_query_keys_name_the_search_or_alert_that_ran(db):
    from app.retag import retag_all
    th = themes(db)
    cid = db.scalar(select(Country.id))
    rules = load_rules(db, cid)
    # first stored from an outlet feed, later returned by the governance search
    url = "https://feed.example/council"
    title = "Presidential Council meets the government in Tripoli"
    rss, _ = store_article(db, cid, rules, url=url, title=title, published_at=DAY, source_key="rss", require_theme=True)
    store_article(db, cid, rules, url=url, title=title, published_at=DAY, source_key="gnews",
                  extra={"query_theme": "governance", "query_themes": ["governance"]},
                  forced_theme_ids=(th["governance"],), query="gnews:governance")
    # a hand-written alert filed under migration
    kufra, _ = store_article(db, cid, rules, url="https://news.example/kufra", title="Sudanese refugees arrive in Kufra",
                             published_at=DAY, source_key="galerts",
                             extra={"alert": "extra:kufra_migration:en", "query_themes": ["migration"]},
                             forced_theme_ids=(th["migration"],), query="extra:kufra_migration:en")
    # an older item from the same alert only names the alert
    old = _article(db, "old-kufra", "Kufra mayor meets aid agencies", source="galerts",
                   extra={"alert": "extra:kufra_migration:en"})
    db.add(ItemTheme(item_id=old.id, theme_id=th["migration"], method="rule", active=True))
    db.commit()
    assert rss.extra["queries"] == {"governance": "gnews:governance"}
    retag_all(db, out=lambda *_: None)
    db.expire_all()
    assert links(db, rss.id)[th["governance"]].evidence["query"] == "gnews:governance"
    assert links(db, kufra.id)[th["migration"]].evidence["query"] == "extra:kufra_migration:en"
    lk = links(db, old.id)[th["migration"]]
    assert (lk.method, lk.active) == ("query", False)
    assert lk.evidence == {"field": "query", "terms": [], "query": "extra:kufra_migration:en"}


class _Resp:
    def __init__(self, body: str):
        self.content = body.encode()

    def raise_for_status(self):
        pass


GNEWS_RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Armed clashes in Zawiya - Libya Observer</title><link>https://news.google.com/rss/articles/zaw1</link>
<pubDate>Tue, 13 Oct 2026 10:00:00 GMT</pubDate><source url="https://libyaobserver.ly">Libya Observer</source></item>
</channel></rss>"""
ALERT_ATOM = """<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>Google Alert</title>
<entry><id>tag:1</id><title type="html">Sudanese refugees arrive in Kufra</title>
<link href="https://www.google.com/url?rct=j&amp;sa=t&amp;url=https://news.example/kufra-2&amp;ct=ga"/>
<published>2026-10-13T10:00:00Z</published><updated>2026-10-13T10:00:00Z</updated>
<content type="html">Sudanese refugees arrive in Kufra ... aid agencies</content></entry></feed>"""


def test_collectors_record_the_query_on_first_store(db, monkeypatch):
    from app.collectors import galerts, gdelt, gnews
    from app.models import AlertFeed
    monkeypatch.setattr(gnews, "polite_get", lambda *a, **k: _Resp(GNEWS_RSS))
    gnews.collect(db, themes=["security"])
    it = db.scalar(select(Item).where(Item.url == "https://news.google.com/rss/articles/zaw1"))
    assert it.extra["query_theme"] == "security" and it.extra["query_themes"] == ["security"]
    assert it.extra["queries"] == {"security": "gnews:security"}

    feed = db.scalar(select(AlertFeed).where(AlertFeed.key == "extra:kufra_migration:en"))
    feed.feed_url = "https://www.google.com/alerts/feeds/1/2"
    db.commit()
    monkeypatch.setattr(galerts, "polite_get", lambda *a, **k: _Resp(ALERT_ATOM))
    galerts.collect(db)
    it = db.scalar(select(Item).where(Item.url == "https://news.example/kufra-2"))
    assert it.extra["alert"] == "extra:kufra_migration:en" and it.extra["query_themes"] == ["migration"]
    assert it.extra["queries"] == {"migration": "extra:kufra_migration:en"}

    monkeypatch.setattr(gdelt, "_json", lambda *a, **k: {"articles": [
        {"url": "https://gd.example/1", "title": "Libya clashes", "seendate": "20261013T100000Z", "domain": "gd.example"}]})
    gdelt.collect(db)
    it = db.scalar(select(Item).where(Item.url == "https://gd.example/1"))
    assert it.extra["queries"] and all(v == f"gdelt:{k}" for k, v in it.extra["queries"].items())
    assert set(it.extra["queries"]) == set(it.extra["query_themes"])


def test_retag_theme_after_an_admin_edit(db):
    from app.retag import retag_theme
    th = themes(db)
    it = _article(db, "strike", "Teachers strike closes schools in Sabha")
    db.add(ItemTheme(item_id=it.id, theme_id=th["security"], method="rule", active=True))   # another theme
    db.commit()
    assert retag_theme(db, th["governance"]) == 1
    assert links(db, it.id)[th["governance"]].active
    gov = db.get(Theme, th["governance"])
    gov.en_terms = [t for t in gov.en_terms if t != "teachers strike"]
    gov.version += 1
    db.commit()
    retag_theme(db, th["governance"])
    db.expire_all()
    lk = links(db, it.id)
    assert (lk[th["governance"]].active, lk[th["governance"]].theme_version, lk[th["governance"]].evidence) == \
        (False, gov.version, None)
    assert lk[th["security"]].active                       # a governance edit leaves security alone
    assert retag_theme(db, th["governance"]) == 0


def test_gender_and_migration_word_removals(db):
    rules = load_rules(db, db.scalar(select(Country.id)))
    th = themes(db)
    hits = lambda t: set(classify_item(t, None, rules.themes))  # noqa: E731
    assert th["gender_migrant_detained_women"] not in hits("امرأة تحمل جنسية أجنبية تصل إلى مطار معيتيقة")
    assert th["gender_migrant_detained_women"] not in hits("وفاة امرأة أثناء الولادة في مستشفى سبها")
    assert th["gender_economic_health"] in hits("وفاة امرأة أثناء الولادة في مستشفى سبها")
    assert th["gender_legal_status"] not in hits("سيدة أعمال تنتقد قرار وزارة الاقتصاد")
    assert th["migration"] not in hits("البحث عن مفقودين بعد السيول في درنة")


def test_plural_is_not_a_second_snippet_word():
    r = [ThemeRule.build(1, "migration", 1, ["migrant", "migrants", "clash", "clashes"], [], [])]
    assert classify_item("Mayor opens market", "Migrants arrived. One migrant spoke.", r) == {}
    assert classify_item("Mayor opens market", "Migrants arrived after clashes.", r) == {1: ("snippet", ["clashes", "migrants"])}


def test_dateline_keeps_a_lead_that_spells_an_acronym():
    lead = "Benghazi Medical Centre (BMC) – the hospital received ten patients"
    assert strip_dateline(lead) == lead
    assert strip_dateline("Benghazi (LANA) – the hospital received ten patients") == "the hospital received ten patients"


def test_sync_themes_leaves_unchanged_themes_alone(db, capsys):
    from app.cli import main
    gov = db.scalar(select(Theme).where(Theme.slug == "governance"))
    gov.veto, gov.mask = None, None          # older rows: the newer columns are NULL
    db.commit()
    versions = {t.slug: t.version for t in db.scalars(select(Theme))}
    assert main(["sync-themes"]) == 0
    db.expire_all()
    assert {t.slug: t.version for t in db.scalars(select(Theme))} == versions
    assert "updated 0 themes" in capsys.readouterr().out


def test_admin_preview_uses_the_stored_vetoes_and_pairs(client, users, db):
    from app.models import utcnow
    from tests.conftest import login
    sec = db.scalar(select(Theme).where(Theme.slug == "security"))
    gv = db.scalar(select(Theme).where(Theme.slug == "gender_violence"))
    crash, clash = "Three killed in traffic accident near Tripoli", "Three killed in armed clashes in Zawiya"
    women = "Two women killed in Tripoli shelling"
    for k, t in (("p1", crash), ("p2", clash), ("p3", women)):
        _article(db, k, t, published=utcnow())
    db.commit()
    login(client, "admin@example.org", "admin-password-1")

    def form(t, name=None):
        return {"name_en": name or t.name_en, "name_ar": t.name_ar, "en_terms": t.en_terms, "ar_terms": t.ar_terms,
                "exclude": t.exclude, "active": True}

    def titles(url, body):
        return {x["title"] for x in client.post(url, json=body).json()["samples"]}

    for url in (f"/api/themes/preview?tid={sec.id}", "/api/themes/preview"):
        assert crash not in titles(url, form(sec)) and clash in titles(url, form(sec))
    assert women in titles(f"/api/themes/preview?tid={gv.id}", form(gv))
    # a new theme has nothing stored: the preview uses exactly what the form sends
    assert {crash, clash} <= titles("/api/themes/preview", form(sec, "A new theme"))
