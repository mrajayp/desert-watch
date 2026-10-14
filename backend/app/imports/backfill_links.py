"""Backfill coverage from a list of article links (e.g. a media-monitoring review's citations).

Input JSON: [{"url", "date" (YYYY-MM-DD the link was cited), "outlet" (name or null),
              "ref": {...internal labels, never shown}}]
Only links from outlets we under-collect are imported: an outlet qualifies when the articles we
already hold from it since the earliest date are fewer than `max_ratio` x its links in the file.
That keeps us from double-counting outlets we already monitor (whose items may sit under Google
News redirect URLs that cannot be matched by URL).

Each page is fetched for its real title (the review's own wording is never used); our own rules
then tag topic and place. Idempotent and resumable: links already stored are skipped."""
import json
import logging
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..fetch_meta import FetchError, fetch_meta
from ..ingest import domain_of, load_rules, store_article, url_key
from ..models import Country, Item, Outlet

log = logging.getLogger("backfill")
SOURCE = "backfill"


def _published(meta_published: str | None, cited: date) -> datetime:
    """The page's own date when plausible (within 10 days before the citation), else the day before."""
    if meta_published:
        try:
            dt = datetime.fromisoformat(meta_published.replace("Z", "+00:00")).replace(tzinfo=None)
            if cited - timedelta(days=10) <= dt.date() <= cited:
                return dt
        except ValueError:
            pass
    return datetime.combine(cited - timedelta(days=1), datetime.min.time()).replace(hour=12)


# bot walls, error pages and homepages: not an article title
_JUNK = ("contact support", "just a moment", "access denied", "attention required", "forbidden", "not found",
         "page not found", "404", "403", "error", "security check", "are you a robot", "captcha", "403 forbidden",
         "service unavailable", "just a moment...", "الصفحة غير موجودة", "خطأ", "الرئيسية")


def _clean_title(title: str | None, site: str | None) -> str | None:
    if not title or title.strip().lower() in _JUNK or len(title.strip()) < 12:
        return None
    for sep in (" | ", " - ", " – ", " — "):
        if sep in title:
            head, tail = title.rsplit(sep, 1)
            if site and site.strip().lower() in tail.lower() or len(tail) < 30 and len(head) > 25:
                title = head
    return title.strip() or None


def select_links(s: Session, rows: list[dict], max_ratio: float) -> tuple[list[dict], dict]:
    """Rows from under-collected outlets, minus links already stored."""
    if not rows:
        return [], {}
    first = min(r["date"] for r in rows)
    by_dom = Counter(domain_of(r["url"]) for r in rows)
    ours = dict(s.execute(select(Outlet.domain, func.count(Item.id)).join(Item, Item.outlet_id == Outlet.id)
                          .where(Item.kind == "article", Item.published_at >= first, Item.source_key != SOURCE)
                          .group_by(Outlet.domain)).all())
    keep_dom = {d for d, n in by_dom.items() if ours.get(d, 0) < max_ratio * n}
    have = set()
    keys = [url_key(r["url"]) for r in rows]
    for i in range(0, len(keys), 500):
        chunk = keys[i:i + 500]
        have |= set(s.scalars(select(Item.dedupe_key).where(Item.dedupe_key.in_(chunk))))
    todo = [r for r, k in zip(rows, keys) if domain_of(r["url"]) in keep_dom and k not in have]
    stats = {"links": len(rows), "outlets_in_file": len(by_dom), "outlets_backfilled": len(keep_dom),
             "already_stored": sum(k in have for k in keys), "to_fetch": len(todo)}
    return todo, stats


def run(s: Session, path: Path, *, max_ratio: float = 0.2, limit: int | None = None, workers: int = 8,
        per_domain_interval: float = 1.0, fetch=fetch_meta) -> dict:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    c = s.scalar(select(Country).where(Country.iso2 == "LY"))
    todo, stats = select_links(s, rows, max_ratio)
    if limit:
        todo = todo[:limit]
    rules = load_rules(s, c.id)
    cache: dict = {}
    locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
    last: dict[str, float] = {}

    def get(r):
        d = domain_of(r["url"])
        with locks[d]:  # one request at a time per site, spaced out
            wait = per_domain_interval - (time.monotonic() - last.get(d, 0))
            if wait > 0:
                time.sleep(wait)
            try:
                return r, fetch(r["url"]), None
            except (FetchError, Exception) as e:  # noqa: BLE001
                return r, None, type(e).__name__ if not isinstance(e, FetchError) else str(e)
            finally:
                last[d] = time.monotonic()

    # interleave sites so the pool is not stuck behind one slow domain
    by_dom = defaultdict(list)
    for r in todo:
        by_dom[domain_of(r["url"])].append(r)
    order = [r for group in zip_longest(*by_dom.values()) for r in group if r]
    ok = failed = untitled = 0
    errors = Counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for n, (r, meta, err) in enumerate(pool.map(get, order), 1):
            if err or not meta:
                failed += 1
                errors[f"{domain_of(r['url'])}: {err}"[:80]] += 1
            else:
                cited = date.fromisoformat(r["date"])
                title = _clean_title(meta.get("title"), meta.get("site_name"))
                if not title:
                    untitled += 1
                else:
                    _, created = store_article(
                        s, c.id, rules, url=r["url"], title=title, snippet=(meta.get("description") or "")[:600] or None,
                        published_at=_published(meta.get("published"), cited), source_key=SOURCE,
                        lang=meta.get("lang") if meta.get("lang") in ("ar", "en") else None,
                        outlet_name=r.get("outlet"), extra={"ref": r.get("ref", {})}, outlet_cache=cache,
                        assume_relevant=True)
                    ok += created
            if n % 200 == 0:
                s.commit()
                log.warning("backfill %d/%d stored=%d failed=%d", n, len(order), ok, failed)
    s.commit()
    return {**stats, "stored": ok, "failed": failed, "no_title": untitled, "top_errors": errors.most_common(8)}


def zip_longest(*groups):
    from itertools import zip_longest as _z
    return _z(*groups)
