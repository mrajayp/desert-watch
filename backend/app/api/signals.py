"""Signals from outside the news, shown next to coverage and never scored: daily indicators
(Wikipedia pages people in Libya looked up, the dinar's exchange rates) and the Libya pages read
from Libya each day (collectors/wikireading.py)."""
from collections import defaultdict
from datetime import date, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import auth
from ..db import get_db
from ..models import Indicator, User, WikiReading
from .common import country_or_404

router = APIRouter(prefix="/api")

# indicators that do not come from the country config (collectors/fxrate.py). Keys sharing a chart are
# drawn together on one axis (same unit). style: main = the headline line, alt = a variant, ref = the reference.
FX_NOTE = ("The parallel rate is Al-Mashhad al-Libi's daily closing figure for Tripoli's market. The official rate is the "
           "Central Bank of Libya's average of buy and sell.")
FIXED = {
    "usd_lyd_parallel": {"label": "Parallel market, cash", "unit": "dinars", "theme": "economy", "chart": "usd", "style": "main", "note": FX_NOTE},
    "usd_lyd_parallel_cheque": {"label": "Parallel market, by bank cheque", "unit": "dinars", "theme": "economy", "chart": "usd", "style": "alt", "note": FX_NOTE},
    "usd_lyd_official": {"label": "Official rate", "unit": "dinars", "theme": "economy", "chart": "usd", "style": "ref", "note": FX_NOTE},
    "eur_lyd_parallel": {"label": "Parallel market, cash", "unit": "dinars", "theme": "economy", "chart": "eur", "style": "main", "note": FX_NOTE},
    "eur_lyd_official": {"label": "Official rate", "unit": "dinars", "theme": "economy", "chart": "eur", "style": "ref", "note": FX_NOTE},
}
CHARTS = {"usd": "One US dollar in Libyan dinars", "eur": "One euro in Libyan dinars"}
WIKI_NOTE = ("Wikimedia only publishes a page for a country on days it has more than about 90 views from there, "
             "and adds noise of about 35 views. A gap means fewer than about 90 views that day.")


def _meta(config: dict) -> dict:
    out = {k: dict(v, source="exchange") for k, v in FIXED.items()}
    for k, v in (config.get("wiki_indicators") or {}).items():
        out[k] = {"label": v.get("label", k), "label_ar": v.get("label_ar"), "unit": v.get("unit", "views a day"),
                  "theme": v.get("theme"), "source": "wikimedia_dp", "note": WIKI_NOTE}
    return out


@router.get("/indicators")
def indicators(country: str = "LY", days: int = 400, theme: str | None = None,
               s: Session = Depends(get_db), _: User = Depends(auth.current_user)):
    c = country_or_404(s, country)
    meta = _meta(c.config or {})
    start = date.today() - timedelta(days=max(7, min(days, 5000)))
    rows = defaultdict(list)
    for key, day, value in s.execute(select(Indicator.key, Indicator.day, Indicator.value)
                                     .where(Indicator.country_id == c.id, Indicator.day >= start)
                                     .order_by(Indicator.day)):
        rows[key].append({"day": day.isoformat(), "value": value})
    return {"charts": CHARTS,
            "indicators": [{"key": k, **m, "rows": rows.get(k, [])} for k, m in meta.items()
                           if rows.get(k) and (theme is None or m.get("theme") == theme)]}


def _url(project: str, title: str) -> str:
    return f"https://{project}.org/wiki/{quote(title)}" if project.endswith(("wikipedia", "wiktionary")) else ""


@router.get("/wiki-reading")
def wiki_reading(country: str = "LY", days: int = 30, s: Session = Depends(get_db), _: User = Depends(auth.current_user)):
    c = country_or_404(s, country)
    start = date.today() - timedelta(days=max(1, min(days, 400)))
    by_day = defaultdict(list)
    for r in s.scalars(select(WikiReading).where(WikiReading.country_id == c.id, WikiReading.day >= start)
                       .order_by(WikiReading.day.desc(), WikiReading.views.desc())):
        by_day[r.day].append({"project": r.project, "title": r.page_title.replace("_", " "), "views": r.views,
                              "url": _url(r.project, r.page_title)})
    checked = sorted(set(s.scalars(select(Indicator.day).where(Indicator.country_id == c.id, Indicator.source == "wikimedia_dp",
                                                               Indicator.day >= start)).all()), reverse=True)
    return {"note": WIKI_NOTE, "days": [{"day": d.isoformat(), "pages": by_day.get(d, [])} for d in checked]}
