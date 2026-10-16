"""GDELT DOC 2.0. Searches English machine translations only, so queries use English
terms; `sourcelang:` narrows by original language. artlist returns <=250 rows for
the last 3 months, so it is queried in 1-day windows; timelinevolraw gives long
history counts for the national trend. Limit: one request every 5 seconds."""
from datetime import date, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ingest import load_rules, store_article
from ..models import Country, CoverageSeries, Theme
from .base import STOP_AFTER, RunResult, http_client, polite_get, refused

API = "https://api.gdeltproject.org/api/v2/doc/doc"
INTERVAL = 6.0
# GDELT answers bursts with 429 or "Please limit requests". The six-hourly article run backs off 12 and 24 s
# (it shares the job lock with the hourly collectors). The long-run line, run by hand, waits 12, 24, 48, 96 s.
RETRIES, TIMELINE_RETRIES = 2, 4
LANG = {"Arabic": "ar", "English": "en", "French": "fr", "Italian": "it"}


def theme_query(country_term: str, terms: list[str], extra: str = "") -> str:
    # phrases and hyphenated words go in quotes: GDELT rejects a bare "same-sex" (illegal character)
    quoted = [f'"{t}"' if " " in t or "-" in t else t for t in terms[:8]]
    return f'{country_term} ({" OR ".join(quoted)}) {extra}'.strip()


class Refused(RuntimeError):
    """GDELT said no after its retries, or did not answer."""


def _json(client, params, retries: int = RETRIES):
    try:
        r = polite_get(client, API, params={**params, "format": "json"}, min_interval=INTERVAL, retries=retries)
    except httpx.TransportError as e:
        raise Refused(f"no answer ({type(e).__name__})") from e
    if refused(r):
        raise Refused(f"HTTP {r.status_code}: {r.text[:150]}")
    r.raise_for_status()
    if not r.text.strip().startswith("{"):
        raise RuntimeError(r.text[:200])
    return r.json()


def _stopped(res: RunResult, refusals: int) -> RunResult:
    if refusals >= STOP_AFTER:
        res.detail = f"stopped after {STOP_AFTER} refusals in a row. {res.detail}"[:500]
    return res


def collect(s: Session, *, days: int = 1) -> RunResult:
    res = RunResult()
    refusals = 0
    with http_client(timeout=60) as client:
        for country in s.scalars(select(Country)).all():
            g = country.config.get("gdelt")
            if not g:
                continue
            rules = load_rules(s, country.id)
            cache: dict = {}
            for th in s.scalars(select(Theme).where(Theme.active.is_(True))).all():
                for d in range(days):
                    if refusals >= STOP_AFTER:
                        break
                    end = datetime.utcnow().replace(minute=0, second=0, microsecond=0) - timedelta(days=d)
                    start = end - timedelta(days=1)
                    try:
                        data = _json(client, {"query": theme_query(g["country_term"], th.en_terms), "mode": "artlist",
                                              "maxrecords": 250, "sort": "datedesc",
                                              "startdatetime": start.strftime("%Y%m%d%H%M%S"),
                                              "enddatetime": end.strftime("%Y%m%d%H%M%S")})
                    except Exception as e:  # noqa: BLE001
                        refusals = refusals + 1 if isinstance(e, Refused) else 0
                        res.errors += 1
                        res.detail = f"{th.slug}: {e}"[:500]
                        continue
                    refusals = 0
                    for a in data.get("articles", []):
                        pub = datetime.strptime(a["seendate"], "%Y%m%dT%H%M%SZ")
                        _, created = store_article(
                            s, country.id, rules, url=a["url"], title=a.get("title"), published_at=pub,
                            source_key="gdelt", lang=LANG.get(a.get("language"), None),
                            outlet_domain=a.get("domain"), extra={"sourcecountry": a.get("sourcecountry")},
                            forced_theme_ids=(th.id,), outlet_cache=cache)
                        res.rows += created
                    s.commit()
    return _stopped(res, refusals)


def collect_timeline(s: Session, *, timespan: str = "24m", themes: list[str] | None = None) -> RunResult:
    """National coverage history per theme (raw article counts per day). One theme per request, each
    retried with backoff. Every theme's 'all' series comes first, so a run cut short by rate limits
    still leaves each theme a line. `themes` (slugs) limits the run. Stops after STOP_AFTER refusals in a row."""
    res = RunResult()
    refusals = 0
    with http_client(timeout=90) as client:
        for country in s.scalars(select(Country)).all():
            g = country.config.get("gdelt")
            if not g:
                continue
            q = select(Theme).where(Theme.active.is_(True)).order_by(Theme.id)
            if themes:
                q = q.where(Theme.slug.in_(themes))
            todo = s.scalars(q).all()
            for series, extra in (("all", ""), ("sourcecountry", f"sourcecountry:{g['sourcecountry']}")):
                for th in todo:
                    if refusals >= STOP_AFTER:
                        break
                    try:
                        data = _json(client, {"query": theme_query(g["country_term"], th.en_terms, extra),
                                              "mode": "timelinevolraw", "timespan": timespan}, retries=TIMELINE_RETRIES)
                    except Exception as e:  # noqa: BLE001
                        refusals = refusals + 1 if isinstance(e, Refused) else 0
                        res.errors += 1
                        res.detail = f"{th.slug}/{series}: {e}"[:500]
                        continue
                    refusals = 0
                    for tl in data.get("timeline", [])[:1]:
                        for pt in tl.get("data", []):
                            day = datetime.strptime(pt["date"][:8], "%Y%m%d").date()
                            row = s.scalar(select(CoverageSeries).where(
                                CoverageSeries.theme_id == th.id, CoverageSeries.day == day,
                                CoverageSeries.series == series))
                            if row:
                                row.value = pt["value"]
                            else:
                                s.add(CoverageSeries(country_id=country.id, theme_id=th.id, series=series,
                                                     day=day, value=pt["value"]))
                                res.rows += 1
                    s.commit()
    return _stopped(res, refusals)
