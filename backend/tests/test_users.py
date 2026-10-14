from sqlalchemy import select

from app.models import User
from tests.conftest import login


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
