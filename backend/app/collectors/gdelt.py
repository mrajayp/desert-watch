"""GDELT DOC 2.0. Searches English machine translations only, so queries use English
terms; `sourcelang:` narrows by original language. artlist returns <=250 rows for
the last 3 months, so it is queried in 1-day windows; timelinevolraw gives long
history counts for the national trend. Limit: one request every 5 seconds."""
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ingest import load_rules, store_article
from ..models import Country, CoverageSeries, Theme
from .base import RunResult, http_client, polite_get

API = "https://api.gdeltproject.org/api/v2/doc/doc"
INTERVAL = 6.0
LANG = {"Arabic": "ar", "English": "en", "French": "fr", "Italian": "it"}


def theme_query(country_term: str, terms: list[str], extra: str = "") -> str:
    quoted = [f'"{t}"' if " " in t else t for t in terms[:8]]
    return f'{country_term} ({" OR ".join(quoted)}) {extra}'.strip()


def _json(client, params):
    r = polite_get(client, API, params={**params, "format": "json"}, min_interval=INTERVAL)
    r.raise_for_status()
    if not r.text.strip().startswith("{"):
        raise RuntimeError(r.text[:200])
    return r.json()


def collect(s: Session, *, days: int = 1) -> RunResult:
    res = RunResult()
    with http_client(timeout=60) as client:
        for country in s.scalars(select(Country)):
            g = country.config.get("gdelt")
            if not g:
                continue
            rules = load_rules(s, country.id)
            cache: dict = {}
            for th in s.scalars(select(Theme).where(Theme.active.is_(True))):
                for d in range(days):
                    end = datetime.utcnow().replace(minute=0, second=0, microsecond=0) - timedelta(days=d)
                    start = end - timedelta(days=1)
                    try:
                        data = _json(client, {"query": theme_query(g["country_term"], th.en_terms), "mode": "artlist",
                                              "maxrecords": 250, "sort": "datedesc",
                                              "startdatetime": start.strftime("%Y%m%d%H%M%S"),
                                              "enddatetime": end.strftime("%Y%m%d%H%M%S")})
                    except Exception as e:  # noqa: BLE001
                        res.errors += 1
                        res.detail = f"{th.slug}: {e}"[:500]
                        continue
                    for a in data.get("articles", []):
                        pub = datetime.strptime(a["seendate"], "%Y%m%dT%H%M%SZ")
                        _, created = store_article(
                            s, country.id, rules, url=a["url"], title=a.get("title"), published_at=pub,
                            source_key="gdelt", lang=LANG.get(a.get("language"), None),
                            outlet_domain=a.get("domain"), extra={"sourcecountry": a.get("sourcecountry")},
                            forced_theme_ids=(th.id,), outlet_cache=cache)
                        res.rows += created
                    s.commit()
    return res


def collect_timeline(s: Session, *, timespan: str = "24m") -> RunResult:
    """National coverage history per theme (raw article counts per day)."""
    res = RunResult()
    with http_client(timeout=90) as client:
        for country in s.scalars(select(Country)):
            g = country.config.get("gdelt")
            if not g:
                continue
            for th in s.scalars(select(Theme).where(Theme.active.is_(True))):
                for series, extra in (("all", ""), ("sourcecountry", f"sourcecountry:{g['sourcecountry']}")):
                    try:
                        data = _json(client, {"query": theme_query(g["country_term"], th.en_terms, extra),
                                              "mode": "timelinevolraw", "timespan": timespan})
                    except Exception as e:  # noqa: BLE001
                        res.errors += 1
                        res.detail = f"{th.slug}/{series}: {e}"[:500]
                        continue
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
    return res
