"""Google News RSS search: the main keyless Arabic coverage source (GDELT cannot
search Arabic script). One query per theme × language × week window. Only title,
link, outlet and date are stored.

Google returns more for a recent week than for the same week asked about months later
(settings.DRIFT_PER_WEEK), so when a week was first retrieved matters. The six-hourly run asks for the
last 7 days; settle() asks again for the weeks that ended 2, 3 and 4 weeks ago (the Sunday job
jobs.gnews_settle), so every week from now on is retrieved at the same ages. Both are idempotent: an
article already stored (ingest.store_article, by URL key) is updated with the query that found it
again, never stored twice."""
import calendar
from datetime import date, datetime, timedelta

import feedparser
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import settings
from ..ingest import domain_of, load_rules, store_article
from ..models import Country, Theme
from .base import RunResult, http_client, polite_get

ENDPOINT = "https://news.google.com/rss/search"
MAX_TERMS = 7  # keep queries short; Google truncates long OR lists
# The editions a country's config does not name: English through the UK edition, Arabic through the
# legacy hl/gl/ceid keys (the Egypt-Arabic edition for Libya, which has no edition of its own).
DEFAULT_EN_EDITION = {"lang": "en", "hl": "en-GB", "gl": "GB", "ceid": "GB:en"}


def editions(g: dict, lang: str, iso2: str) -> list[dict]:
    """The Google News editions to ask for one language: config `gnews.editions` entries with that
    lang; without any, the legacy keys for Arabic (hl, gl, ceid) and the UK edition for English. Each
    is {lang, hl, gl, ceid}."""
    listed = [e for e in (g.get("editions") or []) if e.get("lang") == lang]
    if listed:
        return [{"lang": lang, "hl": e["hl"], "gl": e["gl"], "ceid": e["ceid"]} for e in listed]
    if lang == "ar":
        return [{"lang": "ar", "hl": g.get("hl", "ar"), "gl": g.get("gl", iso2), "ceid": g.get("ceid", f"{iso2}:ar")}]
    return [dict(DEFAULT_EN_EDITION)]


def build_query(country_term: str, terms: list[str], start, end) -> str:
    quoted = [f'"{t}"' if " " in t else t for t in terms[:MAX_TERMS]]
    fmt = lambda d: d.isoformat() if isinstance(d, date) and not isinstance(d, datetime) else d.date().isoformat()  # noqa: E731
    body = f'{country_term} ({" OR ".join(quoted)})' if quoted else country_term
    return f'{body} after:{fmt(start)} before:{fmt(end)}'


def _entries(client, q: str, hl: str, gl: str, ceid: str):
    r = polite_get(client, ENDPOINT, params={"q": q, "hl": hl, "gl": gl, "ceid": ceid}, min_interval=2.0)
    r.raise_for_status()
    return feedparser.parse(r.content).entries


CAP = 95  # Google News RSS returns at most ~100 items per query


def _fetch_window(client, cterm, chunk, start, end, hl, gl, ceid, stats):
    """Fetch one window; if the result is capped, split the window in half (down to 1 day)."""
    entries = _entries(client, build_query(cterm, chunk, start, end), hl, gl, ceid)
    if len(entries) >= CAP and (end - start).days > 1:
        mid = start + (end - start) / 2
        return (_fetch_window(client, cterm, chunk, start, mid, hl, gl, ceid, stats)
                + _fetch_window(client, cterm, chunk, mid, end, hl, gl, ceid, stats))
    if len(entries) >= CAP:
        stats["capped"] += 1
    return entries


def collect(s: Session, *, weeks: int = 1, end: date | None = None, start: date | None = None,
            step_days: int = 7, themes: list[str] | None = None, windows: list[tuple[date, date]] | None = None,
            stats: dict | None = None) -> RunResult:
    """Default: the last `weeks` weeks. Backfill: pass `start` (and optionally `end`), a window
    `step_days`, and `themes` (slugs or prefixes like 'gender') to limit the run. `windows` names the
    [start, end) windows outright (settle). A `stats` dict passed in receives the counts: queries made,
    results already stored (updated, not duplicated), one-day windows that hit the cap."""
    res = RunResult()
    stats = stats if stats is not None else {}
    stats.update({"capped": 0, "queries": 0, "seen": 0})
    end = end or (date.today() + timedelta(days=1))
    with http_client() as client:
        for country in s.scalars(select(Country)):
            g = country.config.get("gnews")
            if not g:
                continue
            rules = load_rules(s, country.id)
            cache: dict = {}
            theme_rows = [t for t in s.scalars(select(Theme).where(Theme.active.is_(True)))
                          if not themes or any(t.slug == x or t.slug.startswith(x) for x in themes)]
            # one variant per language and edition (config gnews.editions; one Arabic and one English
            # edition unless the owner adds more): (lang, country term, hl, gl, ceid, term field)
            cterms = {"ar": g["country_term_ar"], "en": country.config.get("gdelt", {}).get("country_term", country.name_en)}
            variants = [(lang, cterms[lang], e["hl"], e["gl"], e["ceid"], f"{lang}_terms")
                        for lang in ("ar", "en") for e in editions(g, lang, country.iso2)]
            if windows is None:
                windows = []
                if start:
                    cur = end
                    while cur > start:
                        windows.append((max(start, cur - timedelta(days=step_days)), cur))
                        cur -= timedelta(days=step_days)
                else:
                    windows = [(end - timedelta(days=7 * (w + 1)), end - timedelta(days=7 * w)) for w in range(weeks)]
            for w_start, w_end in windows:
                for th in theme_rows:
                    for lang, cterm, hl, gl, ceid, attr in variants:
                        terms = getattr(th, attr) or []
                        for i in range(0, len(terms), MAX_TERMS):
                            chunk = terms[i:i + MAX_TERMS]
                            try:
                                entries = _fetch_window(client, cterm, chunk, w_start, w_end, hl, gl, ceid, stats)
                                stats["queries"] += 1
                            except Exception as e:  # noqa: BLE001
                                res.errors += 1
                                res.detail = f"{th.slug}/{lang}: {e}"[:500]
                                continue
                            for e in entries:
                                src = e.get("source") or {}
                                src_url = src.get("href") or src.get("url")
                                if not e.get("published_parsed") or not e.get("link"):
                                    continue
                                pub = datetime.utcfromtimestamp(calendar.timegm(e.published_parsed))
                                title = e.get("title", "")
                                outlet_name = src.get("title")
                                if outlet_name and title.endswith(" - " + outlet_name):
                                    title = title[: -len(outlet_name) - 3]
                                _, created = store_article(
                                    s, country.id, rules, url=e.link, title=title, published_at=pub,
                                    source_key="gnews", lang=lang, outlet_name=outlet_name,
                                    outlet_domain=domain_of(src_url) if src_url else None,
                                    extra={"query_theme": th.slug, "query_themes": [th.slug]}, forced_theme_ids=(th.id,),
                                    outlet_cache=cache, query=f"gnews:{th.slug}")
                                res.rows += created
                                stats["seen"] += not created
                            s.commit()
                # the outlet searches (config gnews.outlet_queries): everything one outlet published in
                # the window, kept when a theme rule matches, as a feed's items are
                if not themes:
                    res.rows += _outlet_queries(s, client, country, g, rules, cache, w_start, w_end, stats, res)
    if stats["capped"]:
        res.detail = (res.detail + "; " if res.detail else "") + f"{stats['capped']} one-day windows still hit the 100-result cap"
    return res


def _outlet_queries(s: Session, client, country: Country, g: dict, rules, cache: dict, w_start, w_end, stats: dict,
                    res: RunResult) -> int:
    """One `site:` search per outlet query (config gnews.outlet_queries) and window: the Libyan majors
    with no feed. The first edition of the query's language is used; results are filed on the outlet
    named by `domain` (Google's own source link is kept as a check), stored as source gnews with no
    theme prior (require_theme: a rule must match, as for feed items), and recorded in extra.outlet_query."""
    rows = 0
    for q in g.get("outlet_queries") or []:
        lang = q.get("lang", "ar")
        ed = editions(g, lang, country.iso2)[0]
        try:
            entries = _fetch_window(client, q["query"], [], w_start, w_end, ed["hl"], ed["gl"], ed["ceid"], stats)
            stats["queries"] += 1
        except Exception as e:  # noqa: BLE001
            res.errors += 1
            res.detail = f"{q.get('label') or q['query']}: {e}"[:500]
            continue
        for e in entries:
            src = e.get("source") or {}
            src_url = src.get("href") or src.get("url")
            if not e.get("published_parsed") or not e.get("link"):
                continue
            title = e.get("title", "")
            outlet_name = src.get("title")
            if outlet_name and title.endswith(" - " + outlet_name):
                title = title[: -len(outlet_name) - 3]
            domain = q.get("domain") or (domain_of(src_url) if src_url else None)
            _, created = store_article(
                s, country.id, rules, url=e.link, title=title,
                published_at=datetime.utcfromtimestamp(calendar.timegm(e.published_parsed)), source_key="gnews",
                lang=lang, outlet_name=outlet_name, outlet_domain=domain, require_theme=True,
                extra={"outlet_query": q.get("label") or q["query"]}, outlet_cache=cache, query=f"gnews:site:{domain}")
            rows += created
            stats["seen"] += not created
        s.commit()
    return rows


def settle_windows(today: date, weeks_ago=None) -> list[tuple[date, date]]:
    """[start, end) of the calendar weeks (Monday to Sunday) that ended `weeks_ago` weeks before the week
    of `today`: on Sunday 1 November the week that ended 2 weeks ago is 12 to 18 October."""
    weeks_ago = weeks_ago or settings.SETTLE_WEEKS_AGO
    cur = today - timedelta(days=today.weekday())
    return [(cur - timedelta(weeks=k), cur - timedelta(weeks=k - 1)) for k in weeks_ago]


def settle(s: Session, *, weeks_ago=None, today: date | None = None, themes: list[str] | None = None) -> RunResult:
    """The Sunday re-query (jobs.gnews_settle, CLI gnews-settle): the weeks that ended 2, 3 and 4 weeks
    ago (settings.SETTLE_WEEKS_AGO) searched again, every theme in both languages, so every week going
    forward has been retrieved at the same ages. About 230 queries at the collector's polite spacing,
    around 8 minutes. Articles already stored are updated, never duplicated; the detail says how many."""
    today = today or date.today()
    windows = settle_windows(today, weeks_ago)
    stats: dict = {}
    res = collect(s, windows=windows, themes=themes, stats=stats)
    span = f"{windows[-1][0].isoformat()} to {(windows[0][1] - timedelta(days=1)).isoformat()}"
    note = (f"{len(windows)} weeks ({span}) searched again: {stats['queries']} queries, {res.rows} new articles, "
            f"{stats['seen']} already stored")
    res.detail = f"{note}; {res.detail}" if res.detail else note
    return res
