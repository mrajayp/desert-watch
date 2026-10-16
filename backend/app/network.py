"""Precomputed coverage networks (nightly). The browser only draws.

Node ids: 'o:<outlet_id>', 'r:<region_id>', 't:<theme_id>'.
Edge kinds:
  outlet_region  per week, per theme: articles by outlet that mention a place in the region
  outlet_theme   per week: articles by outlet on the theme
  outlet_outlet  whole window: cosine similarity of outlets' theme profiles (top-k)
  syndication    whole window: near-identical headlines, earlier outlet -> later outlet
Also writes story pickup (item_engagement source='pickup', age_bucket='now'): how many distinct
outlets carried each article's story in the last 12 weeks, from the same headline matches. Pickup
covers every counted article with an outlet, tagged with a theme or not.
"""
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

import networkx as nx
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from .engagement import SHORTENERS, upsert_readings
from .models import (Country, Item, ItemEngagement, ItemRegion, ItemTheme, NetworkEdgeWeek, NodeMetric, Outlet,
                     Region, utcnow)
from .scoring import week_start
from .textnorm import normalise

TOP_K_SIMILAR = 3
MIN_SIMILARITY = 0.5
MIN_ARTICLES_FOR_SIMILARITY = 10
MAX_SIMILARITY_NODES = 120
SYNDICATION_JACCARD = 0.75
SYNDICATION_HOURS = 48


def title_tokens(title: str) -> frozenset[str]:
    return frozenset(t for t in normalise(title).split() if len(t) > 2)


def jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def find_syndication(items: list[tuple[int, int, datetime, str]], *, clusters: bool = False):
    """items: (item_id, outlet_id, published_at, title). Returns Counter[(from_outlet, to_outlet)].
    With clusters=True also returns the stories: lists of item ids joined (union-find) by the same
    matched pairs, singletons included. Blocking on the two rarest tokens keeps this near-linear."""
    toks = [(i, o, p, title_tokens(t)) for i, o, p, t in items if t]
    parent = {x[0]: x[0] for x in toks}

    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    df = Counter(tok for *_, ts in toks for tok in ts)
    blocks = defaultdict(list)
    for idx, (_, _, _, ts) in enumerate(toks):
        for tok in sorted(ts, key=lambda x: (df[x], x))[:2]:
            blocks[tok].append(idx)
    seen, pairs = set(), Counter()
    for members in blocks.values():
        if len(members) > 200:
            continue
        for a_i in range(len(members)):
            for b_i in range(a_i + 1, len(members)):
                a, b = toks[members[a_i]], toks[members[b_i]]
                key = (a[0], b[0])
                if key in seen or a[1] == b[1]:
                    continue
                seen.add(key)
                if abs((a[2] - b[2]).total_seconds()) > SYNDICATION_HOURS * 3600:
                    continue
                if jaccard(a[3], b[3]) >= SYNDICATION_JACCARD:
                    first, second = (a, b) if a[2] <= b[2] else (b, a)
                    pairs[(first[1], second[1])] += 1
                    parent[root(a[0])] = root(b[0])
    if not clusters:
        return pairs
    stories = defaultdict(list)
    for x in toks:
        stories[root(x[0])].append(x[0])
    return pairs, list(stories.values())


def story_pickup(items: list[tuple[int, int, datetime, str]], stories: list[list[int]]) -> dict[int, dict]:
    """item_id -> pickup reading: distinct outlets that carried the item's story (1 = only its own)."""
    outlet = {i: o for i, o, *_ in items}
    out = {}
    for members in stories:
        n = len({outlet[i] for i in members})
        for i in members:
            out[i] = {"total": float(n), "raw": {"story": min(members)} if n > 1 else {}}
    return out


def pickup_readings(s: Session, country_id: int, since: datetime) -> dict[int, dict]:
    """Story pickup for every counted article with an outlet since `since`, with or without a theme.
    Link shorteners are not outlets: left out."""
    shorteners = set(s.scalars(select(Outlet.id).where(Outlet.domain.in_(SHORTENERS))))
    rows = s.execute(select(Item.id, Item.outlet_id, Item.published_at, Item.title).where(
        Item.country_id == country_id, Item.kind == "article", Item.relevant.is_(True), Item.duplicate_of.is_(None),
        Item.outlet_id.is_not(None), Item.published_at >= since)).all()
    items = [(i, o, p, t or "") for i, o, p, t in rows if o not in shorteners]
    _, stories = find_syndication(items, clusters=True)
    return story_pickup(items, stories)


def store_pickup(s: Session, country_id: int, since: datetime, readings: dict[int, dict]) -> int:
    """Writes the readings that changed and removes the readings of articles since `since` that left
    the set (now a duplicate, not relevant, or without an outlet)."""
    n = upsert_readings(s, "pickup", "now", readings)
    had = s.scalars(select(ItemEngagement.item_id).join(Item, Item.id == ItemEngagement.item_id).where(
        ItemEngagement.source == "pickup", Item.country_id == country_id, Item.published_at >= since)).all()
    gone = [i for i in had if i not in readings]
    for i in range(0, len(gone), 900):
        s.execute(delete(ItemEngagement).where(ItemEngagement.source == "pickup",
                                               ItemEngagement.item_id.in_(gone[i:i + 900])))
    return n + len(gone)


def cosine(u: dict, v: dict) -> float:
    dot = sum(u[k] * v.get(k, 0) for k in u)
    nu = math.sqrt(sum(x * x for x in u.values()))
    nv = math.sqrt(sum(x * x for x in v.values()))
    return dot / (nu * nv) if nu and nv else 0.0


SIMILARITY_WEEKS = 12  # clusters and reprints describe the recent window; weekly edges cover all history


def compute(s: Session, country_id: int, *, weeks: int = 12, today: date | None = None) -> int:
    today = today or date.today()
    first = week_start(today) - timedelta(weeks=weeks - 1)
    since = datetime.combine(first, datetime.min.time())
    regions = {r.id: r for r in s.scalars(select(Region).where(Region.country_id == country_id))}

    rows = s.execute(
        select(Item.id, Item.outlet_id, Item.published_at, Item.title, ItemTheme.theme_id)
        .join(ItemTheme, and_(ItemTheme.item_id == Item.id, ItemTheme.active.is_(True)))
        .where(Item.country_id == country_id, Item.kind == "article", Item.relevant.is_(True), Item.duplicate_of.is_(None),
               Item.outlet_id.is_not(None), Item.published_at >= since)).all()
    ids = {r.id for r in rows}
    item_regions = defaultdict(set)
    for ir in s.scalars(select(ItemRegion).where(ItemRegion.active.is_(True))):
        if ir.item_id in ids and ir.region_id in regions:
            # attach to the district and its macro region
            item_regions[ir.item_id].add(ir.region_id)
            p = regions[ir.region_id].parent_id
            if p and regions[p].level == "macro":
                item_regions[ir.item_id].add(p)

    o_r = Counter()   # (outlet, region, theme, week)
    o_t = Counter()   # (outlet, theme, week)
    profile = defaultdict(Counter)
    titles = {}
    recent = datetime.combine(week_start(today) - timedelta(weeks=SIMILARITY_WEEKS - 1), datetime.min.time())
    for r in rows:
        wk = week_start(r.published_at.date())
        o_t[(r.outlet_id, r.theme_id, wk)] += 1
        for reg in item_regions.get(r.id, ()):
            o_r[(r.outlet_id, reg, r.theme_id, wk)] += 1
        if r.published_at >= recent:
            profile[r.outlet_id][r.theme_id] += 1
            titles[r.id] = (r.id, r.outlet_id, r.published_at, r.title or "")
    pickup = pickup_readings(s, country_id, recent)   # before the write below: clustering is the slow part

    # Replace only what this run recomputes: weekly edges from `first` on, plus the whole-window
    # kinds. (The hourly 12-week run used to wipe the full weekly history until the nightly run.)
    s.execute(delete(NetworkEdgeWeek).where(
        NetworkEdgeWeek.country_id == country_id,
        or_(and_(NetworkEdgeWeek.kind.in_(("outlet_region", "outlet_theme")), NetworkEdgeWeek.week_start >= first),
            NetworkEdgeWeek.kind.in_(("outlet_outlet", "syndication")))))
    edges = []
    for (o, reg, t, wk), w in o_r.items():
        edges.append(NetworkEdgeWeek(country_id=country_id, kind="outlet_region", source_node=f"o:{o}",
                                     target_node=f"r:{reg}", theme_id=t, week_start=wk, weight=w))
    for (o, t, wk), w in o_t.items():
        edges.append(NetworkEdgeWeek(country_id=country_id, kind="outlet_theme", source_node=f"o:{o}",
                                     target_node=f"t:{t}", theme_id=t, week_start=wk, weight=w))
    # Similarity on theme *specialisation*: each outlet's theme shares minus the overall
    # shares (raw profiles all look alike because every outlet covers the big themes).
    outlets = sorted((o for o, p in profile.items() if sum(p.values()) >= MIN_ARTICLES_FOR_SIMILARITY),
                     key=lambda o: -sum(profile[o].values()))[:MAX_SIMILARITY_NODES]
    total = Counter()
    for o in outlets:
        total.update(profile[o])
    grand = sum(total.values()) or 1
    base = {t: v / grand for t, v in total.items()}
    resid = {}
    for o in outlets:
        n = sum(profile[o].values())
        resid[o] = {t: profile[o].get(t, 0) / n - base[t] for t in base}
    sim_graph = nx.Graph()
    for o in outlets:
        sims = sorted(((cosine(resid[o], resid[o2]), o2) for o2 in outlets if o2 != o), reverse=True)
        for sim, o2 in sims[:TOP_K_SIMILAR]:
            if sim >= MIN_SIMILARITY:
                sim_graph.add_edge(o, o2, weight=sim)
    for a, b, d in sim_graph.edges(data=True):
        edges.append(NetworkEdgeWeek(country_id=country_id, kind="outlet_outlet", source_node=f"o:{a}",
                                     target_node=f"o:{b}", weight=round(d["weight"], 4)))
    # reprints (link shorteners are not outlets: left out)
    shorteners = set(s.scalars(select(Outlet.id).where(Outlet.domain.in_(SHORTENERS))))
    story_items = [v for v in titles.values() if v[1] not in shorteners]
    syndication = find_syndication(story_items)
    for (a, b), w in syndication.items():
        edges.append(NetworkEdgeWeek(country_id=country_id, kind="syndication", source_node=f"o:{a}",
                                     target_node=f"o:{b}", weight=w))
    s.add_all(edges)
    store_pickup(s, country_id, recent, pickup)

    # node metrics on the outlet-similarity graph (communities = coverage clusters)
    s.execute(delete(NodeMetric).where(NodeMetric.country_id == country_id))
    if sim_graph.number_of_nodes():
        comms = nx.community.louvain_communities(sim_graph, weight="weight", seed=42)
        comm_of = {n: i for i, c in enumerate(comms) for n in c}
        cent = nx.degree_centrality(sim_graph)
        for n in sim_graph.nodes:
            s.add(NodeMetric(country_id=country_id, graph="outlet_outlet", node=f"o:{n}",
                             degree=sim_graph.degree(n), strength=sim_graph.degree(n, weight="weight"),
                             community=comm_of.get(n), centrality=cent.get(n, 0), computed_at=utcnow()))
    s.commit()
    return len(edges)


def compute_all(s: Session, **kw) -> int:
    return sum(compute(s, c.id, **kw) for c in s.scalars(select(Country)))
