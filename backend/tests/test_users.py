import pytest
from sqlalchemy import select

from app import throttle
from app.models import AuthSession, User
from tests.conftest import login


@pytest.fixture(autouse=True)
def _fresh_throttle():
    throttle.LOGIN.reset()
    yield
    throttle.LOGIN.reset()


def test_signup_approval_and_roles(client, users, db):
    r = client.post("/api/auth/signup", json={"email": "New@Example.org", "password": "long-password-1",
                                              "display_name": "New Person", "organisation": "Libya Desk", "note": "please"})
    assert r.status_code == 200
    # duplicate signup gives the same answer (no account probing)
    assert client.post("/api/auth/signup", json={"email": "new@example.org", "password": "long-password-2",
                                                  "display_name": "x"}).json()["ok"]
    r = client.post("/api/auth/login", json={"email": "new@example.org", "password": "long-password-1"})
    assert r.status_code == 403 and "waiting" in r.json()["detail"]
    login(client, "admin@example.org", "admin-password-1")
    pending = [u for u in client.get("/api/admin/users").json() if u["status"] == "pending"]
    assert len(pending) == 1 and pending[0]["organisation"] == "Libya Desk" and pending[0]["role"] == "viewer"
    uid = pending[0]["id"]
    r = client.patch(f"/api/admin/users/{uid}", json={"status": "active", "role": "viewer"})
    assert r.json()["status"] == "active" and r.json()["approved_by"] == "Admin"
    client.post("/api/auth/logout")
    login(client, "new@example.org", "long-password-1")
    # viewers are read-only
    assert client.get("/api/meta").status_code == 200
    r = client.post("/api/comments", json={"object_type": "gap", "object_key": "1:1", "body": "hello"})
    assert r.status_code == 403
    # feedback is open to every signed-in user
    assert client.post("/api/feedback", json={"page": "/", "kind": "question", "body": "How is the gap scored?"}).status_code == 200
    client.post("/api/auth/logout")
    login(client, "admin@example.org", "admin-password-1")
    assert client.patch(f"/api/admin/users/{uid}", json={"role": "journalist"}).json()["role"] == "journalist"
    fb = client.get("/api/admin/feedback").json()
    assert fb[0]["kind"] == "question" and fb[0]["user"] == "New Person"
    assert client.patch(f"/api/admin/feedback/{fb[0]['id']}", json={"reply": "See the method note."}).status_code == 200
    # disabling signs the user out and blocks login
    assert client.patch(f"/api/admin/users/{uid}", json={"status": "disabled"}).json()["status"] == "disabled"
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "new@example.org", "password": "long-password-1"}).status_code == 403


def test_admin_cannot_lock_themselves_out(client, users, db):
    login(client, "admin@example.org", "admin-password-1")
    me = client.get("/api/me").json()
    assert client.patch(f"/api/admin/users/{me['id']}", json={"role": "viewer"}).status_code == 400
    assert client.patch(f"/api/admin/users/{me['id']}", json={"status": "disabled"}).status_code == 400
    assert client.patch(f"/api/admin/users/{me['id']}", json={"role": "superuser"}).status_code == 400


# ---------------------------------------------------------------- C-R1.4: sign-in throttle
def _wrong(client, email="j@example.org", pw="not-the-password", **kw):
    return client.post("/api/auth/login", json={"email": email, "password": pw}, **kw)


def test_five_failures_hold_the_email_back_with_a_doubling_retry_after(client, users, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(throttle.LOGIN, "_clock", lambda: clock[0])
    assert [_wrong(client).status_code for _ in range(4)] == [401] * 4
    assert _wrong(client).status_code == 401           # the fifth failure places the first hold
    r = _wrong(client)
    assert r.status_code == 429 and r.headers["Retry-After"] == "60" and "1 min" in r.json()["detail"]
    r = _wrong(client, headers={"X-Lang": "ar"})
    assert r.status_code == 429 and "دقيقة" in r.json()["detail"]
    # the right password is held back too, so the hold cannot be probed away
    assert client.post("/api/auth/login", json={"email": "j@example.org", "password": "journo-password-1"}).status_code == 429
    clock[0] += 61
    r = _wrong(client)                                   # the sixth failure: the hold doubles
    assert r.status_code == 401
    r = _wrong(client)
    assert r.status_code == 429 and r.headers["Retry-After"] == "120" and "2 min" in r.json()["detail"]
    clock[0] += 121
    for hold in (240, 480):
        assert _wrong(client).status_code == 401
        assert _wrong(client).headers["Retry-After"] == str(hold)
        clock[0] += hold + 1
    # the first failures are now outside the 15-minute window, so the count starts again from the recent ones
    assert [_wrong(client).status_code for _ in range(2)] == [401, 401]
    r = _wrong(client)
    assert r.status_code == 429 and r.headers["Retry-After"] == "60"
    clock[0] += 61
    assert login(client, "j@example.org", "journo-password-1").status_code == 200   # success clears the count
    client.post("/api/auth/logout")
    assert [_wrong(client).status_code for _ in range(5)] == [401] * 5
    assert _wrong(client).status_code == 429
    # other emails are not held back by this one
    assert _wrong(client, email="admin@example.org").status_code == 401


def test_the_hold_doubles_per_failure_and_caps_at_fifteen_minutes():
    now = [0.0]
    t = throttle.Throttle(clock=lambda: now[0])
    assert [t.failed("x@example.org", "1.1.1.1") for _ in range(10)] == [0, 0, 0, 0, 60, 120, 240, 480, 900, 900]
    assert t.check("X@example.org") == 900 and t.check("y@example.org") == 0
    now[0] += 900
    assert t.check("x@example.org") == 0
    t.succeeded("x@example.org")
    assert t.failed("x@example.org") == 0


def test_unknown_emails_are_throttled_like_known_ones(client, users):
    assert [_wrong(client, email="nobody@example.org").status_code for _ in range(5)] == [401] * 5
    r = _wrong(client, email="Nobody@Example.org ")
    assert r.status_code == 429 and r.headers["Retry-After"] == "60"
    assert _wrong(client, email="someone-else@example.org").status_code == 401


def test_the_address_cap_is_soft_and_keyed_on_the_fly_header(client, users, monkeypatch):
    monkeypatch.setattr(throttle, "IP_FAILURES", 6)
    for i in range(5):
        assert _wrong(client, email=f"u{i}@example.org", headers={"Fly-Client-IP": "41.0.0.1"}).status_code == 401
    assert _wrong(client, email="u9@example.org", headers={"Fly-Client-IP": "41.0.0.1"}).status_code == 401   # the sixth
    r = _wrong(client, email="u7@example.org", headers={"Fly-Client-IP": "41.0.0.1"})
    assert r.status_code == 429 and r.headers["Retry-After"] == str(throttle.IP_HOLD)
    assert _wrong(client, email="u8@example.org", headers={"Fly-Client-IP": "41.0.0.2"}).status_code == 401   # another address
    assert throttle.ip_key("41.0.0.1") != throttle.ip_key("41.0.0.2") and "41.0.0.1" not in throttle.ip_key("41.0.0.1")


def test_signup_limiter_keys_on_the_real_client_address(client, db, monkeypatch):
    from app.api import account
    monkeypatch.setattr(account, "_SIGNUPS", {})
    body = {"email": "a@example.org", "password": "long-password-1", "display_name": "A"}
    for _ in range(5):
        assert client.post("/api/auth/signup", json=body, headers={"Fly-Client-IP": "41.0.0.1"}).status_code == 200
    assert client.post("/api/auth/signup", json=body, headers={"Fly-Client-IP": "41.0.0.1"}).status_code == 429
    assert client.post("/api/auth/signup", json=body, headers={"Fly-Client-IP": "41.0.0.9"}).status_code == 200


# ---------------------------------------------------------------- C-R1.5: sign out everywhere, password change
def test_logout_all_ends_every_session(client, users, db):
    from fastapi.testclient import TestClient
    from app.main import app
    login(client, "j@example.org", "journo-password-1")
    with TestClient(app) as other:
        login(other, "j@example.org", "journo-password-1")
        assert other.get("/api/me").status_code == 200
        assert db.scalar(select(AuthSession.user_id)) is not None
        r = client.post("/api/auth/logout-all")
        assert r.status_code == 200 and r.json()["ended"] == 2
        assert client.get("/api/me").status_code == 401 and other.get("/api/me").status_code == 401
    assert client.post("/api/auth/logout-all").status_code == 401


def test_password_change_ends_the_other_sessions_and_needs_the_current_one(client, users, db):
    from fastapi.testclient import TestClient
    from app.main import app
    login(client, "j@example.org", "journo-password-1")
    with TestClient(app) as other:
        login(other, "j@example.org", "journo-password-1")
        assert client.post("/api/me/password", json={"current": "wrong-password-1", "new": "new-password-123"}).status_code == 400
        assert client.post("/api/me/password", json={"current": "journo-password-1", "new": "short"}).status_code == 400
        assert other.get("/api/me").status_code == 200
        r = client.post("/api/me/password", json={"current": "journo-password-1", "new": "new-password-123"})
        assert r.status_code == 200 and r.json()["other_sessions_ended"] == 1
        assert client.get("/api/me").status_code == 200 and other.get("/api/me").status_code == 401
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "j@example.org", "password": "journo-password-1"}).status_code == 401
    assert login(client, "j@example.org", "new-password-123").status_code == 200
    # wrong current passwords count towards the sign-in throttle of the email
    for _ in range(5):
        client.post("/api/me/password", json={"current": "wrong-password-1", "new": "new-password-456"})
    assert client.post("/api/me/password", json={"current": "new-password-123", "new": "new-password-456"}).status_code == 429


def test_feedback_reply_visible_to_author(client, users, db):
    login(client, "j@example.org", "journo-password-1")
    client.post("/api/feedback", json={"page": "/timeline", "kind": "suggestion", "body": "Add a zoom brush"})
    client.post("/api/auth/logout")
    login(client, "admin@example.org", "admin-password-1")
    fid = client.get("/api/admin/feedback").json()[0]["id"]
    client.patch(f"/api/admin/feedback/{fid}", json={"status": "planned", "reply": "Good idea."})
    client.post("/api/auth/logout")
    login(client, "j@example.org", "journo-password-1")
    mine = client.get("/api/feedback/mine?page=/timeline").json()
    assert mine[0]["status"] == "planned" and mine[0]["reply"] == "Good idea."
