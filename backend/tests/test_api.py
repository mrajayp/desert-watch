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
