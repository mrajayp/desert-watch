"""Load country, region, theme and outlet config from YAML into the database.
Idempotent: existing rows are kept (themes edited in the UI are not overwritten)."""
from datetime import date

import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import settings
from .geo import centroids_by_name
from .models import Country, Outlet, OutletCategory, PlaceAlias, Region, Theme, utcnow
from .textnorm import normalise

SEED_EVIDENCE = "config/countries/{file}"


def _load(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def seed_themes(s: Session) -> int:
    data = _load(settings.CONFIG_DIR / "themes.yaml")
    n = 0
    for t in data["themes"]:
        if s.scalar(select(Theme).where(Theme.slug == t["slug"])):
            continue
        s.add(Theme(slug=t["slug"], group=t.get("group"), name_en=t["name_en"], name_ar=t["name_ar"],
                    en_terms=t.get("en_terms", []), ar_terms=t.get("ar_terms", []),
                    exclude=t.get("exclude", []), cooc=t.get("cooc", []), strict=bool(t.get("strict", False)),
                    require_country=bool(t.get("require_country", False)),
                    veto=t.get("veto", []), mask=t.get("mask", []),
                    cooc_veto_context=t.get("cooc_veto_context", []),
                    acled_event_types=t.get("acled_event_types", []),
                    reliefweb_themes=t.get("reliefweb_themes", []), active=bool(t.get("active", True))))
        n += 1
    return n


TERM_FIELDS = ("en_terms", "ar_terms", "exclude", "cooc", "veto", "mask", "cooc_veto_context")


def apply_theme_terms(s: Session, slugs: list[str]) -> dict[str, list[str]]:
    """Copy only the term fields of the named themes from themes.yaml into the database. Every
    other field, and every other theme, stays as edited in Admin. A changed theme gets a new
    version. Returns the changed fields per theme (re-tag afterwards with retag-all)."""
    data = {t["slug"]: t for t in _load(settings.CONFIG_DIR / "themes.yaml")["themes"]}
    out = {}
    for slug in slugs:
        th = s.scalar(select(Theme).where(Theme.slug == slug))
        if slug not in data or not th:
            raise ValueError(f"{slug}: not in {'themes.yaml' if slug not in data else 'the database'}")
        changed = [k for k in TERM_FIELDS if (getattr(th, k) or []) != data[slug].get(k, [])]
        for k in changed:
            setattr(th, k, data[slug].get(k, []))
        if changed:
            th.version += 1
            th.updated_at = utcnow()
        out[slug] = changed
    return out


def seed_country(s: Session, file: str) -> Country:
    cfg = _load(settings.CONFIG_DIR / "countries" / file)
    c = s.scalar(select(Country).where(Country.iso2 == cfg["iso2"]))
    if not c:
        c = Country(iso2=cfg["iso2"], name_en=cfg["name_en"], name_ar=cfg["name_ar"], config={})
        s.add(c)
        s.flush()
    import json
    c.config = json.loads(json.dumps({k: v for k, v in cfg.items() if k not in ("districts", "outlets", "macro_regions",
                                                                                 "youtube_channels", "social_parents")},
                                     default=str, ensure_ascii=False))  # YAML dates -> ISO strings
    c.config["config_file"] = file
    c.config["district_geo"] = {d["slug"]: d.get("geo") for d in cfg["districts"]}

    def region(slug, level, name_en, name_ar, parent=None, lat=None, lon=None):
        r = s.scalar(select(Region).where(Region.country_id == c.id, Region.slug == slug))
        if not r:
            r = Region(country_id=c.id, slug=slug, level=level, name_en=name_en, name_ar=name_ar,
                       parent_id=parent.id if parent else None, lat=lat, lon=lon)
            s.add(r)
            s.flush()
        return r

    b = cfg.get("boundaries", {})
    geo_dir = settings.CONFIG_DIR / "geo"
    dist_c = centroids_by_name(geo_dir / b["districts_geojson"]) if b.get("districts_geojson") else {}
    macro_c = centroids_by_name(geo_dir / b["macro_geojson"]) if b.get("macro_geojson") else {}
    macro_geo = b.get("macro_geo_names", {})
    lats = [c[0] for c in dist_c.values()] or [None]
    lons = [c[1] for c in dist_c.values()] or [None]
    nat_ll = (sum(lats) / len(lats), sum(lons) / len(lons)) if dist_c else (None, None)

    national = region("national", "national", cfg["name_en"], cfg["name_ar"], None, *nat_ll)
    macros = {m["slug"]: region(m["slug"], "macro", m["name_en"], m["name_ar"], national,
                                *macro_c.get(macro_geo.get(m["slug"], ""), (None, None)))
              for m in cfg["macro_regions"]}
    # aliases that are also common words or places elsewhere (config `ambiguous_aliases`); the flag
    # follows the config on every seed, so a list change reaches existing rows
    ambiguous = {normalise(a).strip() for a in cfg.get("ambiguous_aliases") or []}

    def alias(r, a):
        norm = normalise(a).strip()
        row = s.scalar(select(PlaceAlias).where(PlaceAlias.region_id == r.id, PlaceAlias.norm == norm))
        if not row:
            s.add(PlaceAlias(region_id=r.id, alias=a, norm=norm, ambiguous=norm in ambiguous))
        elif bool(row.ambiguous) != (norm in ambiguous):
            row.ambiguous = norm in ambiguous

    for d in cfg["districts"]:
        r = region(d["slug"], "district", d["name_en"], d["name_ar"], macros[d["macro"]],
                   *dist_c.get(d.get("geo", ""), (None, None)))
        if r.lat is None and d.get("geo") in dist_c:
            r.lat, r.lon = dist_c[d["geo"]]
        for a in {d["name_en"], d["name_ar"], *d.get("aliases", [])}:
            alias(r, a)
    for m in cfg["macro_regions"]:
        for a in {m["name_en"], m["name_ar"]}:
            alias(macros[m["slug"]], a)

    cities = cfg.get("cities", {})
    for o in cfg.get("outlets", []):
        out = s.scalar(select(Outlet).where(Outlet.domain == o["domain"]))
        if out:
            continue
        city = o.get("base_city")
        lat, lon = cities.get(city, (None, None)) if city else (None, None)
        out = Outlet(country_id=c.id, name=o["name"], domain=o["domain"], languages=o.get("languages", []),
                     rss_url=o.get("rss"), base_city=city, base_country=o.get("base_country"),
                     lat=lat, lon=lon, created_via="seed")
        s.add(out)
        s.flush()
        # Uncontested dimensions only; evidence = the config file + outlet homepage.
        for dim, val in (("scope", o.get("scope")), ("medium", o.get("medium")), ("type", o.get("type"))):
            if val:
                s.add(OutletCategory(outlet_id=out.id, dimension=dim, value=val, confidence="unverified",
                                     evidence_url=f"https://{o['domain']}/",
                                     note=f"Seeded from {SEED_EVIDENCE.format(file=file)}; verify.",
                                     valid_from=date.today()))
        if o.get("scope") == "international" and not o.get("type"):
            s.add(OutletCategory(outlet_id=out.id, dimension="type", value="international",
                                 confidence="unverified", evidence_url=f"https://{o['domain']}/",
                                 note="Seeded; verify.", valid_from=date.today()))
    from .models import KeyEvent, Theme as _Theme
    slug_ids = {t.slug: t.id for t in s.scalars(select(_Theme))}
    for e in cfg.get("events", []) or []:
        day = e["date"] if isinstance(e["date"], date) else date.fromisoformat(str(e["date"]))
        row = s.scalar(select(KeyEvent).where(KeyEvent.country_id == c.id, KeyEvent.day == day, KeyEvent.label == e["label"]))
        if not row and e.get("source"):
            # a config event reworded later (the day and the source stayed): rename the row, never add a twin
            row = s.scalar(select(KeyEvent).where(KeyEvent.country_id == c.id, KeyEvent.day == day,
                                                  KeyEvent.source_url == e["source"], KeyEvent.origin == "config"))
            if row:
                row.label = e["label"]
        if not row:
            s.add(KeyEvent(country_id=c.id, day=day, label=e["label"], label_ar=e.get("label_ar"),
                           theme_id=slug_ids.get(e.get("theme")), source_url=e.get("source", ""), origin="config"))
        elif row.label_ar != e.get("label_ar"):
            row.label_ar = e.get("label_ar")     # Arabic labels added to the config later
    for scope, domains in (cfg.get("scope_overrides") or {}).items():
        for dom in domains:
            o = s.scalar(select(Outlet).where(Outlet.domain == dom))
            if not o or s.scalar(select(OutletCategory.id).where(OutletCategory.outlet_id == o.id,
                                                                 OutletCategory.dimension == "scope")):
                continue
            s.add(OutletCategory(outlet_id=o.id, dimension="scope", value=scope, confidence="likely",
                                 evidence_url=f"https://{dom}/", note=f"From {SEED_EVIDENCE.format(file=file)} scope_overrides.",
                                 valid_from=date.today()))
    seed_social_accounts(s, c, cfg, file)
    return c


YOUTUBE_FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={id}"


def seed_social_accounts(s: Session, c: Country, cfg: dict, file: str) -> None:
    """YouTube channels (created, read through their feed) and social accounts that an outlet's own
    website links to (existing outlets only). Each gets external.parent = that website and the
    website's scope/type. Idempotent, and a label an admin has closed is never put back. The feed and
    the parent are filled once (external.seed_filled lists them), so a feed or parent an admin
    cleared stays cleared."""
    for ch in cfg.get("youtube_channels") or []:
        dom = f"youtube.com/channel/{ch['id']}"
        o = s.scalar(select(Outlet).where(func.lower(Outlet.domain) == dom.lower()))
        if not o:
            o = Outlet(country_id=c.id, name=ch["name"], domain=dom, languages=ch.get("languages", []),
                       created_via="seed", external={})
            s.add(o)
            s.flush()
            s.add(OutletCategory(outlet_id=o.id, dimension="medium", value="youtube", confidence="reported",
                                 evidence_url=f"https://www.youtube.com/channel/{ch['id']}",
                                 note=f"Seeded from {SEED_EVIDENCE.format(file=file)}.", valid_from=date.today()))
        if _fill_once(o, "rss_url") and not o.rss_url:
            o.rss_url = YOUTUBE_FEED.format(id=ch["id"])
        _link_parent(s, o, ch["parent"], ch, file)
    for site, accounts in (cfg.get("social_parents") or {}).items():
        for dom in accounts:
            o = s.scalar(select(Outlet).where(func.lower(Outlet.domain) == dom.lower()))
            if o:
                _link_parent(s, o, site, {}, file)


def _fill_once(o: Outlet, field: str) -> bool:
    """True the first time the seed handles this field on this outlet (it may then fill it if empty),
    False ever after. Notes the field in external.seed_filled."""
    done = (o.external or {}).get("seed_filled") or []
    if field in done:
        return False
    o.external = {**(o.external or {}), "seed_filled": [*done, field]}
    return True


def _link_parent(s: Session, o: Outlet, site: str, fallback: dict, file: str) -> None:
    if _fill_once(o, "parent") and not (o.external or {}).get("parent"):
        o.external = {**(o.external or {}), "parent": site}
    parent = s.scalar(select(Outlet).where(Outlet.domain == site))
    for dim in ("scope", "type"):  # never alignment
        if s.scalar(select(OutletCategory.id).where(OutletCategory.outlet_id == o.id, OutletCategory.dimension == dim)):
            continue
        src = parent and s.scalar(select(OutletCategory).where(
            OutletCategory.outlet_id == parent.id, OutletCategory.dimension == dim, OutletCategory.status == "active",
            OutletCategory.valid_to.is_(None)))
        if src:
            value, conf, note = src.value, src.confidence, f"Copied from {site}, the website that links this account."
        elif fallback.get(dim):
            value, conf, note = fallback[dim], "likely", f"From {SEED_EVIDENCE.format(file=file)}. {site} links this account."
        else:
            continue
        s.add(OutletCategory(outlet_id=o.id, dimension=dim, value=value, confidence=conf, evidence_url=f"https://{site}/",
                             note=note, valid_from=date.today()))


def seed_all(s: Session):
    seed_themes(s)
    for f in sorted((settings.CONFIG_DIR / "countries").glob("*.yaml")):
        seed_country(s, f.name)
    s.flush()
    from .alerts import sync_specs
    sync_specs(s)
