"""Outlet reach snapshots (monthly): dated figures in outlet.external['reach'].

Tranco web rank: GET https://tranco-list.eu/api/ranks/domain/<domain>, keyless, at most one request a
second. We store the latest daily rank as reach['tranco'] = {value, as_of, method, checked, history};
value is null when the site is not ranked. Web rank says little about Libyan reach (Arabic outlets
live on Facebook), so it is only ever shown dated and per outlet, never as a league table.

Which outlets: every Libyan-scope outlet plus the TOP_OUTLETS outlets with the most counted articles
in the last 12 weeks."""
from datetime import date, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .collectors.base import RunResult, http_client, polite_get
from .engagement import SHORTENERS, fresh_external
from .models import Country, Item, Outlet, OutletCategory, utcnow

TRANCO = "https://tranco-list.eu/api/ranks/domain/"
METHOD = "tranco-list.eu api"
HISTORY = 12
TOP_OUTLETS = 100


def targets(s: Session, limit: int | None = None) -> list[Outlet]:
    since = utcnow() - timedelta(weeks=12)
    counts = dict(s.execute(select(Item.outlet_id, func.count(Item.id)).where(
        Item.kind == "article", Item.relevant.is_(True), Item.duplicate_of.is_(None), Item.outlet_id.is_not(None),
        Item.published_at >= since).group_by(Item.outlet_id)).all())
    scope_values = {"libyan" if c.iso2 == "LY" else c.name_en.lower() for c in s.scalars(select(Country))}
    local = set(s.scalars(select(OutletCategory.outlet_id).where(
        OutletCategory.dimension == "scope", OutletCategory.value.in_(scope_values),
        OutletCategory.status == "active", OutletCategory.valid_to.is_(None))))
    top = {o for o, _ in sorted(counts.items(), key=lambda x: -x[1])[:TOP_OUTLETS]}
    rows = s.scalars(select(Outlet).where(Outlet.id.in_(local | top), Outlet.active.is_(True))).all()
    rows = [o for o in rows if "/" not in o.domain and o.domain not in SHORTENERS and "." in o.domain]
    # Libyan outlets first, then by volume, so a --limit run covers the ones we care most about
    rows.sort(key=lambda o: (o.id not in local, -counts.get(o.id, 0), o.domain))
    return rows[:limit] if limit else rows


def tranco_entry(payload: dict, today: date) -> dict:
    ranks = [r for r in (payload.get("ranks") or []) if isinstance(r, dict) and r.get("rank")]
    latest = max(ranks, key=lambda r: r.get("date") or "") if ranks else None
    return {"value": int(latest["rank"]) if latest else None,
            "as_of": (latest.get("date") if latest else None) or today.isoformat(),
            "method": METHOD, "checked": today.isoformat()}


def store(o: Outlet, entry: dict) -> None:
    ext = fresh_external(o)
    reach = dict(ext.get("reach") or {})
    old = reach.get("tranco") or {}
    hist = [h for h in old.get("history", []) if h.get("as_of") != entry["as_of"]]
    hist.append({"value": entry["value"], "as_of": entry["as_of"]})
    reach["tranco"] = {**entry, "history": sorted(hist, key=lambda h: h["as_of"])[-HISTORY:]}
    o.external = {**ext, "reach": reach}


def snapshot(s: Session, *, limit: int | None = None, client: httpx.Client | None = None,
             today: date | None = None) -> dict:
    today = today or utcnow().date()
    outlets = targets(s, limit)
    stats = {"outlets": len(outlets), "ranked": 0, "unranked": 0, "errors": 0, "ranks": {}}
    own = client is None
    client = client or http_client(timeout=20)
    try:
        for o in outlets:
            try:
                r = polite_get(client, TRANCO + o.domain, min_interval=1.0, retries=1)
                payload = r.json() if r.status_code == 200 else None
            except Exception:  # noqa: BLE001 - keep the previous snapshot, carry on
                payload = None
            if not isinstance(payload, dict):
                stats["errors"] += 1
                continue
            entry = tranco_entry(payload, today)
            store(o, entry)
            stats["ranked" if entry["value"] else "unranked"] += 1
            stats["ranks"][o.domain] = entry["value"]
            s.commit()
    finally:
        if own:
            client.close()
    return stats


def collect(s: Session, *, limit: int | None = None, **kw) -> RunResult:
    st = snapshot(s, limit=limit, **kw)
    return RunResult(rows=st["ranked"] + st["unranked"], errors=st["errors"],
                     detail=f"{st['outlets']} outlets: {st['ranked']} ranked, {st['unranked']} not ranked, "
                            f"{st['errors']} failed")
