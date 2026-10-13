"""Google Alerts RSS (Atom) feeds. Each feed keeps only ~20 recent results, so poll hourly.
Links are wrapped in a google.com/url redirect; the real URL is in the `url` parameter."""
import calendar
import re
from datetime import datetime
from html import unescape
from urllib.parse import parse_qs, urlsplit

import feedparser
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ingest import load_rules, store_article
from ..models import AlertFeed, ItemRegion, utcnow
from .base import AwaitingKey, RunResult, http_client, polite_get

_TAGS = re.compile(r"<[^>]+>")


def unwrap(link: str) -> str:
    p = urlsplit(link)
    if p.netloc.endswith("google.com") and p.path == "/url":
        q = parse_qs(p.query)
        if q.get("url"):
            return q["url"][0]
        if q.get("q"):
            return q["q"][0]
    return link


def clean(html: str | None) -> str:
    return re.sub(r"\s+", " ", unescape(_TAGS.sub(" ", html or ""))).strip()


def collect(s: Session) -> RunResult:
    res = RunResult()
    feeds = s.scalars(select(AlertFeed).where(AlertFeed.active.is_(True), AlertFeed.feed_url.is_not(None))).all()
    if not feeds:
        raise AwaitingKey("No alert feeds attached yet: create the alerts, then paste feed URLs in Admin → Google Alerts.")
    rules_by_country: dict = {}
    errors = []
    with http_client() as client:
        for f in feeds:
            rules = rules_by_country.setdefault(f.country_id, load_rules(s, f.country_id))
            try:
                r = polite_get(client, f.feed_url, min_interval=1.0)
                r.raise_for_status()
                parsed = feedparser.parse(r.content)
            except Exception as e:  # noqa: BLE001
                f.last_error = str(e)[:300]
                res.errors += 1
                errors.append(f"{f.key}: {e}")
                continue
            n = 0
            for e in parsed.entries:
                when = e.get("published_parsed") or e.get("updated_parsed")
                if not e.get("link") or not when:
                    continue
                item, created = store_article(
                    s, f.country_id, rules, url=unwrap(e.link), title=clean(e.get("title")),
                    snippet=clean(e.get("summary") or e.get("content", [{}])[0].get("value")),
                    published_at=datetime.utcfromtimestamp(calendar.timegm(when)), source_key="galerts",
                    lang=f.lang, extra={"alert": f.key},
                    forced_theme_ids=(f.theme_id,) if f.theme_id else ())
                if item is not None and f.region_id and not s.get(ItemRegion, (item.id, f.region_id)):
                    s.add(ItemRegion(item_id=item.id, region_id=f.region_id, method="query"))
                n += created
            f.last_ok_at, f.last_items, f.last_error = utcnow(), len(parsed.entries), None
            res.rows += n
            s.commit()
    res.detail = "; ".join(errors)[:1000]
    return res
