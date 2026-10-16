from datetime import date, timedelta

import httpx
import pytest
from sqlalchemy import select

from app import reach
from app.ingest import load_rules, store_article
from app.models import Outlet, OutletCategory, utcnow


@pytest.fixture()
def no_sleep(monkeypatch):
    monkeypatch.setattr("app.collectors.base.time.sleep", lambda _: None)


def tranco(calls):
    def handler(request):
        dom = request.url.path.rsplit("/", 1)[1]
        calls.append(dom)
        if dom == "broken.ly":
            return httpx.Response(503, text="busy")
        if dom.startswith("unranked"):
            return httpx.Response(200, json={"ranks": [], "domain": dom})
        return httpx.Response(200, json={"ranks": [{"date": "2026-10-14", "rank": 174517},
                                                   {"date": "2026-10-15", "rank": 174512}]})
    return handler


def test_tranco_entry_takes_latest_and_null_when_unranked():
    e = reach.tranco_entry({"ranks": [{"date": "2026-10-14", "rank": 2}, {"date": "2026-10-15", "rank": 1}]},
                           date(2026, 10, 16))
    assert e == {"value": 1, "as_of": "2026-10-15", "method": "tranco-list.eu api", "checked": "2026-10-16"}
    e = reach.tranco_entry({"ranks": []}, date(2026, 10, 16))
    assert e["value"] is None and e["as_of"] == "2026-10-16"


def test_snapshot_targets_and_history(db, no_sleep):
    cid = db.scalar(select(Outlet.country_id).limit(1))
    rules = load_rules(db, cid)
    now = utcnow()
    for dom, n in (("busy.example", 3), ("unranked.example", 1), ("t.co", 5), ("broken.ly", 1)):
        for k in range(n):
            store_article(db, cid, rules, url=f"https://{dom}/{k}", title=f"Libya: water cuts in Sabha {dom} {k}",
                          published_at=now - timedelta(days=2), source_key="rss")
    quiet = Outlet(country_id=cid, name="Quiet Libyan", domain="quiet-libyan.ly")   # no recent articles
    db.add(quiet)
    db.flush()
    db.add(OutletCategory(outlet_id=quiet.id, dimension="scope", value="libyan", confidence="reported",
                          evidence_url="https://example.org"))
    db.commit()

    doms = [o.domain for o in reach.targets(db)]
    assert "quiet-libyan.ly" in doms                                     # Libyan scope, even with no articles
    assert "t.co" not in doms and "busy.example" in doms
    assert reach.targets(db, limit=1)[0].domain in {o.domain for o in db.scalars(select(Outlet).join(
        OutletCategory, OutletCategory.outlet_id == Outlet.id).where(OutletCategory.value == "libyan"))}

    calls = []
    with httpx.Client(transport=httpx.MockTransport(tranco(calls))) as c:
        st = reach.snapshot(db, client=c, today=date(2026, 10, 16))
    assert st["errors"] == 1 and st["ranks"]["busy.example"] == 174512 and st["ranks"]["unranked.example"] is None
    busy = db.scalar(select(Outlet).where(Outlet.domain == "busy.example"))
    t = busy.external["reach"]["tranco"]
    assert (t["value"], t["as_of"], t["method"]) == (174512, "2026-10-15", "tranco-list.eu api")
    assert t["history"] == [{"value": 174512, "as_of": "2026-10-15"}]
    assert "reach" not in (db.scalar(select(Outlet).where(Outlet.domain == "broken.ly")).external or {})

    # next month: history grows, same-day reruns do not duplicate
    with httpx.Client(transport=httpx.MockTransport(tranco(calls))) as c:
        reach.snapshot(db, client=c, today=date(2026, 10, 16))
    db.refresh(busy)
    assert len(busy.external["reach"]["tranco"]["history"]) == 1
    busy.external = {**busy.external, "reach": {"tranco": {**t, "as_of": "2026-09-15", "history": [
        {"value": 180000, "as_of": "2026-09-15"}]}}}
    db.commit()
    with httpx.Client(transport=httpx.MockTransport(tranco(calls))) as c:
        reach.snapshot(db, client=c, today=date(2026, 10, 16))
    db.refresh(busy)
    assert [h["as_of"] for h in busy.external["reach"]["tranco"]["history"]] == ["2026-09-15", "2026-10-15"]


def test_long_runs_do_not_overwrite_each_others_outlet_figures(db):
    from app.db import SessionLocal
    from app.engagement import set_external
    o = Outlet(name="Two Jobs", domain="twojobs.ly", external={"social_media_scrape": {"articles": 3}})
    db.add(o)
    db.commit()
    stale = db.get(Outlet, o.id)                    # loaded at the start of a long run
    with SessionLocal() as other:                   # another job stores reach meanwhile
        x = other.get(Outlet, o.id)
        reach.store(x, {"value": 5, "as_of": "2026-10-15", "method": reach.METHOD, "checked": "2026-10-16"})
        other.commit()
    set_external(stale, "wp_json", {"ok": True, "checked": "2026-10-16"})
    db.commit()
    with SessionLocal() as check:
        ext = check.get(Outlet, o.id).external
    assert set(ext) == {"social_media_scrape", "reach", "wp_json"} and ext["reach"]["tranco"]["value"] == 5
