"""Keyed providers for the search lens. They give the same rows as scripts/fetch_gtrends.py, which
is the default route (fetched locally, loaded with `import-search`). Both are off until configured.

  official  The Google Trends API (consistent scaling, 1,800 days, ISO 3166-2 regions) is a closed
            alpha: apply at developers.google.com/search/apis/trends. Stub only.
  serpapi   SerpApi's google_trends engine (free tier: 250 searches a month; a run is 2-4 searches).
            Legal risk: Google sued SerpApi on 19 Dec 2025 over scraping its results (DMCA). The first
            complaint was dismissed in July 2026, Google filed an amended one on 10 Aug 2026, and a
            hearing on a second motion to dismiss was set for 29 Sep 2026 (no outcome found by
            2026-10-16). The owner decides before setting SERPAPI_KEY. SerpApi reads the same widget,
            so the anchor, rounding, sampling and privacy-threshold limits all still apply.

Unkeyed calls to trends.google.com must never run from the server."""
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import gtrends, settings
from ..models import Country
from .base import AwaitingKey

SERPAPI = "https://serpapi.com/search.json"


def official(g: dict, **kw) -> list[dict]:
    if not settings.GOOGLE_TRENDS_API_KEY:
        raise AwaitingKey("The official Google Trends API is a closed alpha. Apply at "
                          "developers.google.com/search/apis/trends, then set GOOGLE_TRENDS_API_KEY.")
    # TODO(official API): once access is granted, request each list on its own (scaling is
    # consistent across requests, so no anchor is needed) and return rows via gtrends.build_rows.
    raise NotImplementedError("Google Trends API: waiting for alpha access")


def _serpapi_points(data: dict) -> list[dict]:
    """SerpApi timeline -> the points gtrends.build_rows takes. A "0" is a week Google held back
    (below its threshold). Rounded-down weeks read "<1"."""
    out = []
    for p in (data.get("interest_over_time") or {}).get("timeline_data", []):
        vals = p["values"]
        out.append({"day": datetime.fromtimestamp(int(p["timestamp"]), tz=timezone.utc).date(),
                    "values": [int(v.get("extracted_value") or 0) for v in vals],
                    "has_data": [str(v.get("value")) != "0" for v in vals],
                    "partial": bool(p.get("partial_data"))})
    return out


def serpapi(g: dict, *, daily: bool = False, transport=None, today: date | None = None) -> list[dict]:
    if not settings.SERPAPI_KEY:
        raise AwaitingKey("Set SERPAPI_KEY to fetch search interest through SerpApi (off by default: "
                          "see the note on Google's lawsuit in collectors/gtrends.py).")
    today = today or datetime.now(timezone.utc).date()
    windows = [("week", "today 5-y")]
    if daily:
        windows.append(("day", f"{(today - timedelta(days=gtrends.DAILY_MAX_DAYS - 1)).isoformat()} {today.isoformat()}"))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rows = []
    with httpx.Client(timeout=60, transport=transport, headers={"User-Agent": settings.USER_AGENT}) as client:
        for res, when in windows:
            for k, grp in enumerate(gtrends.groups(g), 1):
                slots = [(sl, g["baskets"][sl]) for sl in grp]
                q = ",".join([gtrends.slot(t) for _, t in slots] + [g["anchor"]])
                r = client.get(SERPAPI, params={"engine": "google_trends", "q": q, "geo": g.get("geo", "LY"),
                                                "date": when, "data_type": "TIMESERIES", "tz": "-120",
                                                "api_key": settings.SERPAPI_KEY})
                r.raise_for_status()
                rows += gtrends.build_rows(_serpapi_points(r.json()), slots, g["anchor"], resolution=res,
                                           request_id=f"serpapi-{stamp}-{res}{k}",
                                           fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                           geo=g.get("geo", "LY"), provider="serpapi")
    return rows


PROVIDERS = {"official": official, "serpapi": serpapi}


def collect_and_import(s: Session, *, provider: str = "serpapi", daily: bool = False, country_iso2: str = "LY",
                       **kw) -> dict:
    from ..imports.search_trends import import_rows
    c = s.scalar(select(Country).where(Country.iso2 == country_iso2))
    g = gtrends.config(c.config or {}) if c else None
    if not g:
        return {"error": f"no gtrends config for {country_iso2}"}
    try:
        rows = PROVIDERS[provider](g, daily=daily, **kw)
    except AwaitingKey as e:
        return {"awaiting_key": str(e)}
    return import_rows(s, rows, country_iso2=country_iso2, provider=provider)
