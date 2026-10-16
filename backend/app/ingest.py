"""Storing collected rows: dedupe, outlet resolution, theme + place tagging."""
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .classify import PlaceRule, ThemeRule, classify_themes, tag_places
from .models import Country, Item, ItemRegion, ItemTheme, Outlet, OutletCategory, PlaceAlias, Region, Theme
from .textnorm import detect_lang, normalise, term_variants

_TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "oc"}


def normalise_url(url: str) -> str:
    p = urlsplit(url.strip())
    q = urlencode([(k, v) for k, v in parse_qsl(p.query) if k.lower() not in _TRACKING])
    host = p.netloc.lower().removeprefix("www.")
    return urlunsplit((p.scheme.lower() or "https", host, p.path.rstrip("/") or "/", q, ""))


def domain_of(url: str) -> str:
    host = urlsplit(url).netloc.lower().split(":")[0]
    return host.removeprefix("www.").removeprefix("m.").removeprefix("amp.")


# Social platforms: a post is attributed to its page/account ("facebook.com/<page>"), not to the
# platform, so Facebook pages show up as outlets (and match the Facebook blind-spot register).
SOCIAL = {"facebook.com": "facebook", "fb.com": "facebook", "instagram.com": "instagram", "x.com": "x",
          "twitter.com": "x", "tiktok.com": "tiktok", "youtube.com": "youtube", "t.me": "telegram"}
_SOCIAL_CANON = {"fb.com": "facebook.com", "twitter.com": "x.com", "mobile.twitter.com": "x.com", "youtu.be": "youtube.com"}
# first path segments that are not an account
_SOCIAL_RESERVED = {"watch", "reel", "reels", "share", "story.php", "photo.php", "photo", "video.php", "events",
                    "hashtag", "p", "tv", "explore", "i", "search", "home", "intent", "shorts", "results",
                    "playlist", "embed", "s", "login", "marketplace", "people", "pages", "profile.php",
                    "permalink.php", "media", "stories", "live", "channel", "c", "user", "status", "tag", "discover"}


def social_outlet(url: str) -> tuple[str, str] | None:
    """('facebook.com/<page>', platform) for a post on a social platform, or None. Returns the bare
    platform domain when the account cannot be read from the URL (e.g. facebook.com/reel/123)."""
    p = urlsplit(url)
    host = domain_of(url)
    host = _SOCIAL_CANON.get(host, host)
    if host not in SOCIAL:
        return None
    segs = [x for x in p.path.split("/") if x]
    q = dict(parse_qsl(p.query))
    account = None
    if host == "facebook.com":
        if segs[:1] == ["groups"] and len(segs) > 1:
            account = f"groups/{segs[1]}"
        elif segs and segs[0] in ("permalink.php", "story.php", "profile.php") and q.get("id"):
            account = q["id"]
        elif segs and segs[0].lower() not in _SOCIAL_RESERVED:
            account = segs[0]
    elif host in ("tiktok.com", "youtube.com"):
        if segs and segs[0].startswith("@"):
            account = segs[0]
        elif host == "youtube.com" and len(segs) > 1 and segs[0] in ("channel", "c", "user"):
            account = f"{segs[0]}/{segs[1]}"
        elif host == "youtube.com" and q.get("channel_id"):  # a channel's own feed
            account = f"channel/{q['channel_id']}"
    elif segs and segs[0].lower() not in _SOCIAL_RESERVED:
        account = segs[0]
    return (f"{host}/{account}" if account else host), SOCIAL[host]


SHORTENERS = {"t.co", "bit.ly", "ift.tt", "ow.ly", "buff.ly", "goo.gl", "tinyurl.com"}
# Sites where anyone can post and the domain alone names nobody. Their items are treated like a
# whole-platform bucket (facebook.com with no page): kept, never counted.
USER_PLATFORMS = {"youtu.be", "linkedin.com", "reddit.com", "medium.com", "threads.net", "threads.com"}
NOT_COUNTED = {"shortener", "unlisted_social_account"}


def register_kind(o: Outlet) -> str | None:
    """'media' / 'official' for pages on the 2023-24 Facebook register (imports/social_scrape.py)."""
    kind = ((o.external or {}).get("social_media_scrape") or {}).get("kind")
    return kind if kind in ("media", "official") else None


def labelled_outlets(s: Session) -> set[int]:
    """Outlets with an active type or scope label (set by an admin, the config or an import)."""
    return set(s.scalars(select(OutletCategory.outlet_id).where(
        OutletCategory.dimension.in_(("type", "scope")), OutletCategory.status == "active",
        OutletCategory.valid_to.is_(None))))


def not_counted_reason(o: Outlet | None, labelled: set[int]) -> str | None:
    """Items kept but never counted. A link shortener is not an outlet. A social account nobody has
    listed (no type/scope label, not on the register) can be a private person, and a whole-platform
    bucket (facebook.com, youtube.com ...) hides whose post it is. Labelling the account restores it."""
    if o is None:
        return None
    if o.domain in SHORTENERS:
        return "shortener"
    if o.domain in USER_PLATFORMS:
        return "unlisted_social_account"
    if o.domain.split("/", 1)[0] not in SOCIAL:
        return None
    if "/" in o.domain and (o.id in labelled or register_kind(o)):
        return None
    return "unlisted_social_account"


def url_key(url: str) -> str:
    n = normalise_url(url)
    return "url:" + (n if len(n) < 500 else hashlib.sha256(n.encode()).hexdigest())


@dataclass
class Rules:
    themes: list[ThemeRule] = field(default_factory=list)
    places: list[PlaceRule] = field(default_factory=list)
    region_parent: dict[int, int | None] = field(default_factory=dict)
    country_terms: list[str] = field(default_factory=list)  # normalised variants of the country name/demonym
    local_outlets: set = field(default_factory=set)          # outlet ids with scope = this country
    labelled_outlets: set = field(default_factory=set)       # outlet ids with any type/scope label

    def mentions_country(self, text: str) -> bool:
        n = normalise(text)
        return any(f" {t} " in n for t in self.country_terms) or bool(tag_places(text, self.places))


def load_rules(s: Session, country_id: int) -> Rules:
    themes = [ThemeRule.build(t.id, t.slug, t.version, t.en_terms, t.ar_terms, t.exclude, t.cooc, t.strict, t.require_country)
              for t in s.scalars(select(Theme).where(Theme.active.is_(True)))]
    regions = s.scalars(select(Region).where(Region.country_id == country_id)).all()
    aliases: dict[int, list[str]] = {}
    for a in s.scalars(select(PlaceAlias).where(PlaceAlias.approved.is_(True))):
        aliases.setdefault(a.region_id, []).append(a.alias)
    places = [PlaceRule.build(r.id, aliases.get(r.id, [])) for r in regions if r.level != "national"]
    c = s.get(Country, country_id)
    names = [c.name_en, c.name_ar, *c.config.get("demonyms", [])]
    country_terms = sorted({v for t in names for v in term_variants(t)})
    local = set(s.scalars(select(OutletCategory.outlet_id).where(
        OutletCategory.dimension == "scope", OutletCategory.value == "libyan" if c.iso2 == "LY" else OutletCategory.value == c.name_en.lower(),
        OutletCategory.status == "active", OutletCategory.valid_to.is_(None))))
    return Rules(themes, [p for p in places if p.variants], {r.id: r.parent_id for r in regions}, country_terms, local,
                 labelled_outlets=labelled_outlets(s))


def resolve_outlet(s: Session, country_id: int, domain: str, name: str | None, lang: str | None,
                   cache: dict) -> Outlet:
    if domain in cache:
        return cache[domain]
    social = "/" in domain  # a page on a social platform (see social_outlet)
    if social:  # page names are case-insensitive (the scrape has "LibyaAlAhrarTV", links may not)
        o = s.scalar(select(Outlet).where(func.lower(Outlet.domain) == domain.lower()).limit(1))
    else:
        o = s.scalar(select(Outlet).where(Outlet.domain == domain))
    if not o and not social:
        # Strip a subdomain level for things like arabic.cnn.com -> cnn.com if we know the parent.
        parts = domain.split(".")
        if len(parts) > 2:
            o = s.scalar(select(Outlet).where(Outlet.domain == ".".join(parts[-2:])))
    if not o:
        platform = SOCIAL.get(domain.split("/")[0])
        o = Outlet(country_id=country_id, name=(domain.split("/", 1)[1] if social else name or domain), domain=domain,
                   languages=[lang] if lang and lang != "und" else [], created_via="auto")
        s.add(o)
        s.flush()
        if platform:
            s.add(OutletCategory(outlet_id=o.id, dimension="medium", value=platform, confidence="reported",
                                 evidence_url=f"https://{domain}", note="Inferred from the link."))
        infer_scope(s, o)
    cache[domain] = o
    return o


def reassign_social(s: Session) -> dict:
    """Move posts that were filed under a whole platform (facebook.com, x.com ...) to their page."""
    platforms = [o for o in s.scalars(select(Outlet).where(Outlet.domain.in_(list(SOCIAL))))]
    cache: dict = {}
    moved = pages = 0
    for plat in platforms:
        for it in s.scalars(select(Item).where(Item.outlet_id == plat.id, Item.url.is_not(None))).all():
            social = social_outlet(it.url)
            if not social or social[0] == plat.domain:
                continue
            before = len(cache)
            o = resolve_outlet(s, it.country_id, social[0], None, it.lang, cache)
            pages += len(cache) > before
            it.outlet_id = o.id
            moved += 1
    s.commit()
    return {"moved": moved, "pages": pages}


def infer_scope(s: Session, o: Outlet) -> bool:
    """A domain under the country's TLD (e.g. .ly) is tagged scope=<country> as 'unverified',
    with the domain itself as the evidence. Uncontested; admins can override."""
    if o.country_id is None:
        return False
    c = s.get(Country, o.country_id)
    # facebook.com/almasartv.ly is a page name, not a .ly domain (and could be anyone's)
    if not c or not o.domain.endswith("." + c.iso2.lower()) or o.domain.split("/", 1)[0] in SOCIAL:
        return False
    if s.scalar(select(OutletCategory.id).where(OutletCategory.outlet_id == o.id, OutletCategory.dimension == "scope")):
        return False
    s.add(OutletCategory(outlet_id=o.id, dimension="scope", value=c.name_en.lower() if c.iso2 != "LY" else "libyan",
                         confidence="unverified", evidence_url=f"https://{o.domain}/",
                         note=f"Inferred from the .{c.iso2.lower()} domain."))
    return True


def infer_scopes(s: Session) -> int:
    n = sum(infer_scope(s, o) for o in s.scalars(select(Outlet).where(Outlet.created_via == "auto")))
    s.commit()
    return n


def tag_item(s: Session, item: Item, rules: Rules, forced_theme_ids: tuple[int, ...] = ()) -> None:
    text = " ".join(x for x in (item.title, item.snippet) if x)
    hits = classify_themes(text, rules.themes)
    needs_country = {r.theme_id for r in rules.themes if r.require_country}
    if needs_country & set(hits) and not rules.mentions_country(text):
        hits = {k: v for k, v in hits.items() if k not in needs_country}
    versions = {r.theme_id: r.version for r in rules.themes}
    existing = {it.theme_id for it in s.scalars(select(ItemTheme).where(ItemTheme.item_id == item.id))}
    strict = {r.theme_id for r in rules.themes if r.strict}
    for tid in set(hits) | set(forced_theme_ids):
        if tid in existing:
            continue
        # Strict themes: a search result the rules do not confirm is kept (for review and
        # training) but does not count as coverage.
        confirmed = tid in hits
        s.add(ItemTheme(item_id=item.id, theme_id=tid, method="rule" if confirmed else "query",
                        active=confirmed or tid not in strict, theme_version=versions.get(tid, 1)))
    region_ids = set(tag_places(text, rules.places))
    existing_r = {ir.region_id for ir in s.scalars(select(ItemRegion).where(ItemRegion.item_id == item.id))}
    for rid in region_ids - existing_r:
        s.add(ItemRegion(item_id=item.id, region_id=rid))


def store_article(s: Session, country_id: int, rules: Rules, *, url: str, title: str | None,
                  published_at: datetime, source_key: str, snippet: str | None = None,
                  lang: str | None = None, outlet_name: str | None = None, outlet_domain: str | None = None,
                  extra: dict | None = None, added_by: int | None = None,
                  forced_theme_ids: tuple[int, ...] = (), outlet_cache: dict | None = None,
                  require_theme: bool = False, kind: str = "article",
                  assume_relevant: bool = False) -> tuple[Item | None, bool]:
    """Returns (item, created). With require_theme, items matching no theme are skipped
    (outlet RSS feeds are mostly off-topic)."""
    key = url_key(url)
    existing = s.scalar(select(Item).where(Item.dedupe_key == key))
    if existing:
        if forced_theme_ids:
            tag_item(s, existing, rules, forced_theme_ids)
        return existing, False
    lang = lang or detect_lang(" ".join(x for x in (title, snippet) if x))
    if require_theme and not forced_theme_ids:
        if not classify_themes(" ".join(x for x in (title, snippet) if x), rules.themes):
            return None, False
    social = social_outlet(url)
    # A collector that knows the account keeps it when the link names only the platform
    # (youtube.com/watch?v=..., instagram.com/p/...): the post is filed on the channel.
    if social and "/" not in social[0] and outlet_domain and outlet_domain.lower().startswith(social[0] + "/"):
        social = (outlet_domain, social[1])
    # a social post belongs to its page even when a search result names the platform as the source
    domain = social[0] if social else (outlet_domain or domain_of(url))
    outlet = resolve_outlet(s, country_id, domain, None if social else outlet_name, lang,
                            outlet_cache if outlet_cache is not None else {})
    # Relevance guard for search-sourced items: the text must name the country or one of its
    # places, or come from an outlet scoped to the country. Otherwise keep it but mark it
    # not relevant (users can restore it; the decision becomes a label).
    relevant = True
    extra = dict(extra or {})
    if assume_relevant:   # the source vouches that it is about Libya. Whose post it is still matters
        extra["libya_specific_source"] = True
    if added_by is None and (why := not_counted_reason(outlet, rules.labelled_outlets)):
        relevant = False
        extra["filtered"] = why
    elif not assume_relevant and added_by is None and rules.country_terms and not passes_guard(rules, outlet.id, title, snippet):
        relevant = False
        extra["filtered"] = "no_country_mention"
    item = Item(country_id=country_id, kind=kind, source_key=source_key, dedupe_key=key, url=url,
                title=(title or "")[:1000], snippet=(snippet or "")[:600] or None, lang=lang,
                published_at=published_at, outlet_id=outlet.id, extra=extra, added_by=added_by, relevant=relevant)
    s.add(item)
    s.flush()
    tag_item(s, item, rules, forced_theme_ids)
    return item, True


def passes_guard(rules: Rules, outlet_id: int | None, title: str | None, snippet: str | None) -> bool:
    """Names the country or one of its places; or comes from a local outlet AND matches a theme
    rule (local outlets also publish world news)."""
    text = " ".join(x for x in (title, snippet) if x)
    if rules.mentions_country(text):
        return True
    return outlet_id in rules.local_outlets and bool(classify_themes(text, rules.themes))


def apply_relevance_guard(s: Session, country_id: int) -> int:
    """Re-apply the guard to existing machine-collected articles (never touches user decisions)."""
    rules = load_rules(s, country_id)
    not_counted = not_counted_outlets(s, rules.labelled_outlets)
    n = 0
    for it in s.scalars(select(Item).where(Item.country_id == country_id, Item.kind == "article",
                                           Item.added_by.is_(None))):
        if (it.extra or {}).get("user_relevance") is not None:
            continue
        reason = not_counted.get(it.outlet_id)
        prev = (it.extra or {}).get("filtered")
        if (it.extra or {}).get("libya_specific_source"):   # only the not-counted rule applies
            if reason is None and prev not in NOT_COUNTED:
                continue
            ok = reason is None
        else:
            ok = reason is None and passes_guard(rules, it.outlet_id, it.title, it.snippet)
        why = reason or (None if ok else "no_country_mention")
        if it.relevant != ok or (prev != why and (reason or prev in NOT_COUNTED)):
            it.relevant = ok
            it.extra = {**(it.extra or {}), "filtered": why}
            n += 1
    s.commit()
    return n


def not_counted_outlets(s: Session, labelled: set[int]) -> dict[int, str]:
    """outlet id -> why its items are not counted (shorteners, unlisted social accounts)."""
    return {o.id: why for o in s.scalars(select(Outlet)) if (why := not_counted_reason(o, labelled))}


CC_TLD = {"eg": "Egypt", "tn": "Tunisia", "qa": "Qatar", "ae": "United Arab Emirates", "sa": "Saudi Arabia", "tr": "Turkey",
          "it": "Italy", "fr": "France", "uk": "United Kingdom", "de": "Germany", "gr": "Greece", "mt": "Malta", "lb": "Lebanon",
          "jo": "Jordan", "ma": "Morocco", "dz": "Algeria", "sd": "Sudan", "ng": "Nigeria", "sy": "Syria", "iq": "Iraq",
          "ru": "Russia", "es": "Spain", "ch": "Switzerland", "be": "Belgium", "nl": "Netherlands", "kw": "Kuwait",
          "bh": "Bahrain", "om": "Oman", "ps": "Palestine", "il": "Israel", "td": "Chad", "ne": "Niger", "ml": "Mali",
          "ua": "Ukraine", "ca": "Canada", "au": "Australia", "in": "India", "pk": "Pakistan", "ir": "Iran",
          "at": "Austria", "se": "Sweden", "no": "Norway", "dk": "Denmark", "pt": "Portugal", "ye": "Yemen"}


def infer_bases(s: Session) -> int:
    """Fill Outlet.base_country for foreign outlets (config list first, then country-code domain).
    Never overwrites a value set by an admin. Foreign base + no scope -> scope international."""
    n = 0
    for c in s.scalars(select(Country)):
        explicit = {dom: country for country, doms in (c.config.get("outlet_bases") or {}).items() for dom in doms}
        for o in s.scalars(select(Outlet).where(Outlet.base_country.is_(None), Outlet.base_city.is_(None))):
            base = explicit.get(o.domain) or CC_TLD.get(o.domain.rsplit(".", 1)[-1])
            if not base:
                continue
            o.base_country = base
            n += 1
            if not s.scalar(select(OutletCategory.id).where(OutletCategory.outlet_id == o.id,
                                                             OutletCategory.dimension == "scope")):
                s.add(OutletCategory(outlet_id=o.id, dimension="scope", value="international", confidence="likely",
                                     evidence_url=f"https://{o.domain}/", note=f"Based in {base} (config or domain)."))
    s.commit()
    return n
