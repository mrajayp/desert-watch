"""Re-run the current theme and place rules over stored articles.

Only rule and query links change: a rule link is active when the rules match, a query link
(a search or alert result) is active only when the rules confirm it. User corrections and
learned-model links are never touched. Articles are read in id order, BATCH at a time, and
each batch is committed and dropped from the session so memory stays flat."""
from collections import Counter

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from .classify import clean_snippet, tag_places
from .ingest import Rules, apply_relevance_guard, evidence, load_rules, query_key, rule_for, theme_hits
from .models import Country, Item, ItemRegion, ItemTheme, Region, Theme

BATCH = 2000
OURS = ("rule", "query")


def retag_item(s: Session, item: Item, rules: Rules, links: dict, regions: dict | None = None,
               themes: list | None = None) -> int:
    """Bring one article's rule and query links in line with the rules. `links` maps theme_id ->
    ItemTheme; with `regions` (region_id -> ItemRegion) rule place tags are re-run too.
    Returns the number of rows added or changed."""
    themes = rules.themes if themes is None else themes
    snippet = clean_snippet(item.source_key, item.title, item.snippet)
    hits = theme_hits(rules, item.title, snippet, themes)
    n = 0
    for r in themes:
        lk, hit = links.get(r.theme_id), hits.get(r.theme_id)
        if lk is None:
            if hit:
                s.add(ItemTheme(item_id=item.id, theme_id=r.theme_id, method="rule", active=True,
                                theme_version=r.version, evidence=evidence(*hit, query_key(item, r.slug))))
                n += 1
            continue
        if lk.method not in OURS:
            continue
        if hit:
            ev = evidence(*hit, query_key(item, r.slug))
        else:
            ev = evidence("query", [], query_key(item, r.slug)) if lk.method == "query" else None
        if (lk.active, lk.theme_version, lk.evidence) != (bool(hit), r.version, ev):
            lk.active, lk.theme_version, lk.evidence = bool(hit), r.version, ev
            n += 1
    if regions is not None:
        placed = set(tag_places(" ".join(x for x in (item.title, snippet) if x), rules.places))
        for rid in placed - regions.keys():
            s.add(ItemRegion(item_id=item.id, region_id=rid, method="rule"))
            n += 1
        for rid, ir in regions.items():
            if ir.method == "rule" and ir.active != (rid in placed):
                ir.active = rid in placed
                n += 1
    return n


def _batches(s: Session, batch: int, item_filter=()):
    """Articles in id order, `batch` at a time, with their theme and region links."""
    last = 0
    while True:
        items = s.scalars(select(Item).where(Item.kind == "article", Item.id > last, *item_filter)
                          .order_by(Item.id).limit(batch)).all()
        if not items:
            return
        lo, hi = items[0].id, items[-1].id
        links: dict = {}
        for lk in s.scalars(select(ItemTheme).where(ItemTheme.item_id.between(lo, hi))):
            links.setdefault(lk.item_id, {})[lk.theme_id] = lk
        regions: dict = {}
        for ir in s.scalars(select(ItemRegion).where(ItemRegion.item_id.between(lo, hi))):
            regions.setdefault(ir.item_id, {})[ir.region_id] = ir
        yield items, links, regions
        last = hi


def _done_batch(s: Session, dry_run: bool) -> None:
    if dry_run:
        s.flush()
    else:
        s.commit()
    s.expunge_all()


def retag_theme(s: Session, theme_id: int, batch: int = BATCH) -> int:
    """One theme over all articles (after an edit in Admin). Places are left alone."""
    t = s.get(Theme, theme_id)
    rule = rule_for(t)
    rules = {c.id: load_rules(s, c.id) for c in s.scalars(select(Country))}
    n = 0
    for items, links, _ in _batches(s, batch):
        for it in items:
            n += retag_item(s, it, rules[it.country_id], links.get(it.id, {}), themes=[rule])
        _done_batch(s, False)
    return n


def link_counts(s: Session) -> dict:
    """Active theme links on articles per theme: (all, counted). Counted = relevant and not a duplicate copy."""
    counted = func.sum(case((and_(Item.relevant.is_(True), Item.duplicate_of.is_(None)), 1), else_=0))
    rows = s.execute(select(Theme.slug, func.count(), counted).select_from(ItemTheme)
                     .join(Item, Item.id == ItemTheme.item_id).join(Theme, Theme.id == ItemTheme.theme_id)
                     .where(Item.kind == "article", ItemTheme.active.is_(True)).group_by(Theme.slug)).all()
    return {slug: (n, int(c or 0)) for slug, n, c in rows}


def item_counts(s: Session) -> dict:
    rel = and_(Item.relevant.is_(True), Item.duplicate_of.is_(None))
    row = s.execute(select(func.count(), func.sum(case((Item.relevant.is_(True), 1), else_=0)),
                           func.sum(case((rel, 1), else_=0))).where(Item.kind == "article")).one()
    return {"articles": row[0], "relevant": int(row[1] or 0), "counted": int(row[2] or 0)}


def region_counts(s: Session) -> Counter:
    """Active place tags on counted articles, per region slug."""
    return Counter(dict(s.execute(
        select(Region.slug, func.count()).select_from(ItemRegion).join(Item, Item.id == ItemRegion.item_id)
        .join(Region, Region.id == ItemRegion.region_id)
        .where(Item.kind == "article", ItemRegion.active.is_(True), Item.relevant.is_(True), Item.duplicate_of.is_(None))
        .group_by(Region.slug)).all()))


def retag_all(s: Session, *, dry_run: bool = False, batch: int = BATCH, out=print) -> dict:
    """Re-run the rules over every article, then the relevance guard. Idempotent: a second run
    changes nothing. With dry_run everything is rolled back after the counts are taken."""
    before = (link_counts(s), item_counts(s), region_counts(s))
    rules = {c.id: load_rules(s, c.id) for c in s.scalars(select(Country))}
    changed = seen = 0
    for items, links, regions in _batches(s, batch):
        for it in items:
            changed += retag_item(s, it, rules[it.country_id], links.get(it.id, {}), regions.get(it.id, {}))
        seen += len(items)
        _done_batch(s, dry_run)
        out(f"  {seen} articles, {changed} links added or changed")
    guard = sum(apply_relevance_guard(s, cid, commit=not dry_run) for cid in rules)
    after = (link_counts(s), item_counts(s), region_counts(s))
    if dry_run:
        s.rollback()
    report = {"articles": seen, "links_changed": changed, "relevance_flipped": guard,
              "themes": {k: {"before": before[0].get(k, (0, 0)), "after": after[0].get(k, (0, 0))}
                         for k in sorted(before[0].keys() | after[0].keys())},
              "items": {"before": before[1], "after": after[1]},
              "regions": {k: (before[2].get(k, 0), after[2].get(k, 0)) for k in sorted(before[2].keys() | after[2].keys())},
              "dry_run": dry_run}
    _print_report(report, out)
    return report


def _print_report(r: dict, out) -> None:
    out(("DRY RUN (nothing saved): " if r["dry_run"] else "") +
        f"{r['articles']} articles, {r['links_changed']} links added or changed, "
        f"relevance flipped on {r['relevance_flipped']}")
    out(f"{'theme':34} {'active before':>13} {'after':>8} {'counted before':>15} {'after':>8}")
    for slug, v in r["themes"].items():
        (a0, c0), (a1, c1) = v["before"], v["after"]
        out(f"{slug:34} {a0:>13} {a1:>8} {c0:>15} {c1:>8}")
    b, a = r["items"]["before"], r["items"]["after"]
    out(f"relevant articles {b['relevant']} -> {a['relevant']}; counted (relevant, not a duplicate) {b['counted']} -> {a['counted']}")
    moved = sorted(r["regions"].items(), key=lambda kv: -abs(kv[1][1] - kv[1][0]))[:8]
    out("place tags on counted articles (largest changes): " +
        ", ".join(f"{k} {x}->{y}" for k, (x, y) in moved if x != y))
