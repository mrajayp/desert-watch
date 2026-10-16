"""Wikimedia pageviews: national-level audience-interest lens. One need item per
article per day (value = views). An article listed under several themes is one item with
one ItemTheme per theme, so it counts for each theme and once in any all-theme total.
Every run re-fetches at least the last REFETCH_DAYS days (the collector upserts), so days
lost to rate limiting or late Wikimedia processing fill in on the next run."""
from datetime import date, datetime, timedelta
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Country, Item, ItemTheme, Theme
from .base import RunResult, http_client, polite_get

API = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{proj}.wikipedia/all-access/user/{title}/daily/{start}/{end}"
REFETCH_DAYS = 7
# Wikimedia answers bursts with HTTP 429: back off 4, 8, 16, 32 s (or as long as Retry-After asks)
RETRIES, BACKOFF = 4, 2.0


def _link(s: Session, item_id: int, theme_id: int) -> bool:
    if s.get(ItemTheme, (item_id, theme_id)):
        return False
    s.add(ItemTheme(item_id=item_id, theme_id=theme_id, method="query"))
    return True


def collect(s: Session, *, days: int = 7) -> RunResult:
    res = RunResult()
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=max(days, REFETCH_DAYS) - 1)
    themes = {t.slug: t for t in s.scalars(select(Theme))}
    with http_client() as client:
        for country in s.scalars(select(Country)):
            for slug, langs in (country.config.get("wikipedia") or {}).items():
                th = themes.get(slug)
                if not th:
                    continue
                for proj, titles in langs.items():
                    for title in titles or []:
                        url = API.format(proj=proj, title=quote(title, safe=""), start=start.strftime("%Y%m%d"),
                                         end=end.strftime("%Y%m%d"))
                        r = polite_get(client, url, min_interval=1.0, retries=RETRIES, backoff=BACKOFF)
                        if r.status_code != 200:
                            res.errors += 1
                            res.detail = f"{proj}:{title} -> HTTP {r.status_code}"
                            continue
                        for row in r.json().get("items", []):
                            day = datetime.strptime(row["timestamp"][:8], "%Y%m%d")
                            key = f"wiki:{proj}:{title}:{day.date().isoformat()}"
                            item = s.scalar(select(Item).where(Item.dedupe_key == key))
                            if item:
                                item.value = row["views"]
                            else:
                                item = Item(country_id=country.id, kind="pageview", source_key="wikipedia",
                                            dedupe_key=key, title=title.replace("_", " "), lang=proj,
                                            published_at=day, value=row["views"])
                                s.add(item)
                                s.flush()
                                res.rows += 1
                            _link(s, item.id, th.id)  # the same title can be listed under another theme
                        s.commit()
    return res


def repair_themes(s: Session) -> int:
    """Add the ItemTheme rows that titles listed under several themes never got: the collector used to
    file each day only under the first theme that fetched it. Idempotent. Returns links added."""
    themes = {t.slug: t for t in s.scalars(select(Theme))}
    added = 0
    for country in s.scalars(select(Country)).all():
        for slug, langs in (country.config.get("wikipedia") or {}).items():
            th = themes.get(slug)
            if not th:
                continue
            for proj, titles in langs.items():
                for title in titles or []:
                    prefix = f"wiki:{proj}:{title}:"   # a key range, so the unique index on dedupe_key serves it
                    days = select(Item.id).where(
                        Item.country_id == country.id, Item.kind == "pageview",
                        Item.dedupe_key >= prefix, Item.dedupe_key < prefix + "\U0010ffff")
                    have = set(s.scalars(select(ItemTheme.item_id).where(ItemTheme.theme_id == th.id,
                                                                         ItemTheme.item_id.in_(days))))
                    for iid in s.scalars(days).all():
                        if iid not in have:
                            s.add(ItemTheme(item_id=iid, theme_id=th.id, method="query"))
                            added += 1
                    s.flush()
    s.commit()
    return added
