from datetime import date, datetime

from sqlalchemy import select

from app.models import Event, Item, Label, Outlet, OutletCategory
from tests.conftest import ids, login


def test_requires_login(client):
    assert client.get("/api/meta").status_code == 401


def test_public_health_says_only_ok_and_scheduler(client, db):
    from app.models import SourceRun
    db.add(SourceRun(source_key="rss", started_at=datetime(2020, 1, 1), status="error", error="old"))
    db.commit()
    assert client.get("/health").json() == {"ok": True, "scheduler": False}   # never the schedule, never a stale source


def test_admin_health_reports_the_machine_and_is_admin_only(client, users, db):
    from app.models import SourceRun
    login(client, "j@example.org", "journo-password-1")
    assert client.get("/api/admin/health").status_code == 403
    client.post("/api/auth/logout")
    login(client, "admin@example.org", "admin-password-1")
    db.add(SourceRun(source_key="rss", started_at=datetime(2020, 1, 1), finished_at=datetime(2020, 1, 1), status="ok"))
    db.add(SourceRun(source_key="backup", started_at=datetime(2026, 10, 18, 1, 15), finished_at=datetime(2026, 10, 18, 1, 16),
                     status="ok", error="backups/desert_watch_2026-10-18.db.gz (41.2 MB uploaded), 1 older copies pruned"))
    db.commit()
    h = client.get("/api/admin/health").json()
    assert h["scheduler"] == {"running": False, "jobs": []}
    assert h["lock"] == {"held": False, "holder": None}
    assert set(h["memory"]) == {"rss_mb", "mem_available_mb", "swap_free_mb"}
    assert h["disk"]["free_mb"] > 0 and h["db"]["size_mb"] > 0 and h["db"]["path"].endswith(".db")
    assert h["last_backup"]["status"] == "ok" and h["last_backup"]["at"] == "2026-10-18T01:16" and "41.2 MB" in h["last_backup"]["note"]
    assert h["last_digest"] is None and h["last_recompute"] is None
    assert any(x["key"] == "rss" for x in h["stale_sources"])
    assert not any(x["key"] in ("acled", "ucdp", "reliefweb") for x in h["stale_sources"])   # waiting for keys, not stale
    from app import joblock
    with joblock.held(job="recompute_child"):
        h = client.get("/api/admin/health").json()
    assert h["lock"]["held"] is True and h["lock"]["holder"]["job"] == "recompute_child" and h["lock"]["holder"]["pid"]


def test_invite_flow(client, users):
    login(client, "admin@example.org", "admin-password-1")
    r = client.post("/api/admin/invites", json={"email": "new@example.org"})
    token = r.json()["invite_path"].split("/")[-1]
    client.post("/api/auth/logout")
    r = client.post("/api/auth/accept-invite", json={"token": token, "password": "short", "display_name": "N"})
    assert r.status_code == 400
    r = client.post("/api/auth/accept-invite", json={"token": token, "password": "long-enough-pw", "display_name": "N"})
    assert r.status_code == 200 and r.json()["role"] == "journalist"
    assert client.post("/api/auth/accept-invite", json={"token": token, "password": "long-enough-pw",
                                                        "display_name": "N"}).status_code == 400


def test_help_is_for_every_account_and_the_method_notes_for_admins(client, users):
    assert client.get("/api/content/help").status_code == 401
    login(client, "j@example.org", "journo-password-1")
    md = client.get("/api/content/help").json()["markdown"]
    # the glossary anchors the interface links to (/help#lens, /help#not-judged, /help#gap ...)
    assert md.startswith("# Help") and all(f"{{#{a}}}" in md for a in ("gap", "need-signal", "lens", "not-judged", "week", "warning", "updates"))
    ar = client.get("/api/content/help", headers={"X-Lang": "ar"}).json()["markdown"]
    assert ar.startswith("# المساعدة") and "{#not-judged}" in ar
    assert client.get("/api/content/how_the_numbers_work").status_code == 403
    assert client.get("/api/content/nothing").status_code == 404
    assert client.get("/api/content/..%2Fsettings").status_code == 404
    client.post("/api/auth/logout")
    login(client, "admin@example.org", "admin-password-1")
    assert client.get("/api/content/how_the_numbers_work").json()["markdown"].startswith("# How the numbers work")


def test_journalist_cannot_admin(client, users):
    login(client, "j@example.org", "journo-password-1")
    assert client.post("/api/admin/invites", json={"email": "x@example.org"}).status_code == 403


def test_vote_and_labels(client, users, db):
    themes, regions = ids(db)
    login(client, "j@example.org", "journo-password-1")
    body = {"theme_id": themes["health"], "region_id": regions["fezzan"], "week": "2026-10-05", "lens": "events",
            "vote": "real", "note": "Nobody has been to Ubari hospital"}
    assert client.post("/api/gap/vote", json=body).status_code == 200
    body["vote"] = "not_newsworthy"
    assert client.post("/api/gap/vote", json=body).status_code == 200  # upsert, one vote per user/gap/week
    assert client.post("/api/gap/vote", json={**body, "vote": "covered"}).status_code == 400  # needs link
    from app.learning import build_labels
    assert build_labels(db) >= 1
    assert build_labels(db) == 0  # idempotent
    lab = db.scalars(select(Label).where(Label.label_type == "gap_real")).all()
    assert lab[-1].value["vote"] == "not_newsworthy"


def test_implicit_events_recorded_and_filtered(client, users, db):
    """Opt-out removed 2026-10-13 (owner decision): implicit events are stored once the tracking
    notice has been acknowledged; unknown event types are still dropped."""
    login(client, "j@example.org", "journo-password-1")
    assert client.patch("/api/me", json={"ack_tracking_notice": True}).json()["tracking_notice_ack"] is True
    evs = [{"type": "impression", "object_type": "gap", "object_key": "1:1", "context": {"position": 3}},
           {"type": "dwell", "object_type": "gap", "object_key": "1:1", "context": {"seconds": 30}},
           {"type": "evil", "object_key": "x"}]
    assert client.post("/api/events", json={"events": evs}).json()["stored"] == 2
    assert "tracking_opt_out" not in client.patch("/api/me", json={"tracking_opt_out": True}).json()  # field gone
    assert client.post("/api/events", json={"events": evs}).json()["stored"] == 2
    assert client.post("/api/events", json={"events": [{"type": "comment"}]}).json()["stored"] == 1


def test_events_dropped_until_the_tracking_notice_is_acknowledged(client, users, db):
    """Tracking starts only after the notice (B-R1.10): before the ack, /api/events keeps nothing,
    whatever the client sends; explicit actions (a vote) are still logged by their own endpoint."""
    themes, regions = ids(db)
    login(client, "j@example.org", "journo-password-1")
    assert client.get("/api/me").json()["tracking_notice_ack"] is False
    evs = [{"type": "view", "object_type": "page", "object_key": "/"},
           {"type": "click", "object_type": "gap", "object_key": "1:1"}]
    assert client.post("/api/events", json={"events": evs}).json()["stored"] == 0
    assert db.scalar(select(Event).where(Event.type.in_(("view", "click")))) is None
    body = {"theme_id": themes["health"], "region_id": regions["fezzan"], "week": "2026-10-05", "lens": "events", "vote": "real"}
    assert client.post("/api/gap/vote", json=body).status_code == 200
    assert client.patch("/api/me", json={"ack_tracking_notice": True}).json()["tracking_notice_ack"] is True
    assert client.post("/api/events", json={"events": evs}).json()["stored"] == 2
    assert db.scalar(select(Event).where(Event.type == "view")) is not None


def test_correction_and_comment(client, users, db):
    themes, regions = ids(db)
    from app.ingest import load_rules, store_article
    country_id = db.scalar(select(Outlet.country_id).limit(1))
    it, _ = store_article(db, country_id, load_rules(db, country_id), url="https://ex.org/a",
                          title="Oil workers strike in Brega", published_at=datetime(2026, 10, 1), source_key="test")
    db.commit()
    login(client, "j@example.org", "journo-password-1")
    r = client.post(f"/api/items/{it.id}/correction", json={"theme_id": themes["economy"], "theme_relevant": False})
    assert themes["economy"] not in r.json()["theme_ids"]
    r = client.post(f"/api/items/{it.id}/correction", json={"region_id": regions["al_wahat"], "region_relevant": True})
    assert regions["al_wahat"] in r.json()["region_ids"]
    assert db.scalar(select(Event).where(Event.type == "correction")) is not None
    c = client.post("/api/comments", json={"object_type": "item", "object_key": str(it.id), "body": "@Admin see this"})
    assert c.json()["mentions"] == ["Admin"]
    reply = client.post("/api/comments", json={"object_type": "item", "object_key": str(it.id), "body": "ok",
                                               "parent_id": c.json()["id"]})
    assert reply.status_code == 200
    assert len(client.get(f"/api/comments?object_type=item&object_key={it.id}").json()) == 2
    r = client.post(f"/api/items/{it.id}/assessment", json={"accuracy": 3, "depth": 2, "local_sourcing": 1})
    assert r.status_code == 200
    assert client.get(f"/api/items/{it.id}").json()["assessments"]["mine"]["accuracy"] == 3


def test_category_requires_evidence_and_keeps_history(client, users, db):
    o = db.scalar(select(Outlet).where(Outlet.domain == "libyaherald.com"))
    login(client, "j@example.org", "journo-password-1")
    bad = {"dimension": "alignment", "value": "independent", "confidence": "reported", "evidence_url": "trust me"}
    assert client.post(f"/api/outlets/{o.id}/categories", json=bad).status_code in (400, 422)
    good = {**bad, "evidence_url": "https://example.org/media-landscape-study"}
    assert client.post(f"/api/outlets/{o.id}/categories", json=good).json()["status"] == "proposed"
    client.post("/api/auth/logout")
    login(client, "admin@example.org", "admin-password-1")
    pid = db.scalar(select(OutletCategory.id).where(OutletCategory.status == "proposed"))
    assert client.post(f"/api/outlets/categories/{pid}/review", json={"approve": True}).status_code == 200
    newer = {**good, "value": "tripoli_gnu_aligned", "confidence": "disputed"}
    assert client.post(f"/api/outlets/{o.id}/categories", json=newer).json()["status"] == "active"
    db.expire_all()
    hist = [c for c in client.get(f"/api/outlets/{o.id}/history").json() if c["dimension"] == "alignment"]
    assert len(hist) == 2 and sum(1 for c in hist if c["valid_to"] is None) == 1
    assert {c["set_by"] for c in hist} == {"Journo", "Admin"}


def test_viewers_see_no_names(client, users, db):
    """A read-only account sees votes, claims, comments and label history without the names of the
    people behind them (viewers see no names); contributors still see who did what."""
    from app.auth import create_user
    themes, regions = ids(db)
    create_user(db, "v@example.org", "viewer-password-1", "Viewer", "viewer")
    db.commit()
    gap = {"theme_id": themes["health"], "region_id": regions["fezzan"]}
    login(client, "j@example.org", "journo-password-1")
    assert client.post("/api/gap/vote", json={**gap, "week": "2026-10-05", "lens": "events", "vote": "real"}).status_code == 200
    assert client.post("/api/gap/claim", json={**gap, "status": "working"}).status_code == 200
    d = client.get("/api/gap", params={**gap, "lens": "events", "week": "2026-10-05"}).json()
    key = d["object_key"]
    assert client.post("/api/comments", json={"object_type": "gap", "object_key": key, "body": "hello"}).status_code == 200
    assert d["votes"][0]["user"] == "Journo" and d["claims"][0]["user"] == "Journo"
    assert client.get("/api/comments", params={"object_type": "gap", "object_key": key}).json()[0]["user"] == "Journo"
    o = db.scalar(select(Outlet).where(Outlet.domain == "libyaherald.com"))
    cat = {"dimension": "alignment", "value": "independent", "confidence": "reported", "evidence_url": "https://example.org/study"}
    assert client.post(f"/api/outlets/{o.id}/categories", json=cat).status_code == 200
    assert client.get(f"/api/outlets/{o.id}/history").json()[0]["set_by"] == "Journo"
    client.post("/api/auth/logout")
    login(client, "v@example.org", "viewer-password-1")
    d = client.get("/api/gap", params={**gap, "lens": "events", "week": "2026-10-05"}).json()
    assert d["votes"] and d["votes"][0]["user"] is None and d["votes"][0]["vote"] == "real"
    assert d["claims"] and d["claims"][0]["user"] is None and d["claims"][0]["status"] == "working"
    cs = client.get("/api/comments", params={"object_type": "gap", "object_key": key}).json()
    assert cs and cs[0]["user"] is None and cs[0]["body"] == "hello"
    hist = client.get(f"/api/outlets/{o.id}/history").json()
    assert hist and all(c["set_by"] is None for c in hist)


def test_delete_account(client, users, db):
    login(client, "j@example.org", "journo-password-1")
    client.patch("/api/me", json={"ack_tracking_notice": True})
    assert client.post("/api/events", json={"events": [{"type": "click", "object_key": "x"}]}).json()["stored"] == 1
    assert client.delete("/api/me").status_code == 200
    assert client.get("/api/me").status_code == 401
    assert db.scalar(select(Event)) is None


# ---------------------------------------------------------------- security headers, CSP reports, the __Host- cookie (C-R3.5)
ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]


def test_every_response_carries_the_security_headers_and_hsts_only_over_https(client, monkeypatch):
    import re
    from app import settings
    h = client.get("/health").headers
    csp = h["content-security-policy-report-only"]
    assert csp.startswith("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                          "connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; "
                          "object-src 'none'")
    assert "report-uri /api/csp-report" in csp and "report-to csp" in csp and h["reporting-endpoints"] == 'csp="/api/csp-report"'
    assert "content-security-policy" not in h                      # report-only for its first release: nothing is blocked yet
    assert h["referrer-policy"] == "no-referrer" and h["x-frame-options"] == "DENY" and h["x-content-type-options"] == "nosniff"
    assert h["permissions-policy"] == "camera=(), microphone=(), geolocation=()" and h["cross-origin-opener-policy"] == "same-origin"
    assert "strict-transport-security" not in h                    # plain HTTP in development and tests
    assert client.get("/api/meta").headers["x-frame-options"] == "DENY"   # an error answer (401) carries them too
    monkeypatch.setattr(settings, "COOKIE_SECURE", True)
    assert client.get("/health").headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"
    # the page shell holds no inline script (script-src 'self' allows none) and its favicon is a data: URL (img-src allows it)
    for page in (ROOT / "frontend" / "index.html", ROOT / "frontend" / "dist" / "index.html"):
        if page.exists():
            html = page.read_text(encoding="utf-8")
            scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", html, re.S)
            assert scripts and all("src=" in attrs and not body.strip() for attrs, body in scripts), page
            assert 'href="data:image/svg+xml' in html


def test_csp_reports_are_counted_per_directive_and_shown_to_admins(client, users):
    import json
    from app.api import admin
    admin.CSP_VIOLATIONS.clear()
    legacy = {"csp-report": {"document-uri": "https://desert-watch.fly.dev/", "violated-directive": "script-src 'self'",
                             "effective-directive": "script-src", "blocked-uri": "inline"}}
    r = client.post("/api/csp-report", content=json.dumps(legacy), headers={"Content-Type": "application/csp-report"})
    assert r.status_code == 204 and r.content == b""              # open to the browser, no sign-in, nothing echoed
    modern = [{"type": "csp-violation", "body": {"effectiveDirective": "img-src", "blockedURL": "https://e/"}},
              {"type": "csp-violation", "body": {"effectiveDirective": "img-src"}}]
    assert client.post("/api/csp-report", content=json.dumps(modern), headers={"Content-Type": "application/reports+json"}).status_code == 204
    assert client.post("/api/csp-report", content=b"not json").status_code == 204
    assert client.post("/api/csp-report", content=b"x" * 9000).status_code == 204   # over the cap: dropped, not counted
    login(client, "admin@example.org", "admin-password-1")
    assert client.get("/api/admin/health").json()["csp_violations"] == {"script-src": 1, "img-src": 2, "unknown": 1}
    admin.CSP_VIOLATIONS.clear()


def test_session_cookie_has_the_host_prefix_over_https_and_the_old_name_still_signs_in(db, users, monkeypatch):
    from fastapi.testclient import TestClient
    from app import auth, settings
    from app.main import app
    monkeypatch.setattr(settings, "COOKIE_SECURE", True)
    assert auth.cookie_name() == "__Host-dw_session" and auth.LEGACY_COOKIE == "dw_session"
    with TestClient(app, base_url="https://testserver") as c:
        r = c.post("/api/auth/login", json={"email": "j@example.org", "password": "journo-password-1"})
        assert r.status_code == 200
        sc = r.headers["set-cookie"]
        assert sc.startswith("__Host-dw_session=") and "Secure" in sc and "Path=/" in sc and "HttpOnly" in sc and "Domain" not in sc
        assert c.get("/api/me").status_code == 200
        token = c.cookies["__Host-dw_session"]
        c.cookies.clear()
        assert c.get("/api/me").status_code == 401
        # a browser signed in before the rename sends the old name: still signed in, for one release
        assert c.get("/api/me", headers={"Cookie": f"dw_session={token}"}).status_code == 200
        # sign-out ends the session and clears both names
        r = c.post("/api/auth/logout", headers={"Cookie": f"dw_session={token}"})
        assert {v.split("=", 1)[0] for v in r.headers.get_list("set-cookie")} == {"__Host-dw_session", "dw_session"}
        assert c.get("/api/me", headers={"Cookie": f"dw_session={token}"}).status_code == 401


# ---------------------------------------------------------------- the API trims (B-R4.2 contract) and the health strip's expectations (C-R2.7)
def test_pending_count_and_the_strip_says_how_often_each_source_runs(client, users, db):
    from app.auth import create_user
    login(client, "j@example.org", "journo-password-1")
    assert client.get("/api/admin/pending-count").status_code == 403
    client.post("/api/auth/logout")
    login(client, "admin@example.org", "admin-password-1")
    assert client.get("/api/admin/pending-count").json() == {"pending": 0}
    p = create_user(db, "p@example.org", "pending-password-1", "P")
    p.status, p.active = "pending", False
    db.commit()
    assert client.get("/api/admin/pending-count").json() == {"pending": 1}
    health = {h["key"]: h for h in client.get("/api/sources/health").json()}
    assert (health["rss"]["expected_hours"], health["rss"]["manual"], health["rss"]["stale_after_hours"]) == (1, False, 2)
    assert (health["gnews"]["expected_hours"], health["gnews"]["stale_after_hours"]) == (6, 12)
    # run by hand with no cadence: never stale, shown as "manual, last run ..."
    assert (health["gdelt_timeline"]["manual"], health["gdelt_timeline"]["expected_hours"], health["gdelt_timeline"]["stale"]) == (True, None, False)
    # the weekly search import is by hand too, but a missed week empties the search lens: stale after 10 days
    assert health["gtrends"]["manual"] is True and health["gtrends"]["stale_after_hours"] == 240 and health["gtrends"]["stale"] is True
    assert health["digest"]["stale_after_hours"] == 8 * 24 and health["digest"]["expected_hours"] == 7 * 24
    assert health["reach"]["expected_hours"] == 30 * 24 and health["reach"]["stale_after_hours"] == 35 * 24
    assert health["discover_feeds"]["expected_hours"] == 24 and health["backup"]["stale_after_hours"] == 30
    ar = {h["key"]: h for h in client.get("/api/sources/health", headers={"X-Lang": "ar"}).json()}
    assert ar["reach"]["label"] != health["reach"]["label"] and ar["discover_feeds"]["label"] != health["discover_feeds"]["label"]


def test_gap_detail_carries_thirty_articles_and_twenty_need_items_with_their_totals(client, users, db):
    from datetime import timedelta
    from app.api.gaps import GAP_ARTICLES, GAP_NEED_ITEMS
    from app.ingest import load_rules, store_article
    from app.models import Country, Item, ItemTheme, utcnow
    themes, regions = ids(db)
    c = db.scalar(select(Country))
    rules = load_rules(db, c.id)
    wk = date(2026, 10, 5)
    when = datetime(2026, 10, 7, 9)
    for i in range(GAP_ARTICLES + 5):
        store_article(db, c.id, rules, url=f"https://ex.ly/h{i}", title=f"Libya hospital shortage of medicines {i}",
                      published_at=when, source_key="rss")
    for i in range(GAP_NEED_ITEMS + 3):
        it = Item(country_id=c.id, kind="pageview", source_key="wikipedia", dedupe_key=f"pv:{i}", title=f"Health_in_Libya {i}",
                  published_at=when - timedelta(hours=i), value=100, extra={})
        db.add(it)
        db.flush()
        db.add(ItemTheme(item_id=it.id, theme_id=themes["health"], method="rule"))
    db.commit()
    login(client, "j@example.org", "journo-password-1")
    d = client.get("/api/gap", params={"theme_id": themes["health"], "region_id": regions["national"], "lens": "audience",
                                       "week": wk.isoformat()}).json()
    assert d["articles"]["total"] == GAP_ARTICLES + 5 and len(d["articles"]["items"]) == GAP_ARTICLES == 30
    assert d["need_items"]["total"] == GAP_NEED_ITEMS + 3 and len(d["need_items"]["items"]) == GAP_NEED_ITEMS == 20
    assert utcnow() > when
    # names only for the accounts the votes and claims refer to
    from app import auth
    admin, j = users
    assert auth.team_names(db, admin, only={j.id}) == {j.id: "Journo"}
    assert auth.team_names(db, admin, only=set()) == {} and auth.team_names(db, admin, only={None}) == {}
    assert set(auth.team_names(db, admin)) >= {admin.id, j.id}


def test_network_kinds_filter_what_is_sent_but_not_what_sizes_a_node(client, users, db):
    from app.models import Country, NetworkEdgeWeek, Outlet, Region, Theme
    c = db.scalar(select(Country))
    o1, o2 = db.scalars(select(Outlet).order_by(Outlet.id).limit(2)).all()
    r = db.scalar(select(Region).where(Region.level == "district"))
    t = db.scalar(select(Theme))
    wk = date(2026, 10, 5)
    db.add_all([
        NetworkEdgeWeek(country_id=c.id, kind="outlet_region", source_node=f"o:{o1.id}", target_node=f"r:{r.id}", theme_id=t.id, week_start=wk, weight=3),
        NetworkEdgeWeek(country_id=c.id, kind="outlet_theme", source_node=f"o:{o1.id}", target_node=f"t:{t.id}", theme_id=t.id, week_start=wk, weight=5),
        NetworkEdgeWeek(country_id=c.id, kind="outlet_outlet", source_node=f"o:{o1.id}", target_node=f"o:{o2.id}", weight=0.8),
        NetworkEdgeWeek(country_id=c.id, kind="syndication", source_node=f"o:{o1.id}", target_node=f"o:{o2.id}", weight=2)])
    db.commit()
    login(client, "j@example.org", "journo-password-1")
    full = client.get("/api/network", params={"week": wk.isoformat()}).json()
    assert {e["kind"] for e in full["edges"]} == {"outlet_region", "outlet_theme", "outlet_outlet", "syndication"}
    node = lambda d, key: next(n for n in d["nodes"] if n["id"] == key)  # noqa: E731
    assert node(full, f"o:{o1.id}")["articles"] == 5 and node(full, f"o:{o2.id}")["articles"] == 0
    only = client.get("/api/network", params={"week": wk.isoformat(), "kinds": "outlet_region"}).json()
    assert [e["kind"] for e in only["edges"]] == ["outlet_region"]
    assert node(only, f"o:{o1.id}")["articles"] == 5                       # the bubble size still counts the theme edges
    assert not any(n["id"] == f"o:{o2.id}" for n in only["nodes"])          # an outlet no sent edge touches is left out
    assert {n["type"] for n in only["nodes"]} == {"outlet", "region", "theme"}
    sim = client.get("/api/network", params={"week": wk.isoformat(), "kinds": "similarity,syndication"}).json()
    assert {e["kind"] for e in sim["edges"]} == {"outlet_outlet", "syndication"}
    assert client.get("/api/network", params={"kinds": "outlet_region", "min_weight": 4}).json()["edges"] == []
    assert client.get("/api/network", params={"kinds": "bogus"}).status_code == 400


def test_big_answers_are_gzipped_and_geo_files_are_cached_for_a_day(client, users):
    login(client, "j@example.org", "journo-password-1")
    r = client.get("/api/meta", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip" and r.json()["country"]["iso2"] == "LY"
    assert "content-encoding" not in client.get("/health", headers={"Accept-Encoding": "gzip"}).headers   # under 1 KB
    g = client.get("/geo/libya_districts.geojson")
    assert g.status_code == 200 and g.headers["cache-control"] == "public, max-age=86400"
    assert client.get("/api/meta").headers.get("cache-control") != "public, max-age=86400"
