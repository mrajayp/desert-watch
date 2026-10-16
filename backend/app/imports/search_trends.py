"""Load Google Trends rows (JSONL from scripts/fetch_gtrends.py, or rows from a keyed provider) as
need items for the search lens: one Item per theme per Monday week.

    kind='search', source_key='gtrends', dedupe_key 'gt:<slug>:v<version>:<monday>'
    value = 100 * list / anchor_ref, in anchor units (see app/gtrends.py)

Only rows whose list and anchor match the country config count, so files from trial runs load
safely. Weeks before the config's `since` (Google's 1 Jan 2022 data change) are skipped.
Re-imports overwrite, because Google revises the latest weeks. When the input holds the same week
twice, a week with data beats one without, then the newer fetch day, then daily over weekly data.
Items of an older list version, or of a theme that lost its list, stop counting. Idempotent."""
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import gtrends
from ..models import Country, Item, ItemTheme, SourceRun, Theme, utcnow


def load_rows(path: Path) -> list[dict]:
    text = Path(path).read_text(encoding="utf-8").strip()
    if text.startswith("["):
        return json.loads(text)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _rank(r: dict):
    return bool(r["has_data"]), r["fetched_at"][:10], r.get("resolution") == "day", r["fetched_at"]


def _explore_url(geo: str, terms: list[str], anchor: str, monday: date) -> str:
    span = f"{(monday - timedelta(weeks=12)).isoformat()} {(monday + timedelta(days=6)).isoformat()}"
    return (f"https://trends.google.com/trends/explore?geo={geo}&date={quote(span)}"
            f"&q={quote(gtrends.slot(terms))},{quote(anchor)}")


def import_rows(s: Session, rows: list[dict], *, country_iso2: str = "LY", provider: str | None = None) -> dict:
    country = s.scalar(select(Country).where(Country.iso2 == country_iso2))
    g = gtrends.config(country.config or {}) if country else None
    if not g:
        raise ValueError(f"No gtrends config for {country_iso2}")
    version, anchor, geo = int(g.get("version", 1)), g["anchor"].strip(), g.get("geo", country_iso2)
    since = date.fromisoformat(str(g.get("since") or gtrends.DATA_BREAK))
    themes = {t.slug: t for t in s.scalars(select(Theme))}
    stats = Counter(rows=len(rows))
    by_request = defaultdict(list)
    for r in rows:
        by_request[r["request_id"]].append(r)
    refs = {rid: gtrends.anchor_refs(rs) for rid, rs in by_request.items()}

    best: dict[tuple[str, str], dict] = {}
    for r in rows:
        terms = g["baskets"].get(r["theme_slug"])
        if not terms or not gtrends.same_terms(terms, r["basket"]) or r["anchor"].strip() != anchor:
            stats["other_list"] += 1
            continue
        if r["theme_slug"] not in themes:
            stats["unknown_theme"] += 1
            continue
        if date.fromisoformat(r["week"]) < since:
            stats["before_since"] += 1
            continue
        k = (r["theme_slug"], r["week"])
        if k not in best or _rank(r) > _rank(best[k]):
            best[k] = r

    existing = {it.dedupe_key: it for it in s.scalars(
        select(Item).where(Item.country_id == country.id, Item.source_key == gtrends.SOURCE))}
    for (slug, wk), r in sorted(best.items()):
        theme, terms, monday = themes[slug], g["baskets"][slug], date.fromisoformat(wk)
        ref = refs[r["request_id"]].get(wk, 0.0)
        has = bool(r["has_data"]) and ref > 0
        value = round(100 * r["value_raw"] / ref, 3) if ref > 0 else 0.0
        extra = {"terms": list(terms), "anchor": anchor, "provisional": bool(r.get("provisional")), "has_data": has,
                 "fetched_at": r["fetched_at"], "value_raw": r["value_raw"], "anchor_raw": r["anchor_raw"],
                 "anchor_ref": ref, "resolution": r.get("resolution"), "nodata_days": r.get("nodata_days"),
                 "request_id": r["request_id"], "provider": provider or r.get("provider"), "version": version}
        key = f"gt:{slug}:v{version}:{wk}"
        title = f"Google searches in Libya: {gtrends.slot(terms)}" + (" (provisional)" if extra["provisional"] else "")
        it = existing.get(key)
        if it is None:
            it = Item(country_id=country.id, kind="search", source_key=gtrends.SOURCE, dedupe_key=key, title=title,
                      url=_explore_url(geo, terms, anchor, monday), lang="ar",
                      published_at=datetime.combine(monday, datetime.min.time()), value=value, extra=extra)
            s.add(it)
            s.flush()
            s.add(ItemTheme(item_id=it.id, theme_id=theme.id, method="query", theme_version=theme.version,
                            evidence={"field": "query", "terms": list(terms), "query": "gtrends"}))
            existing[key] = it
            stats["created"] += 1
            continue
        if (it.extra or {}).get("retired"):
            it.relevant = True
        if it.value == value and it.extra == extra and it.title == title:
            stats["unchanged"] += 1
            continue
        it.value, it.extra, it.title = value, extra, title
        stats["updated"] += 1

    current = tuple(f"gt:{slug}:v{version}:" for slug in g["baskets"])
    for key, it in existing.items():
        if not key.startswith(current) and it.relevant:
            it.relevant = False
            it.extra = {**(it.extra or {}), "retired": True}
            stats["retired"] += 1
    stats["weeks_without_data"] = sum(1 for r in best.values() if not r["has_data"])
    s.add(SourceRun(source_key=gtrends.SOURCE, started_at=utcnow(), finished_at=utcnow(), status="ok", ok=True,
                    rows=stats["created"] + stats["updated"],
                    error=f"import: {stats['created']} new, {stats['updated']} updated, {stats['retired']} retired"))
    s.commit()
    return dict(stats)


def run(s: Session, path: Path, *, country_iso2: str = "LY") -> dict:
    return import_rows(s, load_rows(path), country_iso2=country_iso2)
