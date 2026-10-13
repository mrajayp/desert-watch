"""Data-quality review of imported articles. `python -m app.cli review [OUT_DIR]` writes:

  review_summary.json   counts by source / month / language, duplicates, date sanity, guard
                        filtering, region tagging, rule confirmation per theme
  review_sample.csv     a stratified random sample per theme (relevant + filtered items) with
                        empty `judgement` columns, for precision labelling
"""
import csv
import json
import random
from collections import Counter, defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .classify import classify_themes
from .ingest import load_rules
from .models import Country, Item, ItemRegion, ItemTheme, Outlet, Theme
from .network import jaccard, title_tokens


def summarise(s: Session, country: Country) -> dict:
    rules = load_rules(s, country.id)
    themes = {t.id: t for t in s.scalars(select(Theme))}
    items = s.scalars(select(Item).where(Item.country_id == country.id, Item.kind == "article")).all()
    links = defaultdict(list)
    for it in s.scalars(select(ItemTheme).where(ItemTheme.active.is_(True))):
        links[it.item_id].append(it.theme_id)
    regions = defaultdict(list)
    for ir in s.scalars(select(ItemRegion).where(ItemRegion.active.is_(True))):
        regions[ir.item_id].append(ir.region_id)
    outlets = {o.id: o for o in s.scalars(select(Outlet))}

    by_source = Counter(i.source_key for i in items)
    by_month = Counter(i.published_at.strftime("%Y-%m") for i in items if i.relevant)
    by_lang = Counter(i.lang or "und" for i in items if i.relevant)
    now = datetime.utcnow()
    future = [i.id for i in items if i.published_at > now]
    ancient = [i.id for i in items if i.published_at.year < 2011]
    filtered = Counter((i.extra or {}).get("filtered") for i in items if not i.relevant)
    relevant = [i for i in items if i.relevant]

    # near-duplicate titles from the same outlet within 3 days (syndication within an outlet,
    # or the same story collected via two URLs)
    dup = 0
    by_outlet = defaultdict(list)
    for i in relevant:
        by_outlet[i.outlet_id].append(i)
    for arr in by_outlet.values():
        arr.sort(key=lambda x: x.published_at)
        toks = [title_tokens(x.title or "") for x in arr]
        for a in range(len(arr)):
            for b in range(a + 1, min(a + 25, len(arr))):
                if (arr[b].published_at - arr[a].published_at).days > 3:
                    break
                if jaccard(toks[a], toks[b]) >= 0.85:
                    dup += 1
                    break
    # language detection vs collection language (gnews/alerts query language)
    from .textnorm import detect_lang
    lang_mismatch = sum(1 for i in relevant if i.source_key in ("gnews", "galerts") and i.title
                        and detect_lang(i.title) != (i.lang or "und") and detect_lang(i.title) in ("ar", "en"))
    # rule confirmation per theme (precision proxy) and theme counts
    per_theme = {}
    for tid, t in themes.items():
        tagged = [i for i in relevant if tid in links.get(i.id, [])]
        if not tagged:
            continue
        confirmed = sum(1 for i in tagged if tid in classify_themes(f"{i.title or ''} {i.snippet or ''}", rules.themes))
        per_theme[t.slug] = {"articles": len(tagged), "rule_confirmed": round(confirmed / len(tagged), 3),
                             "arabic_share": round(sum(1 for i in tagged if i.lang == "ar") / len(tagged), 3),
                             "with_region": round(sum(1 for i in tagged if regions.get(i.id)) / len(tagged), 3)}
    top_outlets = Counter(outlets[i.outlet_id].name for i in relevant if i.outlet_id in outlets).most_common(15)
    return {
        "country": country.iso2, "generated": now.isoformat(timespec="seconds"),
        "articles_total": len(items), "articles_relevant": len(relevant),
        "by_source": dict(by_source), "by_language": dict(by_lang), "by_month": dict(sorted(by_month.items())),
        "filtered_reasons": {str(k): v for k, v in filtered.items()},
        "future_dated": len(future), "before_2011": len(ancient),
        "near_duplicate_same_outlet": dup, "language_mismatch": lang_mismatch,
        "with_region_share": round(sum(1 for i in relevant if regions.get(i.id)) / max(1, len(relevant)), 3),
        "themes": per_theme, "top_outlets": top_outlets,
    }


def sample(s: Session, country: Country, path, per_theme: int = 40, filtered_per_theme: int = 10, seed: int = 11,
           theme_slugs: list[str] | None = None) -> int:
    rnd = random.Random(seed)
    themes = [t for t in s.scalars(select(Theme).where(Theme.active.is_(True)))
              if not theme_slugs or any(t.slug.startswith(x) for x in theme_slugs)]
    outlets = {o.id: o for o in s.scalars(select(Outlet))}
    rows = []
    for t in themes:
        ids = s.scalars(select(ItemTheme.item_id).where(ItemTheme.theme_id == t.id, ItemTheme.active.is_(True))).all()
        items = s.scalars(select(Item).where(Item.id.in_(ids), Item.kind == "article")).all()
        rel = [i for i in items if i.relevant]
        filt = [i for i in items if not i.relevant]
        for group, pool, k in (("relevant", rel, per_theme), ("filtered", filt, filtered_per_theme)):
            for i in rnd.sample(pool, min(k, len(pool))):
                rows.append({"theme": t.slug, "group": group, "item_id": i.id, "date": i.published_at.date().isoformat(),
                             "lang": i.lang, "source": i.source_key,
                             "outlet": outlets.get(i.outlet_id).name if i.outlet_id in outlets else "",
                             "title": (i.title or "").replace("\n", " "), "url": i.url,
                             "about_country": "", "on_theme": "", "note": ""})
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["theme"])
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def run(s: Session, out_dir, theme_slugs=None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    country = s.scalar(select(Country))
    summ = summarise(s, country)
    (out_dir / "review_summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=2), encoding="utf-8")
    n = sample(s, country, out_dir / "review_sample.csv", theme_slugs=theme_slugs)
    return {"summary": str(out_dir / "review_summary.json"), "sample_rows": n}
