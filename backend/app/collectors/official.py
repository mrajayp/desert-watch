"""Official sources as a separate stream (not media coverage):
  * kind="statement": UN, embassy and government statements
  * kind="report":    humanitarian reports (ReliefWeb) - the humanitarian need lens
Feeds come from `official_feeds` in the country config; blocked sites (UNSMIL, US Embassy, Devex)
come in via Google News `site:` queries in `official_queries`. The Libya relevance guard applies
(regional UN feeds carry mostly other countries)."""
import calendar
import re
from datetime import date, datetime, timedelta
from html import unescape

import feedparser
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ingest import domain_of, load_rules, store_article
from ..models import Country
from .base import RunResult, http_client, polite_get
from .gnews import ENDPOINT, _fetch_window

_TAGS = re.compile(r"<[^>]+>")


def _clean(html):
    return re.sub(r"\s+", " ", unescape(_TAGS.sub(" ", html or ""))).strip()


def keep_official(cfg: dict, source: dict, title: str) -> bool:
    """Veto job ads / maps / sport; for statement searches require a statement word in the headline."""
    from ..textnorm import normalise, term_variants
    n = normalise(title)
    has = lambda words: any(f" {v} " in n for w in words for v in term_variants(w))  # noqa: E731
    if has(cfg.get("official_exclude_words", [])):
        return False
    if source.get("require_statement") and not has(cfg.get("official_statement_words", [])):
        return False
    return True


def collect(s: Session, *, weeks: int = 1, start: date | None = None, end: date | None = None,
            step_days: int = 14, feeds: bool = True) -> RunResult:
    res = RunResult()
    errors = []
    end = end or (date.today() + timedelta(days=1))
    with http_client() as client:
        for country in s.scalars(select(Country)):
            rules = load_rules(s, country.id)
            cache: dict = {}
            if feeds:
                for f in country.config.get("official_feeds", []) or []:
                    try:
                        r = polite_get(client, f["url"], min_interval=1.0)
                        r.raise_for_status()
                        parsed = feedparser.parse(r.content)
                    except Exception as e:  # noqa: BLE001
                        res.errors += 1
                        errors.append(f"{f['name']}: {e}")
                        continue
                    for e in parsed.entries:
                        when = e.get("published_parsed") or e.get("updated_parsed")
                        if not when or not e.get("link") or not keep_official(country.config, f, _clean(e.get("title"))):
                            continue
                        item, created = store_article(
                            s, country.id, rules, url=e.link, title=_clean(e.get("title")),
                            snippet=_clean(e.get("summary"))[:600],
                            published_at=datetime.utcfromtimestamp(calendar.timegm(when)), source_key="official",
                            outlet_name=f["name"], outlet_domain=f["domain"], kind=f["kind"],
                            extra={"official": f["name"]}, outlet_cache=cache,
                            assume_relevant=bool(f.get("libya_specific")))
                        res.rows += created
                    s.commit()
            # Google News site:/phrase queries for sources without usable feeds
            g = country.config.get("gnews", {})
            windows = []
            if start:
                cur = end
                while cur > start:
                    windows.append((max(start, cur - timedelta(days=step_days)), cur))
                    cur -= timedelta(days=step_days)
            else:
                windows = [(end - timedelta(days=7 * (w + 1)), end - timedelta(days=7 * w)) for w in range(weeks)]
            stats = {"capped": 0, "queries": 0}
            for q in country.config.get("official_queries", []) or []:
                ar = q["lang"] == "ar"
                hl, gl, ceid = (g.get("hl", "ar"), g.get("gl", country.iso2), g.get("ceid", f"{country.iso2}:ar")) if ar \
                    else ("en-GB", "GB", "GB:en")
                for w_start, w_end in windows:
                    try:
                        # _fetch_window builds "<term> (<terms>) after: before:"; pass the whole query as the term
                        entries = _fetch_window(client, q["query"], [], w_start, w_end, hl, gl, ceid, stats)
                    except Exception as e:  # noqa: BLE001
                        res.errors += 1
                        errors.append(f"{q['label']}: {e}")
                        continue
                    for e in entries:
                        src = e.get("source") or {}
                        src_url = src.get("href") or src.get("url")
                        if not e.get("published_parsed") or not e.get("link"):
                            continue
                        title = e.get("title", "")
                        name = src.get("title")
                        if name and title.endswith(" - " + name):
                            title = title[: -len(name) - 3]
                        if not keep_official(country.config, q, title):
                            continue
                        _, created = store_article(
                            s, country.id, rules, url=e.link, title=title,
                            published_at=datetime.utcfromtimestamp(calendar.timegm(e.published_parsed)),
                            source_key="official", lang=q["lang"], outlet_name=name,
                            outlet_domain=domain_of(src_url) if src_url else None, kind=q["kind"],
                            extra={"official": q["label"]}, outlet_cache=cache,
                            assume_relevant=bool(q.get("libya_specific")))
                        res.rows += created
                    s.commit()
    res.detail = "; ".join(errors)[:1000]
    return res
