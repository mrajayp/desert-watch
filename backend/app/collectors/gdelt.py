"""GDELT DOC 2.0. Searches English machine translations only, so queries use English
terms; `sourcelang:` narrows by original language. artlist returns <=250 rows for
the last 3 months, so it is queried in 1-day windows; timelinevolraw gives long
history counts for the national trend. Limit: one request every 5 seconds (INTERVAL keeps 6).

A theme has more terms than fit one query, so every theme is asked in chunks of MAX_TERMS terms
(theme_queries), one request per chunk, paced like any other request. The article run merges the
chunks' answers so an article counts once; the history run adds the chunks' daily counts (an article
that matches words from two chunks is counted twice there, so the line is a close upper bound). The
run detail says how many queries a run made and how many GDELT refused."""
from datetime import date, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ingest import load_rules, store_article
from ..models import Country, CoverageSeries, Theme
from .base import STOP_AFTER, RunResult, http_client, polite_get, refused

API = "https://api.gdeltproject.org/api/v2/doc/doc"
INTERVAL = 6.0
MAX_TERMS = 8   # terms per query: GDELT's OR lists stay short; a theme with more terms is asked in several queries
# GDELT answers bursts with 429 or "Please limit requests". The six-hourly article run backs off 12 and 24 s
# (it shares the job lock with the hourly collectors). The long-run line, run by hand, waits 12, 24, 48, 96 s.
RETRIES, TIMELINE_RETRIES = 2, 4
LANG = {"Arabic": "ar", "English": "en", "French": "fr", "Italian": "it"}


def theme_query(country_term: str, terms: list[str], extra: str = "") -> str:
    # phrases and hyphenated words go in quotes: GDELT rejects a bare "same-sex" (illegal character)
    quoted = [f'"{t}"' if " " in t or "-" in t else t for t in terms]
    return f'{country_term} ({" OR ".join(quoted)}) {extra}'.strip()


def theme_queries(country_term: str, terms: list[str] | None, extra: str = "") -> list[str]:
    """One query per chunk of MAX_TERMS terms, so every term of the theme is asked for (in list order,
    repeats dropped). A theme without English terms gets no query."""
    todo = list(dict.fromkeys(t.strip() for t in terms or [] if t and t.strip()))
    return [theme_query(country_term, todo[i:i + MAX_TERMS], extra) for i in range(0, len(todo), MAX_TERMS)]


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


class _Run:
    """One run's bookkeeping: queries made, answers GDELT refused, refusals in a row (the run stops at
    STOP_AFTER) and the last error, written as the run's detail line so the health strip shows them."""

    def __init__(self):
        self.res = RunResult()
        self.asked = self.refused_n = self.refusals = self.themes = 0
        self.last_error = ""

    def stop(self) -> bool:
        return self.refusals >= STOP_AFTER

    def ask(self, client, what: str, params: dict, retries: int):
        """One request. None when it failed: the error is counted and kept for the detail line, and a
        refusal counts towards the stop; any other answer (a bad query) resets that count."""
        self.asked += 1
        try:
            data = _json(client, params, retries=retries)
        except Exception as e:  # noqa: BLE001
            if isinstance(e, Refused):
                self.refusals += 1
                self.refused_n += 1
            else:
                self.refusals = 0
            self.res.errors += 1
            self.last_error = f"{what}: {e}"[:300]
            return None
        self.refusals = 0
        return data

    def finish(self, what: str) -> RunResult:
        line = f"{self.asked} queries for {self.themes} themes {what}, {self.refused_n} refused by GDELT"
        if self.last_error:
            line += f"; {self.last_error}"
        if self.stop():
            line = f"stopped after {STOP_AFTER} refusals in a row. {line}"
        self.res.detail = line[:500]
        return self.res


def collect(s: Session, *, days: int = 1) -> RunResult:
    """Article lists, one day at a time, every chunk of a theme's terms asked and the answers merged (an
    article returned by two chunks is stored once, under the theme). Stops after STOP_AFTER refusals in a row."""
    run = _Run()
    with http_client(timeout=60) as client:
        for country in s.scalars(select(Country)).all():
            g = country.config.get("gdelt")
            if not g:
                continue
            rules = load_rules(s, country.id)
            cache: dict = {}
            for th in s.scalars(select(Theme).where(Theme.active.is_(True))).all():
                queries = theme_queries(g["country_term"], th.en_terms)
                if not queries or run.stop():
                    continue
                run.themes += 1
                for d in range(days):
                    end = datetime.utcnow().replace(minute=0, second=0, microsecond=0) - timedelta(days=d)
                    start = end - timedelta(days=1)
                    seen: set[str] = set()
                    articles = []
                    for q in queries:
                        if run.stop():
                            break
                        data = run.ask(client, th.slug, {"query": q, "mode": "artlist", "maxrecords": 250, "sort": "datedesc",
                                                         "startdatetime": start.strftime("%Y%m%d%H%M%S"),
                                                         "enddatetime": end.strftime("%Y%m%d%H%M%S")}, RETRIES)
                        for a in (data or {}).get("articles", []):
                            if a.get("url") and a["url"] not in seen:   # the same article from two chunks: once
                                seen.add(a["url"])
                                articles.append(a)
                    for a in articles:
                        pub = datetime.strptime(a["seendate"], "%Y%m%dT%H%M%SZ")
                        _, created = store_article(
                            s, country.id, rules, url=a["url"], title=a.get("title"), published_at=pub,
                            source_key="gdelt", lang=LANG.get(a.get("language"), None),
                            outlet_domain=a.get("domain"), extra={"sourcecountry": a.get("sourcecountry")},
                            forced_theme_ids=(th.id,), outlet_cache=cache, query=f"gdelt:{th.slug}")
                        run.res.rows += created
                    s.commit()
    return run.finish(f"over {days} day{'s' if days != 1 else ''}")


def collect_timeline(s: Session, *, timespan: str = "24m", themes: list[str] | None = None) -> RunResult:
    """National coverage history per theme (raw article counts per day): each chunk of the theme's terms
    is one request (retried with backoff) and the chunks' counts are added per day. A theme's line is
    written only when every chunk answered, so a stored line always counts the whole term list. Every
    theme's 'all' series comes first, so a run cut short by rate limits still leaves each theme a line.
    `themes` (slugs) limits the run. Stops after STOP_AFTER refusals in a row."""
    run = _Run()
    with http_client(timeout=90) as client:
        for country in s.scalars(select(Country)).all():
            g = country.config.get("gdelt")
            if not g:
                continue
            q = select(Theme).where(Theme.active.is_(True)).order_by(Theme.id)
            if themes:
                q = q.where(Theme.slug.in_(themes))
            todo = s.scalars(q).all()
            run.themes = len(todo)
            for series, extra in (("all", ""), ("sourcecountry", f"sourcecountry:{g['sourcecountry']}")):
                for th in todo:
                    if run.stop():
                        break
                    totals: dict[date, float] = {}
                    complete = True
                    for query in theme_queries(g["country_term"], th.en_terms, extra):
                        if run.stop():
                            complete = False
                            break
                        data = run.ask(client, f"{th.slug}/{series}",
                                       {"query": query, "mode": "timelinevolraw", "timespan": timespan}, TIMELINE_RETRIES)
                        if data is None:
                            complete = False
                            break
                        for tl in data.get("timeline", [])[:1]:
                            for pt in tl.get("data", []):
                                day = datetime.strptime(pt["date"][:8], "%Y%m%d").date()
                                totals[day] = totals.get(day, 0) + pt["value"]
                    if not complete:
                        continue
                    for day, value in totals.items():
                        row = s.scalar(select(CoverageSeries).where(
                            CoverageSeries.theme_id == th.id, CoverageSeries.day == day,
                            CoverageSeries.series == series))
                        if row:
                            row.value = value
                        else:
                            s.add(CoverageSeries(country_id=country.id, theme_id=th.id, series=series,
                                                 day=day, value=value))
                            run.res.rows += 1
                    s.commit()
    return run.finish("x 2 series")
