"""The outlet register programme (plan C-R2.1): scope labels at scale, honestly.

Most outlets in the register were discovered by a search (Google News, GDELT, an alert) and carry no
scope label, so nobody can say whether an article came from a Libyan outlet or from abroad. The rules
here set a scope only where a machine can be honest about its evidence, and say how sure it is:

  cctld      a foreign country-code domain (.eg, .uk, .tr ...) -> scope international, base_country from
             the domain, confidence unverified, evidence the domain itself. Never the home ccTLD: a
             .ly domain is labelled Libyan by ingest.infer_scope, except the vanity .ly domains below.
  vanity     bit.ly, ow.ly, fast.ly, rebrand.ly ... are never Libyan (config vanity_domains). They get no
             Libyan label, and a Libyan label a rule gave one earlier is closed by label-scopes --apply.
  gdelt      GDELT names the country an outlet publishes from (item.extra.sourcecountry on every GDELT
             article). When GDELT_MIN_VOTES or more of an outlet's articles agree, and at least two in
             three of them, that is a likely scope: Libyan when it names this country, else
             international with that base country. Evidence: GDELT's own article list for the domain.
  homepage   what the feed crawl (collectors/feeds.py) sees on the outlet's homepage: <html lang>,
             og:locale and mentions of the country in the title and navigation. Stored as a SUGGESTION
             only (Outlet.external.scope_suggestion) and shown prefilled on the Contribute review queue;
             a person applies or proposes it (POST /api/outlets/{id}/categories). Never applied here.
  dormant    an outlet with no counted article in DORMANT_DAYS days is dormant: GET /api/outlets hides it
             unless show_dormant=1, and the queue does not ask anyone to label it.

Political alignment is never set by a machine. A label an admin set is never touched: every rule stops
at an outlet that already has a scope. `python -m app.cli label-scopes` prints the plan (a dry run);
`--apply` writes it. The homepage rule reads nothing from the network here; the crawl stores what it
saw and this module only reads it."""
import re
from collections import Counter
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .ingest import CC_TLD, SHORTENERS, SOCIAL, USER_PLATFORMS
from .models import Country, Item, Outlet, OutletCategory, utcnow
from .textnorm import normalise, term_variants

# .ly domains that belong to no Libyan outlet (link shorteners and vanity names), when the config lists none
DEFAULT_VANITY = ("bit.ly", "ow.ly", "fast.ly", "rebrand.ly", "ad.ly", "cutt.ly", "buff.ly", "adf.ly", "gg.ly",
                  "musical.ly", "tinyurl.ly", "shorturl.ly", "snip.ly", "l.ly", "t.ly", "s.ly", "trib.ly", "url.ly",
                  "app.ly", "short.ly", "wp.ly", "fb.ly", "goo.ly", "youtu.ly", "visual.ly", "embed.ly", "bitly.ly")
GDELT_MIN_VOTES = 3           # agreeing GDELT articles before an outlet's source country counts
GDELT_AGREEMENT = 2 / 3       # ... and the share of its GDELT articles that must agree
DORMANT_DAYS = 365
GDELT_EVIDENCE = "https://api.gdeltproject.org/api/v2/doc/doc?query=domain:{domain}&mode=artlist&format=html"

# reverse map for og:locale country codes (ar_EG -> Egypt), the same names ingest.infer_bases uses; a
# locale uses the ISO code where the domain uses the ccTLD (en_GB, .uk)
_ISO2_NAME = {**{k.upper(): v for k, v in CC_TLD.items()}, "GB": "United Kingdom", "US": "United States"}


# ---------------------------------------------------------------- helpers
def home_scope(country: Country) -> str:
    """The scope value for an outlet of this country ("libyan" for Libya, else the country's name)."""
    return "libyan" if country.iso2 == "LY" else country.name_en.lower()


def vanity_domains(cfg: dict | None) -> set[str]:
    listed = (cfg or {}).get("vanity_domains")
    return {d.lower() for d in (listed if listed is not None else DEFAULT_VANITY)}


def is_vanity(domain: str, cfg: dict | None) -> bool:
    """A link shortener or vanity domain under the home ccTLD: never an outlet of the country."""
    d = domain.lower().split("/", 1)[0]
    return d in vanity_domains(cfg) or d in SHORTENERS


def is_site(domain: str) -> bool:
    """A website domain (not a social account, a whole platform, a shortener or a user platform)."""
    d = domain.lower()
    return "/" not in d and d not in SOCIAL and d not in USER_PLATFORMS and d not in SHORTENERS


def scoped_outlets(s: Session) -> set[int]:
    """Outlets with a scope label on record, active or not (a closed or rejected one still means a
    person looked): no rule here writes over any of them."""
    return set(s.scalars(select(OutletCategory.outlet_id).where(OutletCategory.dimension == "scope").distinct()))


def active_outlet_ids(s: Session, country_id: int, days: int = DORMANT_DAYS) -> set[int]:
    """Outlets with a counted article (scoring.counted_items) in the last `days` days. The rest are
    dormant: auto-discovered domains that stopped reaching us."""
    from .scoring import counted_items
    since = utcnow() - timedelta(days=days)
    return set(s.scalars(select(Item.outlet_id).where(*counted_items(country_id), Item.kind == "article",
                                                      Item.published_at >= since, Item.outlet_id.is_not(None)).distinct()))


def counted_articles(s: Session, country_id: int, days: int = DORMANT_DAYS) -> dict[int, int]:
    """outlet id -> counted articles in the last `days` days (what orders the review queue)."""
    from .scoring import counted_items
    since = utcnow() - timedelta(days=days)
    return dict(s.execute(select(Item.outlet_id, func.count(Item.id))
                          .where(*counted_items(country_id), Item.kind == "article", Item.published_at >= since,
                                 Item.outlet_id.is_not(None)).group_by(Item.outlet_id)).all())


# ---------------------------------------------------------------- the rules
def cctld_rule(o: Outlet, country: Country) -> dict | None:
    """A foreign country-code domain: international, based in that country, unverified."""
    if not is_site(o.domain):
        return None
    tld = o.domain.lower().rsplit(".", 1)[-1]
    if tld == country.iso2.lower() or tld not in CC_TLD:
        return None
    return {"rule": "cctld", "scope": "international", "base_country": CC_TLD[tld], "confidence": "unverified",
            "evidence": f"https://{o.domain}/", "note": f"Based in {CC_TLD[tld]} (.{tld} domain)."}


def gdelt_votes(s: Session, country_id: int) -> dict[int, Counter]:
    """outlet id -> Counter of the source countries GDELT gave its articles (item.extra.sourcecountry)."""
    out: dict[int, Counter] = {}
    rows = s.execute(select(Item.outlet_id, func.json_extract(Item.extra, "$.sourcecountry"), func.count(Item.id))
                     .where(Item.country_id == country_id, Item.source_key == "gdelt", Item.kind == "article",
                            Item.outlet_id.is_not(None))
                     .group_by(Item.outlet_id, func.json_extract(Item.extra, "$.sourcecountry"))).all()
    for oid, sc, n in rows:
        if sc:
            out.setdefault(oid, Counter())[str(sc)] += int(n)
    return out


def gdelt_rule(o: Outlet, votes: Counter | None, country: Country) -> dict | None:
    """GDELT_MIN_VOTES agreeing GDELT articles, at least GDELT_AGREEMENT of the outlet's: a likely scope."""
    if not votes or not is_site(o.domain):
        return None
    top, n = votes.most_common(1)[0]
    total = sum(votes.values())
    if n < GDELT_MIN_VOTES or n < GDELT_AGREEMENT * total:
        return None
    evidence = GDELT_EVIDENCE.format(domain=o.domain)
    note = f"GDELT lists {n} of {total} of its articles as published from {top} (sourcecountry)."
    if top.strip().lower() == country.name_en.lower():
        return {"rule": "gdelt", "scope": home_scope(country), "base_country": None, "confidence": "likely",
                "evidence": evidence, "note": note}
    return {"rule": "gdelt", "scope": "international", "base_country": top, "confidence": "likely",
            "evidence": evidence, "note": note}


# ---------------------------------------------------------------- homepage signals (suggestion only)
_HTML_LANG = re.compile(r"<html\b[^>]*?\blang\s*=\s*[\"']?([A-Za-z]{2,3}(?:[-_][A-Za-z]{2,4})?)", re.I)
_META = re.compile(r"<meta\b[^>]*>", re.I)
_ATTR = re.compile(r"([\w:-]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'>]+))")
_TITLE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.I | re.S)
_NAV = re.compile(r"<(?:nav|header)\b[^>]*>(.*?)</(?:nav|header)>", re.I | re.S)
_TAGS = re.compile(r"<[^>]+>")


def _attrs(tag: str) -> dict:
    # findall gives '' for the quoting styles that did not match, so the first non-empty value is the one
    return {k.lower(): (a or b or c) for k, a, b, c in _ATTR.findall(tag)}


def country_terms(country: Country) -> list[str]:
    names = [country.name_en, country.name_ar, *(country.config.get("demonyms") or [])]
    return sorted({v for t in names for v in term_variants(t)})


def _mentions(text: str, terms: list[str]) -> int:
    n = " " + normalise(_TAGS.sub(" ", text)) + " "
    return sum(n.count(f" {t} ") for t in terms)


def homepage_signals(html: str, country: Country) -> dict:
    """What a homepage says about where the outlet is from: the <html lang>, og:locale, and how often the
    title and the navigation name the country. Reads the first 300 KB only."""
    html = html[:300_000]
    lang = (_HTML_LANG.search(html) or [None, None])[1]
    locale = None
    for tag in _META.findall(html):
        a = _attrs(tag)
        if (a.get("property") or a.get("name") or "").lower() == "og:locale" and a.get("content"):
            locale = a["content"].strip()
            break
    terms = country_terms(country)
    title = (_TITLE.search(html) or [None, ""])[1]
    nav = " ".join(_NAV.findall(html))
    return {"lang": lang.lower().replace("_", "-") if lang else None, "locale": locale,
            "title_mentions": _mentions(title, terms), "nav_mentions": _mentions(nav, terms)}


def suggestion_from_signals(sig: dict, country: Country, url: str) -> dict | None:
    """A scope suggestion from homepage signals, always unverified; None when they say nothing. The
    country named in the title or the navigation comes first: an og:locale is often a theme's default
    (ar_AR, ar_SA, en_US on Arabic WordPress sites) and says little on its own."""
    locale = (sig.get("locale") or "").replace("-", "_")
    cc = locale.split("_", 1)[1].upper() if "_" in locale else None
    if sig.get("title_mentions", 0) >= 1 or sig.get("nav_mentions", 0) >= 2 or cc == country.iso2:
        if cc == country.iso2 and not sig.get("title_mentions") and sig.get("nav_mentions", 0) < 2:
            note = f"The homepage says og:locale {locale}."
        else:
            note = f"The homepage names {country.name_en} in its {'title' if sig.get('title_mentions') else 'navigation'}."
        return {"rule": "homepage", "scope": home_scope(country), "base_country": None, "confidence": "unverified",
                "evidence": url, "note": note}
    if cc and cc in _ISO2_NAME:
        return {"rule": "homepage", "scope": "international", "base_country": _ISO2_NAME[cc], "confidence": "unverified",
                "evidence": url, "note": f"The homepage says og:locale {locale}."}
    return None


def store_suggestion(o: Outlet, html: str, url: str, country: Country, today: date | None = None) -> dict | None:
    """Keep what the crawl saw on the homepage as a suggestion on the outlet (never a label). Returns it."""
    sig = homepage_signals(html, country)
    sug = suggestion_from_signals(sig, country, url)
    ext = {k: v for k, v in (o.external or {}).items() if k != "scope_suggestion"}
    if sug:
        ext["scope_suggestion"] = {**sug, "signals": sig, "at": (today or date.today()).isoformat()}
    o.external = ext
    return sug


# ---------------------------------------------------------------- what the queue shows
def suggestion_for(o: Outlet, country: Country, votes: Counter | None = None, has_scope: bool = False) -> dict | None:
    """The suggestion the review queue prefills for one outlet: a rule's proposal when it has no scope
    (cctld, then gdelt), else the homepage suggestion the crawl stored. {scope, base_country,
    confidence, evidence, rule, note} or None."""
    if not has_scope:
        for prop in (cctld_rule(o, country), gdelt_rule(o, votes, country)):
            if prop:
                return prop
    stored = (o.external or {}).get("scope_suggestion")
    if stored and stored.get("scope"):
        return {k: stored.get(k) for k in ("rule", "scope", "base_country", "confidence", "evidence", "note")}
    return None


# ---------------------------------------------------------------- the plan and its application
def plan(s: Session, country: Country, today: date | None = None) -> dict:
    """What label-scopes would write, per rule, plus the counts behind it. Reads only."""
    today = today or date.today()
    scoped = scoped_outlets(s)
    votes = gdelt_votes(s, country.id)
    alive = active_outlet_ids(s, country.id, DORMANT_DAYS)
    vanity = vanity_domains(country.config)
    out = {"country": country.iso2, "cctld": [], "gdelt": [], "vanity": [], "suggestions": 0, "outlets": 0,
           "unlabelled": 0, "unlabelled_with_articles": 0, "dormant": 0}
    machine_libyan = {}
    for c in s.scalars(select(OutletCategory).where(OutletCategory.dimension == "scope", OutletCategory.status == "active",
                                                    OutletCategory.valid_to.is_(None), OutletCategory.set_by.is_(None))):
        machine_libyan[c.outlet_id] = c
    for o in s.scalars(select(Outlet).where(Outlet.active.is_(True), Outlet.country_id == country.id)):
        out["outlets"] += 1
        if o.id not in alive:
            out["dormant"] += 1
        if ((o.external or {}).get("scope_suggestion") or {}).get("scope"):
            out["suggestions"] += 1
        if o.domain.lower().split("/", 1)[0] in vanity:
            cat = machine_libyan.get(o.id)
            if cat and cat.value == home_scope(country):
                out["vanity"].append({"outlet_id": o.id, "domain": o.domain, "category_id": cat.id})
            continue
        if o.id in scoped:
            continue
        out["unlabelled"] += 1
        if o.id in alive:
            out["unlabelled_with_articles"] += 1
        prop = cctld_rule(o, country) or gdelt_rule(o, votes.get(o.id), country)
        if prop:
            out[prop["rule"]].append({"outlet_id": o.id, "domain": o.domain, **prop})
    return out


def apply(s: Session, p: dict, today: date | None = None) -> dict:
    """Write the plan: a scope label per cctld and gdelt proposal (base_country filled when empty), and
    close the Libyan label of every vanity domain. Never alignment, never a label a person set."""
    today = today or date.today()
    n = Counter()
    for rule in ("cctld", "gdelt"):
        for prop in p.get(rule, []):
            o = s.get(Outlet, prop["outlet_id"])
            if o is None or s.scalar(select(OutletCategory.id).where(OutletCategory.outlet_id == o.id,
                                                                     OutletCategory.dimension == "scope")):
                continue   # labelled since the plan was made
            s.add(OutletCategory(outlet_id=o.id, dimension="scope", value=prop["scope"], confidence=prop["confidence"],
                                 evidence_url=prop["evidence"], note=prop["note"], status="active", valid_from=today))
            if prop.get("base_country") and not o.base_country:
                o.base_country = prop["base_country"]
            n[rule] += 1
    for v in p.get("vanity", []):
        cat = s.get(OutletCategory, v["category_id"])
        if cat and cat.valid_to is None and cat.set_by is None:
            cat.valid_to = today
            cat.note = ((cat.note or "") + " Closed: a vanity .ly domain, not a Libyan outlet.").strip()
            n["vanity"] += 1
    s.commit()
    return dict(n)


def report(p: dict, applied: dict | None = None) -> str:
    """The dry-run report label-scopes prints."""
    head = "APPLIED" if applied is not None else "DRY RUN (nothing written)"
    lines = [f"{head}: register of {p['country']}: {p['outlets']} active outlets, {p['unlabelled']} without a scope "
             f"({p['unlabelled_with_articles']} of them with a counted article in {DORMANT_DAYS} days), "
             f"{p['dormant']} dormant (hidden from the list), {p['suggestions']} homepage suggestions on record "
             f"(never applied by a machine)"]
    for rule, title in (("cctld", "foreign country-code domain -> international (unverified)"),
                        ("gdelt", f"GDELT source country, {GDELT_MIN_VOTES}+ agreeing articles -> likely"),
                        ("vanity", "vanity .ly domain: Libyan label closed")):
        rows = p.get(rule, [])
        done = f", {applied.get(rule, 0)} written" if applied is not None else ""
        lines.append(f"{rule}: {len(rows)}{done}  ({title})")
        for r in rows[:12]:
            lines.append(f"  {r['domain']}: {r.get('scope', '')} {r.get('base_country') or ''}".rstrip())
        if len(rows) > 12:
            lines.append(f"  ... and {len(rows) - 12} more")
    lines.append("Alignment is never set by a machine; homepage signals are suggestions for the Contribute queue only.")
    return "\n".join(lines)


def run(s: Session, apply_now: bool = False, out=print) -> dict:
    """The CLI: a plan per country, printed; written with --apply."""
    results = []
    for c in s.scalars(select(Country)):
        p = plan(s, c)
        applied = apply(s, p) if apply_now else None
        out(report(p, applied))
        results.append({"country": c.iso2, "cctld": len(p["cctld"]), "gdelt": len(p["gdelt"]), "vanity": len(p["vanity"]),
                        "applied": applied})
    return {"countries": results, "changed": sum(sum((r["applied"] or {}).values()) for r in results)}
