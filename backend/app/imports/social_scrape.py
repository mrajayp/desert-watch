"""Load the converted social-media scrape (scripts/convert_social_scrape.py output).

  * news domains -> outlets (created if new, RSS added when a feed was found), with the scrape's
    per-domain totals stored under outlet.external["social_media_scrape"]
  * Facebook pages (media / official) -> unmonitored outlets: the Facebook blind-spot register
  * labels -> scrape_source_type / scrape_affiliation categories, confidence "disputed",
    attributed to "Social Media scraped data"; organisations only
Idempotent: re-running updates metrics and leaves existing labels in place."""
import json
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Country, Outlet, OutletCategory

EVIDENCE = "source:social-media-scrape-2023-24"


def _label(s: Session, outlet: Outlet, dim: str, value: str | None, note: str) -> int:
    if not value:
        return 0
    if s.scalar(select(OutletCategory.id).where(OutletCategory.outlet_id == outlet.id, OutletCategory.dimension == dim,
                                                OutletCategory.valid_to.is_(None))):
        return 0
    s.add(OutletCategory(outlet_id=outlet.id, dimension=dim, value=value, confidence="disputed",
                         evidence_url=EVIDENCE, note=note, status="active", valid_from=date.today()))
    return 1


def run(s: Session, path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    src, period = data["source"], data["period"]
    note = f"As published in {src} ({period['from']} to {period['to']}). Not verified by Desert Watch."
    country = s.scalar(select(Country).where(Country.iso2 == "LY"))
    stats = {"domains_new": 0, "domains_updated": 0, "rss_added": 0, "fb_pages": 0, "labels": 0}
    for d in data["domains"]:
        o = s.scalar(select(Outlet).where(Outlet.domain == d["host"]))
        if not o:
            o = Outlet(country_id=country.id, name=d["name"], domain=d["host"], languages=[], created_via="import")
            s.add(o)
            s.flush()
            stats["domains_new"] += 1
            if d.get("libyan"):
                s.add(OutletCategory(outlet_id=o.id, dimension="scope", value="libyan", confidence="likely",
                                     evidence_url=f"https://{d['host']}/", note=f"Listed as a Libyan news domain in {src}."))
        else:
            stats["domains_updated"] += 1
        if d.get("rss") and not o.rss_url:
            o.rss_url = d["rss"]
            stats["rss_added"] += 1
        o.external = {**(o.external or {}), "social_media_scrape": {
            "source": src, "period": period, "articles": d["articles"], "fb_posts": d["fb_posts"],
            "fb_engagement": d["fb_engagement"], "tweets": d["tweets"]}}
        stats["labels"] += _label(s, o, "scrape_source_type", d.get("source_type"), note)
        stats["labels"] += _label(s, o, "scrape_affiliation", d.get("affiliation"), note)
    for p in data["facebook_pages"]:
        dom = f"facebook.com/{p['page']}"
        o = s.scalar(select(Outlet).where(Outlet.domain == dom))
        if not o:
            o = Outlet(country_id=country.id, name=p["page"], domain=dom, languages=["ar"], created_via="import",
                       monitored=False)
            s.add(o)
            s.flush()
            s.add(OutletCategory(outlet_id=o.id, dimension="medium", value="facebook", confidence="reported",
                                 evidence_url=f"https://www.facebook.com/{p['page']}", note=f"Facebook page listed in {src}."))
            if p["kind"] == "official":
                s.add(OutletCategory(outlet_id=o.id, dimension="type", value="state", confidence="likely",
                                     evidence_url=f"https://www.facebook.com/{p['page']}", note="Official/government page (by name)."))
        o.monitored = False
        o.external = {**(o.external or {}), "social_media_scrape": {
            "source": src, "period": period, "kind": p["kind"], "posts": p["posts"], "interactions": p["interactions"],
            "comments": p["comments"], "shares": p["shares"], "link": p["link"]}}
        stats["fb_pages"] += 1
        stats["labels"] += _label(s, o, "scrape_source_type", p.get("source_type"), note)
        stats["labels"] += _label(s, o, "scrape_affiliation", p.get("affiliation"), note)
    s.commit()
    return stats
