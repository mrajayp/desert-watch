"""Load Google Trends rows (JSONL from scripts/fetch_gtrends.py, or rows from a keyed provider) as
need items for the search lens: one Item per theme per Monday week.

    kind='search', source_key='gtrends', dedupe_key 'gt:<slug>:v<version>:<monday>'
    value = 100 * list / anchor_ref, in anchor units (see app/gtrends.py)

Only rows whose list and anchor match the country config count, so files from trial runs load
safely. Weeks before the config's `since` (Google's 1 Jan 2022 data change) are skipped.
Re-imports overwrite, because Google revises the latest weeks. When the input holds the same week
twice, a week with data beats one without, then the newer fetch day, then daily over weekly data.
A week without data keeps has_data false (so windows holding it are not scored) and gets the median
of the data weeks around it as its value, so it does not read as zero need in later baselines.
Items of an older list version, or of a theme that lost its list, stop counting. A user's relevance
decision on an item is kept. Rows are streamed: memory holds the best row per theme-week and each
request's anchor by week, never the whole file. Idempotent."""
import json
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import gtrends
from ..models import Country, Item, ItemTheme, SourceRun, Theme, utcnow

FILL_WEEKS = 4       # a week without data takes the median of the data weeks up to 4 weeks either side
FILL_WEEKS_MAX = 13  # ... or up to 13 when there are none that close


def iter_rows(path: Path) -> Iterator[dict]:
    """Rows from a JSONL file, one line at a time (a JSON array file is read whole)."""
    with Path(path).open(encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("["):
                f.seek(0)
                yield from json.load(f)
                return
            yield json.loads(line)


def load_rows(path: Path) -> list[dict]:
    return list(iter_rows(path))


def _rank(r: dict):
    return bool(r["has_data"]), r["fetched_at"][:10], r.get("resolution") == "day", r["fetched_at"]


def _explore_url(geo: str, terms: list[str], anchor: str, monday: date) -> str:
    span = f"{(monday - timedelta(weeks=12)).isoformat()} {(monday + timedelta(days=6)).isoformat()}"
    return (f"https://trends.google.com/trends/explore?geo={geo}&date={quote(span)}"
            f"&q={quote(gtrends.slot(terms))},{quote(anchor)}")


def _fill(data: dict[date, float], wk: date) -> float:
    """Median of the data weeks near a week without data (0 when there are none)."""
    for span in (FILL_WEEKS, FILL_WEEKS_MAX):
        near = [v for d, v in data.items() if abs((d - wk).days) <= 7 * span]
        if near:
            return round(float(statistics.median(near)), 3)
    return 0.0


def import_rows(s: Session, rows: Iterable[dict], *, country_iso2: str = "LY", provider: str | None = None) -> dict:
    country = s.scalar(select(Country).where(Country.iso2 == country_iso2))
    g = gtrends.config(country.config or {}) if country else None
    if not g:
        raise ValueError(f"No gtrends config for {country_iso2}")
    version, anchor, geo = int(g.get("version", 1)), g["anchor"].strip(), g.get("geo", country_iso2)
    since = date.fromisoformat(str(g.get("since") or gtrends.DATA_BREAK))
    themes = {t.slug: t for t in s.scalars(select(Theme))}
    stats = Counter()
    anchors: dict[str, dict[str, int]] = defaultdict(dict)  # request -> week -> anchor_raw
    best: dict[tuple[str, str], dict] = {}
    for r in rows:
        stats["rows"] += 1
        anchors[r["request_id"]][r["week"]] = r["anchor_raw"]
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
    refs = {rid: gtrends.anchor_refs_by_week(anchors[rid]) for rid in {r["request_id"] for r in best.values()}}
    del anchors

    # values in anchor units; a week without data takes the median of the data weeks around it
    values: dict[tuple[str, str], tuple[float, bool, float]] = {}
    data: dict[str, dict[date, float]] = defaultdict(dict)
    for (slug, wk), r in best.items():
        ref = refs[r["request_id"]].get(wk, 0.0)
        has = bool(r["has_data"]) and ref > 0
        values[(slug, wk)] = (round(100 * r["value_raw"] / ref, 3) if has else None, has, ref)
        if has:
            data[slug][date.fromisoformat(wk)] = values[(slug, wk)][0]

    existing = {it.dedupe_key: it for it in s.scalars(
        select(Item).where(Item.country_id == country.id, Item.source_key == gtrends.SOURCE))}
    for (slug, wk), r in sorted(best.items()):
        theme, terms, monday = themes[slug], g["baskets"][slug], date.fromisoformat(wk)
        value, has, ref = values[(slug, wk)]
        if not has:
            value = _fill(data[slug], monday)
            stats["weeks_filled"] += 1
        extra = {"terms": list(terms), "anchor": anchor, "provisional": bool(r.get("provisional")), "has_data": has,
                 "fetched_at": r["fetched_at"], "value_raw": r["value_raw"], "anchor_raw": r["anchor_raw"],
                 "anchor_ref": ref, "resolution": r.get("resolution"), "nodata_days": r.get("nodata_days"),
                 "request_id": r["request_id"], "provider": provider or r.get("provider"), "version": version}
        if not has:
            extra["filled"] = True
        key = f"gt:{slug}:v{version}:{wk}"
        title = (f"Google searches in Libya: {gtrends.slot(terms)}" + (" (provisional)" if extra["provisional"] else "")
                 + ("" if has else " (Google gave no data, so we use the median of the weeks around it)"))
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
        old = it.extra or {}
        if old.get("user_relevance") is not None:  # never overwrite a user's decision
            extra["user_relevance"] = old["user_relevance"]
        if old.get("retired") and old.get("user_relevance") is not False:
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
    latest = max((wk for (_, wk), v in values.items() if v[1]), default=None)
    s.add(SourceRun(source_key=gtrends.SOURCE, started_at=utcnow(), finished_at=utcnow(), status="ok", ok=True,
                    rows=stats["created"] + stats["updated"],
                    error=f"import: {stats['created']} new, {stats['updated']} updated, {stats['retired']} retired; "
                          f"latest week with data {latest or 'none'}"))
    s.commit()
    return dict(stats)


def newest(path: Path) -> Path:
    """A directory means its newest gtrends-*.jsonl: every fetch holds the whole series."""
    path = Path(path)
    if not path.is_dir():
        return path
    files = sorted(path.glob("gtrends-*.jsonl"))  # names carry the UTC time, so they sort by age
    if not files:
        raise ValueError(f"No gtrends-*.jsonl in {path}")
    return files[-1]


def run(s: Session, path: Path, *, country_iso2: str = "LY") -> dict:
    path = newest(path)
    return {"file": path.name, **import_rows(s, iter_rows(path), country_iso2=country_iso2)}
