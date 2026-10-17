"""Step-1 privacy fixes from docs/research/female_journalists_tools.md (2026-10-17)."""
from datetime import date, timedelta

from sqlalchemy import select, text

from app import auth
from app.models import (AuthSession, Event, Feedback, GapClaim, GapVote, Item, KeyEvent, Label, Outlet, OutletCategory,
                        Suggestion, User, utcnow)
from tests.conftest import ids, login


def _second_journalist(db):
    u = auth.create_user(db, "k@example.org", "other-password-1", "Other")
    db.commit()
    return u


def test_only_author_or_admin_resolves_a_comment(client, users, db):
    _second_journalist(db)
    login(client, "j@example.org", "journo-password-1")
    cid = client.post("/api/comments", json={"object_type": "gap", "object_key": "1:1", "body": "tip"}).json()["id"]
    login(client, "k@example.org", "other-password-1")
    assert client.patch(f"/api/comments/{cid}", json={"resolved": True}).status_code == 403
    login(client, "admin@example.org", "admin-password-1")
    assert client.patch(f"/api/comments/{cid}", json={"resolved": True}).json()["resolved"] is True
    login(client, "j@example.org", "journo-password-1")
    assert client.patch(f"/api/comments/{cid}", json={"resolved": False}).json()["resolved"] is False


def test_safety_comments_reach_only_the_author_and_admins(client, users, db):
    _second_journalist(db)
    themes, regions = ids(db)
    key = f"{themes['economy']}:{regions['national']}" if "national" in regions else "1:1"
    login(client, "j@example.org", "journo-password-1")
    sid = client.post("/api/comments", json={"object_type": "gap", "object_key": key, "body": "I was threatened", "tag": "safety"}).json()["id"]
    client.post("/api/comments", json={"object_type": "gap", "object_key": key, "body": "public note"})
    ev = db.scalars(select(Event).where(Event.type == "comment")).all()
    assert sum("tag" not in (e.context or {}) for e in ev) == 1          # the safety comment's event says nothing about it
    assert not any((e.context or {}).get("tag") == "safety" for e in ev)
    # another journalist sees only the public note, cannot reply to the safety comment, and the count skips it
    login(client, "k@example.org", "other-password-1")
    bodies = [c["body"] for c in client.get("/api/comments", params={"object_type": "gap", "object_key": key}).json()]
    assert bodies == ["public note"]
    assert client.post("/api/comments", json={"object_type": "gap", "object_key": key, "body": "x", "parent_id": sid}).status_code == 400
    # an admin sees it and replies; the author sees the reply, the other journalist does not
    login(client, "admin@example.org", "admin-password-1")
    assert len(client.get("/api/comments", params={"object_type": "gap", "object_key": key}).json()) == 2
    client.post("/api/comments", json={"object_type": "gap", "object_key": key, "body": "call me", "parent_id": sid})
    login(client, "j@example.org", "journo-password-1")
    assert {c["body"] for c in client.get("/api/comments", params={"object_type": "gap", "object_key": key}).json()} == \
        {"I was threatened", "public note", "call me"}
    login(client, "k@example.org", "other-password-1")
    assert [c["body"] for c in client.get("/api/comments", params={"object_type": "gap", "object_key": key}).json()] == ["public note"]
    from app.api.gaps import _feedback_summary
    _, counts, _ = _feedback_summary(db)
    assert counts[key] == 1


def test_key_events_show_the_team_not_the_person(client, users, db):
    themes, _ = ids(db)
    login(client, "j@example.org", "journo-password-1")
    client.post("/api/key-events", json={"day": "2026-10-01", "label": "Fuel strike", "source_url": "https://ex.org/s"})
    ev = [e for e in client.get("/api/timeline").json()["events"] if e["origin"] == "user"]
    assert ev and ev[0]["mine"] is True and "added_by" not in ev[0]
    login(client, "admin@example.org", "admin-password-1")
    ev = [e for e in client.get("/api/timeline").json()["events"] if e["origin"] == "user"]
    assert ev[0]["mine"] is False


def test_delete_me_removes_the_person_from_everything(client, users, db):
    admin, j = users
    themes, regions = ids(db)
    tid, rid = themes["economy"], next(iter(regions.values()))
    login(client, "j@example.org", "journo-password-1")
    client.post("/api/auth/login", json={"email": "j@example.org", "password": "journo-password-1"})  # a second session
    old_pseudo = db.get(User, j.id).pseudo_id
    db.add_all([GapVote(user_id=j.id, theme_id=tid, region_id=rid, week_start=date(2026, 10, 5), lens="audience", vote="real", note="my source in Sabha"),
                GapClaim(user_id=j.id, theme_id=tid, region_id=rid, status="working"),
                Suggestion(user_id=j.id, kind="source", payload={"url": "https://ex.org", "note": "my cousin runs it"}),
                Feedback(user_id=j.id, page="/", kind="question", body="who sees my votes?"),
                KeyEvent(country_id=1, day=date(2026, 10, 1), label="x", source_url="https://ex.org", origin="user", added_by=j.id),
                Label(source_ref="t:1", label_type="theme_relevance", object_type="item", object_key="1", value={}, pseudo_id=old_pseudo, origin="explicit")])
    outlet = db.scalar(select(Outlet).limit(1))
    db.add(OutletCategory(outlet_id=outlet.id, dimension="type", value="private", confidence="likely", evidence_url="https://ex.org", set_by=j.id))
    db.add(Item(country_id=outlet.country_id, kind="suggestion", source_key="user", dedupe_key="s:1", title="my private note",
                published_at=utcnow(), added_by=j.id))
    db.commit()
    exp = client.get("/api/me/export").json()
    assert exp["feedback"] and exp["key_events"] and exp["outlet_labels"] and exp["added_items"] and "organisation" in exp["user"]
    assert client.delete("/api/me").json()["ok"]
    db.expire_all()
    u = db.get(User, j.id)
    assert u.pseudo_id != old_pseudo and not u.active and u.organisation is None and u.email.startswith("deleted-")
    assert db.scalar(select(GapVote.note).where(GapVote.user_id == j.id)) is None
    assert not db.scalars(select(GapClaim).where(GapClaim.user_id == j.id)).all()
    sug = db.scalar(select(Suggestion).where(Suggestion.kind == "source"))
    assert sug.user_id is None and "note" not in sug.payload and sug.payload["url"] == "https://ex.org"
    fb = db.scalar(select(Feedback).where(Feedback.page == "/"))
    assert fb.user_id is None and fb.body == ""
    assert db.scalar(select(KeyEvent.added_by).where(KeyEvent.label == "x")) is None
    assert db.scalar(select(OutletCategory.set_by).where(OutletCategory.evidence_url == "https://ex.org")) is None
    it = db.scalar(select(Item).where(Item.dedupe_key == "s:1"))
    assert it.added_by is None and it.title == "Gap flagged"
    assert db.scalar(select(Label.pseudo_id).where(Label.source_ref == "t:1")) is None
    assert not db.scalars(select(AuthSession).where(AuthSession.user_id == j.id)).all()


def test_nightly_purges_expired_sessions_and_old_rejected_applications(db):
    from app.learning import purge_account_leftovers
    u = auth.create_user(db, "r@example.org", "rejected-password-1", "R", role="viewer")
    u.status, u.organisation, u.signup_note = "rejected", "Some outlet", "please let me in"
    u.created_at = utcnow() - timedelta(days=40)
    fresh = auth.create_user(db, "f@example.org", "fresh-password-1", "F", role="viewer")
    fresh.status, fresh.organisation = "rejected", "Kept for now"
    db.add(AuthSession(token_hash="old", user_id=fresh.id, expires_at=utcnow() - timedelta(days=1)))
    db.add(AuthSession(token_hash="live", user_id=fresh.id, expires_at=utcnow() + timedelta(days=1)))
    db.commit()
    assert purge_account_leftovers(db) == {"sessions": 1, "rejected_blanked": 1}
    db.expire_all()
    assert db.get(User, u.id).organisation is None and db.get(User, fresh.id).organisation == "Kept for now"
    assert db.get(AuthSession, "live") and not db.get(AuthSession, "old")


def test_deleted_rows_are_overwritten_and_the_digest_sees_no_headlines(db):
    assert db.execute(text("PRAGMA secure_delete")).scalar() == 1
    from app import digest
    assert "headline" not in digest.SYSTEM.lower()
    import inspect
    assert "recent_gender_headlines" not in inspect.getsource(digest)
