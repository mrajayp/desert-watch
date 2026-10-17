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

# indicators that do not come from the country config (filled by other collectors)
FIXED = {
    "usd_lyd_parallel": {"label": "US dollar in dinars on the parallel market", "unit": "dinars", "theme": "economy"},
    "usd_lyd_official": {"label": "US dollar in dinars at the official rate", "unit": "dinars", "theme": "economy"},
}
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
    start = date.today() - timedelta(days=max(7, min(days, 1500)))
    rows = defaultdict(list)
    for key, day, value in s.execute(select(Indicator.key, Indicator.day, Indicator.value)
                                     .where(Indicator.country_id == c.id, Indicator.day >= start)
                                     .order_by(Indicator.day)):
        rows[key].append({"day": day.isoformat(), "value": value})
    return {"indicators": [{"key": k, **m, "rows": rows.get(k, [])} for k, m in meta.items()
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
