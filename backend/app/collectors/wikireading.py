"""What people in the country read on Wikipedia, from Wikimedia's privacy-protected daily dataset
(analytics.wikimedia.org/published/datasets/country_project_page, one TSV a day, about 20 MB, no
header: country, ISO2, project, page_id, page_title, item_id, views). A page appears for a country
only with more than about 90 views that day, with noise of about 35 views added (Libya is in
Wikimedia's lowest-risk group). Files appear the next day around 02:30-03:00 UTC.

Two uses, both shown next to coverage and never scored:
- wiki_reading rows: the pages that name the country or one of its places, or that a theme or an
  indicator lists. Everything else (main pages, football, adult titles) is dropped while streaming.
- indicators: config `wiki_indicators` names pages by project and page_id (stable when a page is
  renamed). Their daily views become Indicator rows, value None when the page was below the threshold.

The file is streamed and only the country's rows are kept, so memory stays flat."""
from datetime import date, timedelta

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import settings
from ..ingest import load_rules
from ..models import Country, Indicator, WikiReading
from ..textnorm import normalise, term_variants
from .base import RunResult

URL = "https://analytics.wikimedia.org/published/datasets/country_project_page/{day}.tsv"
LOOKBACK_DAYS = 4          # each run fills any of the last few days not stored yet
FIRST_DAY = date(2023, 2, 6)
# never kept, even when the title names a Libyan place
BLOCKED = {"سكس", "نيك", "اباحي", "اباحيه", "xxx", "porn", "porno", "sex", "xnxx"}


def parse_line(line: str):
    """(iso2, project, page_id, title, qid, views) or None."""
    p = line.rstrip("\r\n").split("\t")
    if len(p) < 7:
        return None
    try:
        return p[1], p[2], int(p[3]), p[4], (p[5] or None), int(float(p[6]))
    except ValueError:
        return None


def stream_country(client: httpx.Client, day: date, iso2: str) -> list[tuple] | None:
    """The country's rows for a day, or None when Wikimedia has not published that day yet."""
    rows, buf = [], b""
    with client.stream("GET", URL.format(day=day.isoformat())) as r:
        if r.status_code == 404:
            return None
        r.raise_for_status()
        tag = f"\t{iso2}\t".encode()
        for chunk in r.iter_bytes():
            buf += chunk
            *lines, buf = buf.split(b"\n")
            for raw in lines:
                if tag in raw:
                    row = parse_line(raw.decode("utf-8", errors="replace"))
                    if row and row[0] == iso2:
                        rows.append(row)
        if buf and tag in buf:
            row = parse_line(buf.decode("utf-8", errors="replace"))
            if row and row[0] == iso2:
                rows.append(row)
    return rows


def indicator_pages(config: dict) -> dict[tuple[str, int], str]:
    """(project, page_id) -> indicator key, from country config `wiki_indicators`."""
    out = {}
    for key, ind in (config.get("wiki_indicators") or {}).items():
        for proj, ids in (ind.get("pages") or {}).items():
            for pid in ids:
                out[(proj, int(pid))] = key
    return out


def theme_titles(config: dict) -> set[tuple[str, str]]:
    """(project, title with underscores) for the articles the themes' audience lens follows."""
    out = set()
    for langs in (config.get("wikipedia") or {}).values():
        for lang, titles in (langs or {}).items():
            for t in titles or []:
                out.add((f"{lang}.wikipedia", t.replace(" ", "_")))
    return out


def extra_terms(config: dict) -> list[str]:
    """Normalised variants of config `wiki_reading_terms` (public figures and institutions)."""
    return sorted({v for t in (config.get("wiki_reading_terms") or []) for v in term_variants(t)})


def keep_row(rules, title: str, project: str, page_id: int, ind: dict, followed: set, terms=()) -> bool:
    text = title.replace("_", " ")
    n = f" {normalise(text)} "
    if set(n.split()) & BLOCKED:
        return False
    return ((project, page_id) in ind or (project, title) in followed or rules.mentions_country(text)
            or any(f" {t} " in n for t in terms))


def store_day(s: Session, c: Country, day: date, rows: list[tuple], rules=None) -> dict:
    """Replace the day's reading rows and indicator values. Idempotent."""
    rules = rules or load_rules(s, c.id)
    ind = indicator_pages(c.config or {})
    followed = theme_titles(c.config or {})
    terms = extra_terms(c.config or {})
    s.execute(delete(WikiReading).where(WikiReading.country_id == c.id, WikiReading.day == day))
    kept, views_by_key = 0, {}
    rows = [r for r in rows if r and r[0] == c.iso2]
    for _, project, page_id, title, qid, views in rows:
        if (project, page_id) in ind:
            k = ind[(project, page_id)]
            views_by_key[k] = views_by_key.get(k, 0) + views
        if keep_row(rules, title, project, page_id, ind, followed, terms):
            s.add(WikiReading(country_id=c.id, day=day, project=project, page_id=page_id, page_title=title[:300],
                              qid=qid, views=views))
            kept += 1
    for key in set(ind.values()):
        row = s.scalar(select(Indicator).where(Indicator.country_id == c.id, Indicator.key == key, Indicator.day == day))
        if row is None:
            row = Indicator(country_id=c.id, key=key, day=day, source="wikimedia_dp")
            s.add(row)
        row.value = views_by_key.get(key)       # None: below Wikimedia's threshold that day
        row.extra = {"rows": len(rows)}
    s.commit()
    return {"day": day.isoformat(), "country_rows": len(rows), "kept": kept, "indicators": views_by_key}


def stored_days(s: Session, country_id: int, start: date, end: date) -> set[date]:
    """Days already done: an indicator row exists for them (written even when the page was absent)."""
    return set(s.scalars(select(Indicator.day).where(Indicator.country_id == country_id, Indicator.source == "wikimedia_dp",
                                                     Indicator.day >= start, Indicator.day <= end)).all())


def run(s: Session, start: date, end: date, *, client: httpx.Client | None = None, out=None) -> dict:
    """Fetch and store every day in [start, end] not stored yet, oldest first. Stops at the first day
    Wikimedia has not published (later days cannot be there either)."""
    done = {"stored": 0, "skipped": 0, "not_yet": None, "days": []}
    countries = [c for c in s.scalars(select(Country)) if indicator_pages(c.config or {}) or (c.config or {}).get("wiki_reading")]
    own = client is None
    client = client or httpx.Client(headers={"User-Agent": settings.USER_AGENT}, timeout=180, follow_redirects=True)
    try:
        for c in countries:
            rules = load_rules(s, c.id)
            have = stored_days(s, c.id, start, end)
            day = start
            while day <= end:
                if day in have:
                    done["skipped"] += 1
                else:
                    rows = stream_country(client, day, c.iso2)
                    if rows is None:
                        done["not_yet"] = day.isoformat()
                        break
                    res = store_day(s, c, day, rows, rules)
                    done["stored"] += 1
                    done["days"].append(res["day"])
                    if out:
                        out(res)
                day += timedelta(days=1)
    finally:
        if own:
            client.close()
    return done


def collect(s: Session) -> RunResult:
    today = date.today()
    res = run(s, today - timedelta(days=LOOKBACK_DAYS), today - timedelta(days=1))
    detail = f"{res['stored']} day(s) stored" + (f", {res['not_yet']} not published yet" if res["not_yet"] else "")
    return RunResult(rows=res["stored"], detail=detail)
