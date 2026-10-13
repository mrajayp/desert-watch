"""Storing collected rows: dedupe, outlet resolution, theme + place tagging."""
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from sqlalchemy import select
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
    return Rules(themes, [p for p in places if p.variants], {r.id: r.parent_id for r in regions}, country_terms, local)


def resolve_outlet(s: Session, country_id: int, domain: str, name: str | None, lang: str | None,
                   cache: dict) -> Outlet:
    if domain in cache:
        return cache[domain]
    o = s.scalar(select(Outlet).where(Outlet.domain == domain))
    if not o:
        # Strip a subdomain level for things like arabic.cnn.com -> cnn.com if we know the parent.
        parts = domain.split(".")
        if len(parts) > 2:
            o = s.scalar(select(Outlet).where(Outlet.domain == ".".join(parts[-2:])))
    if not o:
        o = Outlet(country_id=country_id, name=name or domain, domain=domain,
                   languages=[lang] if lang and lang != "und" else [], created_via="auto")
        s.add(o)
        s.flush()
        infer_scope(s, o)
    cache[domain] = o
    return o


def infer_scope(s: Session, o: Outlet) -> bool:
    """A domain under the country's TLD (e.g. .ly) is tagged scope=<country> as 'unverified',
    with the domain itself as the evidence. Uncontested; admins can override."""
    if o.country_id is None:
        return False
    c = s.get(Country, o.country_id)
    if not c or not o.domain.endswith("." + c.iso2.lower()):
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
                  require_theme: bool = False) -> tuple[Item | None, bool]:
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
    outlet = resolve_outlet(s, country_id, outlet_domain or domain_of(url), outlet_name, lang,
                            outlet_cache if outlet_cache is not None else {})
    # Relevance guard for search-sourced items: the text must name the country or one of its
    # places, or come from an outlet scoped to the country. Otherwise keep it but mark it
    # not relevant (users can restore it; the decision becomes a label).
    relevant = True
    extra = dict(extra or {})
    if added_by is None and rules.country_terms and not passes_guard(rules, outlet.id, title, snippet):
        relevant = False
        extra["filtered"] = "no_country_mention"
    item = Item(country_id=country_id, kind="article", source_key=source_key, dedupe_key=key, url=url,
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
    n = 0
    for it in s.scalars(select(Item).where(Item.country_id == country_id, Item.kind == "article",
                                           Item.added_by.is_(None))):
        if (it.extra or {}).get("user_relevance") is not None:
            continue
        ok = passes_guard(rules, it.outlet_id, it.title, it.snippet)
        if it.relevant != ok:
            it.relevant = ok
            it.extra = {**(it.extra or {}), "filtered": None if ok else "no_country_mention"}
            n += 1
    s.commit()
    return n
