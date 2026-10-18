from collections import Counter, defaultdict
from datetime import date, timedelta

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import auth, settings
from ..db import get_db
from ..models import (ArticleAssessment, CellWeek, Event, Item, ItemTheme, NetworkEdgeWeek, NodeMetric, Outlet,
                      OutletCategory, Region, Theme, User, utcnow)
from .common import country_or_404, outlet_categories
from ..i18n import tr

router = APIRouter(prefix="/api")


def taxonomy() -> dict:
    with open(settings.CONFIG_DIR / "outlet_taxonomy.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@router.get("/outlets/taxonomy")
def get_taxonomy(_: User = Depends(auth.current_user)):
    return taxonomy()


def _quality(s: Session) -> dict[int, dict]:
    rows = s.execute(select(Item.outlet_id, func.avg(ArticleAssessment.accuracy), func.avg(ArticleAssessment.depth),
                            func.avg(ArticleAssessment.local_sourcing), func.count(ArticleAssessment.id))
                     .join(Item, Item.id == ArticleAssessment.item_id).group_by(Item.outlet_id)).all()
    return {o: {"accuracy": round(a, 2), "depth": round(d, 2), "local_sourcing": round(l, 2), "n": n}
            for o, a, d, l, n in rows}


@router.get("/outlets")
def list_outlets(country: str = "LY", days: int = 84, min_articles: int = 0, s: Session = Depends(get_db),
                 _: User = Depends(auth.current_user)):
    c = country_or_404(s, country)
    since = utcnow() - timedelta(days=days)
    counts = dict(s.execute(select(Item.outlet_id, func.count(Item.id)).where(
        Item.country_id == c.id, Item.kind == "article", Item.relevant.is_(True), Item.duplicate_of.is_(None), Item.published_at >= since)
        .group_by(Item.outlet_id)).all())
    langs = defaultdict(Counter)
    for o, l, n in s.execute(select(Item.outlet_id, Item.lang, func.count(Item.id)).where(
            Item.country_id == c.id, Item.kind == "article", Item.published_at >= since).group_by(Item.outlet_id, Item.lang)):
        langs[o][l or "und"] = n
    cats = outlet_categories(s)
    pending = Counter(o for (o,) in s.execute(select(OutletCategory.outlet_id).where(OutletCategory.status == "proposed")))
    q = _quality(s)
    out = []
    for o in s.scalars(select(Outlet).where(Outlet.active.is_(True))):
        n = counts.get(o.id, 0)
        if n < min_articles:
            continue
        out.append({"id": o.id, "name": o.name, "domain": o.domain, "languages": o.languages, "rss": bool(o.rss_url),
                    "base_city": o.base_city, "base_country": o.base_country, "lat": o.lat, "lon": o.lon,
                    "created_via": o.created_via, "monitored": o.monitored is not False,
                    "closed_on": o.closed_on.isoformat() if o.closed_on else None,
                    "external": o.external or {}, "articles": n, "lang_mix": dict(langs.get(o.id, {})),
                    "categories": cats.get(o.id, {}), "pending_changes": pending.get(o.id, 0),
                    "quality": q.get(o.id)})
    out.sort(key=lambda x: -x["articles"])
    return out


@router.get("/outlets/{oid}/history")
def outlet_history(oid: int, s: Session = Depends(get_db), u: User = Depends(auth.current_user)):
    names = auth.team_names(s, u)  # empty for a viewer: set_by comes back None
    return [{"id": c.id, "dimension": c.dimension, "value": c.value, "confidence": c.confidence,
             "evidence_url": c.evidence_url, "note": c.note, "status": c.status, "set_by": names.get(c.set_by),
             "valid_from": c.valid_from.isoformat(), "valid_to": c.valid_to.isoformat() if c.valid_to else None}
            for c in s.scalars(select(OutletCategory).where(OutletCategory.outlet_id == oid)
                               .order_by(OutletCategory.dimension, OutletCategory.valid_from.desc()))]


class CategoryIn(BaseModel):
    dimension: str
    value: str
    confidence: str
    evidence_url: str = Field(min_length=8, max_length=500)
    note: str | None = Field(default=None, max_length=2000)


def _activate(s: Session, cat: OutletCategory):
    for old in s.scalars(select(OutletCategory).where(
            OutletCategory.outlet_id == cat.outlet_id, OutletCategory.dimension == cat.dimension,
            OutletCategory.status == "active", OutletCategory.valid_to.is_(None), OutletCategory.id != cat.id)):
        old.valid_to = date.today()
    cat.status = "active"
    cat.valid_from = date.today()


@router.post("/outlets/{oid}/categories")
def set_category(oid: int, body: CategoryIn, s: Session = Depends(get_db), u: User = Depends(auth.require_contributor)):
    """Admins apply directly (previous value is closed, not overwritten); journalists propose."""
    if not s.get(Outlet, oid):
        raise HTTPException(404, tr("Unknown outlet"))
    tax = taxonomy()
    dim = next((d for d in tax["dimensions"] if d["key"] == body.dimension), None)
    if not dim or body.value not in dim["values"]:
        raise HTTPException(400, tr("Unknown dimension or value"))
    if body.confidence not in tax["confidence_levels"]:
        raise HTTPException(400, tr("Unknown confidence level"))
    if not body.evidence_url.startswith(("http://", "https://")):
        raise HTTPException(400, tr("Evidence must be a link."))
    cat = OutletCategory(outlet_id=oid, dimension=body.dimension, value=body.value, confidence=body.confidence,
                         evidence_url=body.evidence_url, note=body.note, set_by=u.id, status="proposed")
    s.add(cat)
    s.flush()
    if u.role == "admin":
        _activate(s, cat)
    s.add(Event(pseudo_id=u.pseudo_id, type="suggestion", object_type="outlet", object_key=str(oid),
                context={"dimension": body.dimension, "value": body.value, "applied": u.role == "admin"}))
    s.commit()
    return {"ok": True, "status": cat.status}


class ReviewIn(BaseModel):
    approve: bool


@router.post("/outlets/categories/{cid}/review")
def review_category(cid: int, body: ReviewIn, s: Session = Depends(get_db), u: User = Depends(auth.require_admin)):
    cat = s.get(OutletCategory, cid)
    if not cat or cat.status != "proposed":
        raise HTTPException(404, tr("No pending proposal"))
    if body.approve:
        _activate(s, cat)
    else:
        cat.status = "rejected"
    s.commit()
    return {"ok": True}


class OutletPatch(BaseModel):
    name: str | None = None
    base_city: str | None = None
    base_country: str | None = None
    lat: float | None = None
    lon: float | None = None
    rss_url: str | None = None
    active: bool | None = None
    # the day the outlet closed or became unreachable (null reopens it): its source|outlet pairs then stay
    # in the comparable basis so its silence shows as a real drop (scoring.comparable_pairs, flag outlet_closed)
    closed_on: date | None = None


@router.patch("/outlets/{oid}")
def patch_outlet(oid: int, body: OutletPatch, s: Session = Depends(get_db), u: User = Depends(auth.require_admin)):
    o = s.get(Outlet, oid)
    if not o:
        raise HTTPException(404, tr("Unknown outlet"))
    data = body.model_dump(exclude_unset=True)
    if data.get("closed_on") and data["closed_on"] > date.today():
        raise HTTPException(400, tr("The closing date cannot be in the future."))
    if "base_city" in data and data["base_city"] and "lat" not in data:
        # place on the map from the country's city list
        from ..models import Country
        c = s.get(Country, o.country_id) if o.country_id else None
        cities = (c.config.get("cities") if c else None) or {}
        if data["base_city"] in cities:
            o.lat, o.lon = cities[data["base_city"]]
    for k, v in data.items():
        setattr(o, k, v)
    s.commit()
    return {"ok": True}


# ---------------------------------------------------------------- network
@router.get("/network")
def network(country: str = "LY", theme_id: int | None = None, theme_group: str | None = None, week: date | None = None,
            weeks: int = 4, min_weight: float = 1, s: Session = Depends(get_db), _: User = Depends(auth.current_user)):
    c = country_or_404(s, country)
    week = week or s.scalar(select(func.max(NetworkEdgeWeek.week_start)).where(NetworkEdgeWeek.country_id == c.id))
    edges_q = select(NetworkEdgeWeek).where(NetworkEdgeWeek.country_id == c.id)
    weekly = []
    if week:
        start = week - timedelta(weeks=weeks - 1)
        wq = edges_q.where(NetworkEdgeWeek.kind.in_(("outlet_region", "outlet_theme")),
                           NetworkEdgeWeek.week_start >= start, NetworkEdgeWeek.week_start <= week)
        if theme_id:
            wq = wq.where(NetworkEdgeWeek.theme_id == theme_id)
        elif theme_group:
            wq = wq.where(NetworkEdgeWeek.theme_id.in_(select(Theme.id).where(Theme.group == theme_group)))
        weekly = s.scalars(wq).all()
    static = s.scalars(edges_q.where(NetworkEdgeWeek.kind.in_(("outlet_outlet", "syndication")))).all()

    agg = Counter()
    for e in weekly:
        agg[(e.kind, e.source_node, e.target_node)] += e.weight
    edges = [{"kind": k, "source": a, "target": b, "weight": w} for (k, a, b), w in agg.items() if w >= min_weight]
    edges += [{"kind": e.kind, "source": e.source_node, "target": e.target_node, "weight": e.weight} for e in static]

    used = {e["source"] for e in edges} | {e["target"] for e in edges}
    outlet_ids = [int(n[2:]) for n in used if n.startswith("o:")]
    outlets = {o.id: o for o in s.scalars(select(Outlet).where(Outlet.id.in_(outlet_ids)))}
    cats = outlet_categories(s, outlet_ids)
    metrics = {m.node: m for m in s.scalars(select(NodeMetric).where(NodeMetric.country_id == c.id))}
    volume = Counter()
    for e in edges:
        if e["kind"] == "outlet_theme":
            volume[e["source"]] += e["weight"]
    nodes = []
    for oid, o in outlets.items():
        key = f"o:{oid}"
        cat = cats.get(oid, {})
        m = metrics.get(key)
        nodes.append({"id": key, "type": "outlet", "name": o.name, "domain": o.domain, "lat": o.lat, "lon": o.lon,
                      "base_city": o.base_city, "base_country": o.base_country, "languages": o.languages,
                      "categories": {k: v["value"] for k, v in cat.items()},
                      "confidence": {k: v["confidence"] for k, v in cat.items()},
                      "articles": volume.get(key, 0), "community": m.community if m else None,
                      "centrality": m.centrality if m else 0})
    for r in s.scalars(select(Region).where(Region.country_id == c.id)):
        nodes.append({"id": f"r:{r.id}", "type": "region", "region_id": r.id, "name": r.name_en, "name_ar": r.name_ar,
                      "level": r.level, "lat": r.lat, "lon": r.lon, "parent": f"r:{r.parent_id}" if r.parent_id else None})
    for t in s.scalars(select(Theme).where(Theme.active.is_(True))):
        nodes.append({"id": f"t:{t.id}", "type": "theme", "theme_id": t.id, "name": t.name_en, "name_ar": t.name_ar})
    return {"week": week.isoformat() if week else None, "weeks": weeks, "theme_id": theme_id, "nodes": nodes,
            "edges": edges}


# ---------------------------------------------------------------- clusters
@router.get("/clusters")
def clusters(country: str = "LY", s: Session = Depends(get_db), _: User = Depends(auth.current_user)):
    """Coverage clusters (Louvain communities on outlet theme-specialisation similarity),
    each named in plain words from what makes it different: its most over-indexed themes,
    dominant language and scope. Plus a cluster × district table: the share of each
    cluster's articles that name each district (empty cells = no cluster covers it)."""
    c = country_or_404(s, country)
    metrics = s.scalars(select(NodeMetric).where(NodeMetric.country_id == c.id, NodeMetric.graph == "outlet_outlet",
                                                 NodeMetric.community.is_not(None))).all()
    comm_of = {int(m.node[2:]): m.community for m in metrics}
    if not comm_of:
        return {"clusters": [], "districts": [], "table": {}}
    themes = {t.id: t for t in s.scalars(select(Theme).where(Theme.active.is_(True)))}
    regions = {r.id: r for r in s.scalars(select(Region).where(Region.country_id == c.id))}
    theme_n = defaultdict(Counter)
    region_n = defaultdict(Counter)
    for e in s.scalars(select(NetworkEdgeWeek).where(NetworkEdgeWeek.country_id == c.id,
                                                     NetworkEdgeWeek.kind.in_(("outlet_theme", "outlet_region")))):
        oid = int(e.source_node[2:])
        if oid not in comm_of:
            continue
        if e.kind == "outlet_theme":
            theme_n[oid][int(e.target_node[2:])] += e.weight
        else:
            region_n[oid][int(e.target_node[2:])] += e.weight
    outlets = {o.id: o for o in s.scalars(select(Outlet).where(Outlet.id.in_(list(comm_of))))}
    cats = outlet_categories(s, list(comm_of))
    total_theme = Counter()
    for v in theme_n.values():
        total_theme.update(v)
    grand = sum(total_theme.values()) or 1
    by_comm = defaultdict(list)
    for oid, cm in comm_of.items():
        by_comm[cm].append(oid)
    out = []
    for cm, members in by_comm.items():
        tn = Counter()
        rn = Counter()
        lang = Counter()
        scope = Counter()
        for oid in members:
            tn.update(theme_n[oid])
            rn.update(region_n[oid])
            for l in outlets[oid].languages or ["und"]:
                lang[l] += 1
            scope[cats.get(oid, {}).get("scope", {}).get("value", "unknown")] += 1
        articles = sum(tn.values())
        if not articles:
            continue
        lift = sorted(((tn[t] / articles) / (total_theme[t] / grand), t) for t in tn if total_theme[t])[::-1]
        top = [themes[t] for _, t in lift[:2] if t in themes]
        main_lang = lang.most_common(1)[0][0]
        known_scope = [(k, v) for k, v in scope.most_common() if k != "unknown"]
        name = " & ".join(t.name_en.split(" (")[0] for t in top)
        tags = [{"ar": "Arabic", "en": "English"}.get(main_lang, main_lang.upper())]
        if known_scope and known_scope[0][1] >= len(members) / 2:
            tags.append(known_scope[0][0])
        districts = {rid: n for rid, n in rn.items() if regions.get(rid) and regions[rid].level == "district"}
        out.append({
            "id": cm, "name": name or "Mixed coverage", "name_ar": " و".join(t.name_ar.split(" (")[0] for t in top) or "تغطية متنوعة",
            "tags": tags, "outlets": len(members), "articles": articles,
            "top_outlets": [outlets[o].name for o in sorted(members, key=lambda o: -sum(theme_n[o].values()))[:5]],
            "themes": [{"theme_id": t, "share": round(n / articles, 3), "lift": round((n / articles) / (total_theme[t] / grand), 2)}
                       for t, n in tn.most_common()],
            "district_share": {str(rid): round(n / articles, 4) for rid, n in districts.items()},
            "members": [f"o:{o}" for o in members],
        })
    out.sort(key=lambda x: -x["articles"])
    total_articles = sum(x["articles"] for x in out) or 1
    for i, x in enumerate(out):
        x["rank"] = i
        x["share"] = round(x["articles"] / total_articles, 3)
    dists = [{"id": r.id, "name_en": r.name_en, "name_ar": r.name_ar, "parent_id": r.parent_id}
             for r in regions.values() if r.level == "district"]
    return {"clusters": out, "districts": sorted(dists, key=lambda d: (d["parent_id"], d["name_en"]))}


@router.get("/clusters/periods")
def cluster_periods(country: str = "LY", period_weeks: int = 4, s: Session = Depends(get_db),
                    _: User = Depends(auth.current_user)):
    """Articles per outlet and per cluster in consecutive fixed-length periods (default 4 weeks),
    over the same network window, for small multiples. The outlet set is held fixed (the
    current clusters' members) so differences between panels reflect coverage, not collection."""
    c = country_or_404(s, country)
    comm = {m.node: m.community for m in s.scalars(select(NodeMetric).where(
        NodeMetric.country_id == c.id, NodeMetric.graph == "outlet_outlet", NodeMetric.community.is_not(None)))}
    edges = s.scalars(select(NetworkEdgeWeek).where(NetworkEdgeWeek.country_id == c.id,
                                                    NetworkEdgeWeek.kind == "outlet_theme",
                                                    NetworkEdgeWeek.week_start.is_not(None))).all()
    if not edges or not comm:
        return {"periods": [], "outlets": {}, "clusters": {}}
    last = max(e.week_start for e in edges)
    first = min(e.week_start for e in edges)
    n_periods = max(1, ((last - first).days // 7 + 1) // period_weeks)
    periods = []
    for i in range(n_periods):
        end = last - timedelta(weeks=period_weeks * (n_periods - 1 - i))
        start = end - timedelta(weeks=period_weeks - 1)
        periods.append({"start": start.isoformat(), "end": (end + timedelta(days=6)).isoformat()})
    per_outlet = defaultdict(lambda: [0] * n_periods)
    per_cluster = defaultdict(lambda: [0] * n_periods)
    per_cluster_theme = defaultdict(lambda: [Counter() for _ in range(n_periods)])
    for e in edges:
        if e.source_node not in comm:
            continue
        idx = n_periods - 1 - ((last - e.week_start).days // 7) // period_weeks
        if idx < 0:
            continue
        per_outlet[e.source_node][idx] += e.weight
        per_cluster[comm[e.source_node]][idx] += e.weight
        per_cluster_theme[comm[e.source_node]][idx][int(e.target_node[2:])] += e.weight
    return {"periods": periods, "outlets": per_outlet,
            "clusters": {k: {"articles": v, "themes": [dict(x) for x in per_cluster_theme[k]]} for k, v in per_cluster.items()}}


@router.get("/outlets/blind-spots")
def blind_spots(country: str = "LY", s: Session = Depends(get_db), _: User = Depends(auth.current_user)):
    """Known outlets we only see in part (Facebook register pages: just the posts Google News
    indexes), with their reach in the period the external dataset covers, and any third-party
    labels as published."""
    c = country_or_404(s, country)
    rows = s.scalars(select(Outlet).where(Outlet.country_id == c.id, Outlet.monitored.is_(False))).all()
    cats = outlet_categories(s, [r.id for r in rows])
    out = []
    for r in rows:
        ext = (r.external or {}).get("social_media_scrape", {})
        out.append({"id": r.id, "name": r.name, "domain": r.domain, "kind": ext.get("kind"), "posts": ext.get("posts"),
                    "interactions": ext.get("interactions"), "comments": ext.get("comments"), "shares": ext.get("shares"),
                    "link": ext.get("link"), "period": ext.get("period"), "source": ext.get("source"),
                    "labels": {k: v["value"] for k, v in cats.get(r.id, {}).items() if k.startswith("scrape_")}})
    out.sort(key=lambda x: -(x["interactions"] or 0))
    return out


# ---------------------------------------------------------------- reach (engagement.py)
@router.get("/outlets/{oid}/reach")
def outlet_reach_api(oid: int, s: Session = Depends(get_db), _: User = Depends(auth.current_user)):
    """Dated reach figures for one outlet: Tranco web rank, the 2023-24 scrape's Facebook figures
    (historical) and our own Facebook median once there are enough readings."""
    from ..engagement import outlet_reach
    o = s.get(Outlet, oid)
    if not o:
        raise HTTPException(404, tr("Unknown outlet"))
    return outlet_reach(s, o)


# ---------------------------------------------------------------- one outlet
# Registered last: /outlets/taxonomy and /outlets/blind-spots above must match before {oid}.
@router.get("/outlets/{oid}")
def outlet_detail(oid: int, s: Session = Depends(get_db), u: User = Depends(auth.current_user)):
    """One outlet. ai_cited_4w: citations by AI assistants in the last 4 weeks (the AI answers audit), or
    None when the user may not see audit results yet."""
    from .ai_audit import ai_cited_4w
    o = s.get(Outlet, oid)
    if not o:
        raise HTTPException(404, tr("Unknown outlet"))
    return {"id": o.id, "name": o.name, "domain": o.domain, "languages": o.languages, "base_city": o.base_city,
            "base_country": o.base_country, "monitored": o.monitored is not False, "active": o.active,
            "closed_on": o.closed_on.isoformat() if o.closed_on else None,
            "categories": outlet_categories(s, [o.id]).get(o.id, {}), "ai_cited_4w": ai_cited_4w(s, u, o.id)}
