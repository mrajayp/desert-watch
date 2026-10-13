"""Wikimedia pageviews: national-level audience-interest lens. One need item per
article per day (value = views)."""
from datetime import date, datetime, timedelta
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Country, Item, ItemTheme, Theme
from .base import RunResult, http_client, polite_get

API = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{proj}.wikipedia/all-access/user/{title}/daily/{start}/{end}"


def collect(s: Session, *, days: int = 7) -> RunResult:
    res = RunResult()
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
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
                        r = polite_get(client, url, min_interval=1.0, retries=3)
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
                                continue
                            item = Item(country_id=country.id, kind="pageview", source_key="wikipedia",
                                        dedupe_key=key, title=title.replace("_", " "), lang=proj,
                                        published_at=day, value=row["views"])
                            s.add(item)
                            s.flush()
                            s.add(ItemTheme(item_id=item.id, theme_id=th.id, method="query"))
                            res.rows += 1
                        s.commit()
    return res
