"""Re-run the current theme and place rules over stored articles.

Only rule and query links change: a rule link is active when the rules match, a query link
(a search or alert result) is active only when the rules confirm it. A rule link the rules no
longer confirm becomes a query link when the item's own search or alert asked for that theme. User corrections and
learned-model links are never touched. Articles are read in id order, BATCH at a time, and
each batch is committed and dropped from the session so memory stays flat.

Writes are guarded UPDATEs (WHERE method is still 'rule' or 'query'), so a correction a user
makes while a batch is being worked out is never written over. A dry run writes nothing at all:
it works out the same changes in memory and adds them to the counts taken at the start, so it
never holds the database write lock."""
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import and_, bindparam, case, func, insert, or_, select
from sqlalchemy.orm import Session

from .classify import clean_snippet, tag_places
from .ingest import (Rules, apply_relevance_guard, evidence, guard_verdict, load_rules, not_counted_outlets, query_key,
                     rule_for, theme_hits)
from .models import AlertFeed, Country, Item, ItemRegion, ItemTheme, Region, Theme

BATCH = 2000
OURS = ("rule", "query")
_T, _R = ItemTheme.__table__, ItemRegion.__table__


@dataclass
class Plan:
    """What re-tagging changes for one article.
    links: theme_id -> (method, active, theme_version, evidence, new row?)
    regions: region_id -> (active, new row?)"""
    links: dict = field(default_factory=dict)
    regions: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.links) + len(self.regions)


def plan_item(item: Item, rules: Rules, links: dict, regions: dict | None = None, themes: list | None = None,
              alert_themes: dict | None = None) -> Plan:
    """Bring one article's rule and query links in line with the rules. `links` maps theme_id ->
    ItemTheme; with `regions` (region_id -> ItemRegion) rule place tags are re-run too. Reads only."""
    themes = rules.themes if themes is None else themes
    snippet = clean_snippet(item.source_key, item.title, item.snippet)
    hits = theme_hits(rules, item.title, snippet, themes)
    p = Plan()
    for r in themes:
        lk, hit = links.get(r.theme_id), hits.get(r.theme_id)
        if lk is None:
            if hit:
                p.links[r.theme_id] = ("rule", True, r.version, evidence(*hit, query_key(item, r.slug, alert_themes)), True)
            continue
        if lk.method not in OURS:
            continue
        qk = query_key(item, r.slug, alert_themes)
        method = lk.method
        if hit:
            ev = evidence(*hit, qk)
        elif method == "query" or qk:
            # no longer confirmed, but the item's own search or alert asked for this theme: a prior
            method, ev = "query", evidence("query", [], qk)
        else:
            ev = None
        new = (method, bool(hit), r.version, ev)
        if (lk.method, lk.active, lk.theme_version, lk.evidence) != new:
            p.links[r.theme_id] = (*new, False)
    if regions is not None:
        placed = set(tag_places(" ".join(x for x in (item.title, snippet) if x), rules.places))
        for rid in placed - regions.keys():
            p.regions[rid] = (True, True)
        for rid, ir in regions.items():
            if ir.method == "rule" and ir.active != (rid in placed):
                p.regions[rid] = (rid in placed, False)
    return p


# ---------------------------------------------------------------- writing
_UPD_LINK = (_T.update()
             .where(_T.c.item_id == bindparam("k_item"), _T.c.theme_id == bindparam("k_theme"),
                    or_(_T.c.method == "rule", _T.c.method == "query"))
             .values(method=bindparam("v_method", type_=_T.c.method.type),
                     active=bindparam("v_active", type_=_T.c.active.type),
                     theme_version=bindparam("v_version", type_=_T.c.theme_version.type),
                     evidence=bindparam("v_evidence", type_=_T.c.evidence.type)))
_UPD_REGION = (_R.update()
               .where(_R.c.item_id == bindparam("k_item"), _R.c.region_id == bindparam("k_region"), _R.c.method == "rule")
               .values(active=bindparam("v_active", type_=_R.c.active.type)))


def _insert_new(s: Session, table):
    """INSERT that skips a row a user added in the meantime (same primary key)."""
    name = s.get_bind().dialect.name
    if name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as dialect_insert
    elif name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as dialect_insert
    else:
        return insert(table)
    return dialect_insert(table).on_conflict_do_nothing()


def write_plans(s: Session, plans: list[tuple[int, Plan]]) -> None:
    upd, new, rupd, rnew = [], [], [], []
    for item_id, p in plans:
        for tid, (method, active, version, ev, is_new) in p.links.items():
            if is_new:
                new.append({"item_id": item_id, "theme_id": tid, "method": method, "active": active,
                            "theme_version": version, "evidence": ev, "score": None, "model_version": None})
            else:
                upd.append({"k_item": item_id, "k_theme": tid, "v_method": method, "v_active": active,
                            "v_version": version, "v_evidence": ev})
        for rid, (active, is_new) in p.regions.items():
            if is_new:
                rnew.append({"item_id": item_id, "region_id": rid, "method": "rule", "active": active})
            else:
                rupd.append({"k_item": item_id, "k_region": rid, "v_active": active})
    if upd:
        s.execute(_UPD_LINK, upd)
    if new:
        s.execute(_insert_new(s, _T), new)
    if rupd:
        s.execute(_UPD_REGION, rupd)
    if rnew:
        s.execute(_insert_new(s, _R), rnew)


# ---------------------------------------------------------------- reading
def _batches(s: Session, batch: int, with_regions: bool = True):
    """Articles in id order, `batch` at a time, with their theme and region links."""
    last = 0
    while True:
        items = s.scalars(select(Item).where(Item.kind == "article", Item.id > last)
                          .order_by(Item.id).limit(batch)).all()
        if not items:
            return
        last = items[-1].id
        # by id range, articles only: page-view items sit between articles and carry many links
        span = (Item.kind == "article", Item.id.between(items[0].id, last))
        links: dict = {}
        for lk in s.scalars(select(ItemTheme).join(Item, Item.id == ItemTheme.item_id).where(*span)):
            links.setdefault(lk.item_id, {})[lk.theme_id] = lk
        regions: dict = {}
        if with_regions:
            for ir in s.scalars(select(ItemRegion).join(Item, Item.id == ItemRegion.item_id).where(*span)):
                regions.setdefault(ir.item_id, {})[ir.region_id] = ir
        yield items, links, regions


def _alert_themes(s: Session) -> dict:
    """alert key -> theme slug, for alerts filed under a theme (older items only name the alert)."""
    return dict(s.execute(select(AlertFeed.key, Theme.slug).join(Theme, Theme.id == AlertFeed.theme_id)).all())


def retag_theme(s: Session, theme_id: int, batch: int = BATCH) -> int:
    """One theme over all articles (after an edit in Admin). Places are left alone."""
    rule = rule_for(s.get(Theme, theme_id))
    rules = {c.id: load_rules(s, c.id) for c in s.scalars(select(Country))}
    not_counted = {cid: not_counted_outlets(s, r.labelled_outlets) for cid, r in rules.items()}
    alerts = _alert_themes(s)
    n = 0
    for items, links, _ in _batches(s, batch, with_regions=False):
        plans = [(it.id, plan_item(it, rules[it.country_id], links.get(it.id, {}), themes=[rule], alert_themes=alerts))
                 for it in items]
        write_plans(s, plans)
        n += sum(len(p) for _, p in plans)
        s.commit()
        s.expunge_all()
    return n


# ---------------------------------------------------------------- counts
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


class _Delta:
    """How the counts above move, worked out item by item (the dry run writes nothing)."""

    def __init__(self, s: Session):
        self.theme_slug = dict(s.execute(select(Theme.id, Theme.slug)).all())
        self.region_slug = dict(s.execute(select(Region.id, Region.slug)).all())
        self.links, self.counted, self.regions = Counter(), Counter(), Counter()
        self.relevant = self.items_counted = 0

    def add(self, it: Item, links: dict, regions: dict, p: Plan, relevant: bool) -> None:
        single = it.duplicate_of is None
        was, now = bool(it.relevant) and single, bool(relevant) and single
        on = {tid for tid, lk in links.items() if lk.active}
        on_after = (on | {t for t, v in p.links.items() if v[1]}) - {t for t, v in p.links.items() if not v[1]}
        for tids, sign, counted in ((on, -1, was), (on_after, 1, now)):
            for tid in tids:
                self.links[self.theme_slug[tid]] += sign
                self.counted[self.theme_slug[tid]] += sign * counted
        placed = {rid for rid, ir in regions.items() if ir.active}
        placed_after = (placed | {r for r, v in p.regions.items() if v[0]}) - {r for r, v in p.regions.items() if not v[0]}
        for rids, sign, counted in ((placed, -1, was), (placed_after, 1, now)):
            if counted:
                for rid in rids:
                    self.regions[self.region_slug[rid]] += sign
        self.relevant += bool(relevant) - bool(it.relevant)
        self.items_counted += now - was

    def after(self, before: tuple) -> tuple:
        links, items, regions = before
        th = {k: (links.get(k, (0, 0))[0] + self.links[k], links.get(k, (0, 0))[1] + self.counted[k])
              for k in links.keys() | self.links.keys()}
        rg = Counter({k: regions.get(k, 0) + self.regions[k] for k in regions.keys() | self.regions.keys()})
        return ({k: v for k, v in th.items() if v[0]},
                {**items, "relevant": items["relevant"] + self.relevant, "counted": items["counted"] + self.items_counted},
                Counter({k: v for k, v in rg.items() if v}))


# ---------------------------------------------------------------- the full pass
def retag_all(s: Session, *, dry_run: bool = False, batch: int = BATCH, out=print) -> dict:
    """Re-run the rules over every article, then the relevance guard. Idempotent: a second run
    changes nothing. A dry run writes nothing and reports the same numbers a real run would."""
    before = (link_counts(s), item_counts(s), region_counts(s))
    rules = {c.id: load_rules(s, c.id) for c in s.scalars(select(Country))}
    not_counted = {cid: not_counted_outlets(s, r.labelled_outlets) for cid, r in rules.items()}
    alerts = _alert_themes(s)
    delta = _Delta(s) if dry_run else None
    changed = seen = flips = 0
    for items, links, regions in _batches(s, batch):
        plans = []
        for it in items:
            lk, rg = links.get(it.id, {}), regions.get(it.id, {})
            p = plan_item(it, rules[it.country_id], lk, rg, alert_themes=alerts)
            plans.append((it.id, p))
            changed += len(p)
            if dry_run:
                ok = guard_verdict(rules[it.country_id], it, not_counted[it.country_id])
                relevant = it.relevant if ok is None else ok
                flips += ok is not None and it.relevant != ok
                delta.add(it, lk, rg, p, relevant)
        seen += len(items)
        if not dry_run:
            write_plans(s, plans)
            s.commit()
        s.expunge_all()
        if dry_run:
            s.rollback()  # nothing was written; this only hands the connection back
        out(f"  {seen} articles, {changed} links added or changed")
    if dry_run:
        after = delta.after(before)
    else:
        flips = sum(apply_relevance_guard(s, cid) for cid in rules)
        after = (link_counts(s), item_counts(s), region_counts(s))
    report = {"articles": seen, "links_changed": changed, "relevance_flipped": flips,
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
    out(f"relevant articles {b['relevant']} -> {a['relevant']}, counted (relevant, not a duplicate) {b['counted']} -> {a['counted']}")
    moved = sorted(r["regions"].items(), key=lambda kv: -abs(kv[1][1] - kv[1][0]))[:8]
    out("place tags on counted articles (largest changes): " +
        ", ".join(f"{k} {x}->{y}" for k, (x, y) in moved if x != y))
