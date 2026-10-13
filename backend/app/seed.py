"""Load country, region, theme and outlet config from YAML into the database.
Idempotent: existing rows are kept (themes edited in the UI are not overwritten)."""
from datetime import date

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import settings
from .geo import centroids_by_name
from .models import Country, Outlet, OutletCategory, PlaceAlias, Region, Theme
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
                    acled_event_types=t.get("acled_event_types", []),
                    reliefweb_themes=t.get("reliefweb_themes", [])))
        n += 1
    return n


def seed_country(s: Session, file: str) -> Country:
    cfg = _load(settings.CONFIG_DIR / "countries" / file)
    c = s.scalar(select(Country).where(Country.iso2 == cfg["iso2"]))
    if not c:
        c = Country(iso2=cfg["iso2"], name_en=cfg["name_en"], name_ar=cfg["name_ar"], config={})
        s.add(c)
        s.flush()
    import json
    c.config = json.loads(json.dumps({k: v for k, v in cfg.items() if k not in ("districts", "outlets", "macro_regions")},
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
    for d in cfg["districts"]:
        r = region(d["slug"], "district", d["name_en"], d["name_ar"], macros[d["macro"]],
                   *dist_c.get(d.get("geo", ""), (None, None)))
        if r.lat is None and d.get("geo") in dist_c:
            r.lat, r.lon = dist_c[d["geo"]]
        for a in {d["name_en"], d["name_ar"], *d.get("aliases", [])}:
            norm = normalise(a).strip()
            if not s.scalar(select(PlaceAlias).where(PlaceAlias.region_id == r.id, PlaceAlias.norm == norm)):
                s.add(PlaceAlias(region_id=r.id, alias=a, norm=norm))
    for m in cfg["macro_regions"]:
        r = macros[m["slug"]]
        for a in {m["name_en"], m["name_ar"]}:
            norm = normalise(a).strip()
            if not s.scalar(select(PlaceAlias).where(PlaceAlias.region_id == r.id, PlaceAlias.norm == norm)):
                s.add(PlaceAlias(region_id=r.id, alias=a, norm=norm))

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
    for scope, domains in (cfg.get("scope_overrides") or {}).items():
        for dom in domains:
            o = s.scalar(select(Outlet).where(Outlet.domain == dom))
            if not o or s.scalar(select(OutletCategory.id).where(OutletCategory.outlet_id == o.id,
                                                                 OutletCategory.dimension == "scope")):
                continue
            s.add(OutletCategory(outlet_id=o.id, dimension="scope", value=scope, confidence="likely",
                                 evidence_url=f"https://{dom}/", note=f"From {SEED_EVIDENCE.format(file=file)} scope_overrides.",
                                 valid_from=date.today()))
    return c


def seed_all(s: Session):
    seed_themes(s)
    for f in sorted((settings.CONFIG_DIR / "countries").glob("*.yaml")):
        seed_country(s, f.name)
    s.flush()
    from .alerts import sync_specs
    sync_specs(s)
