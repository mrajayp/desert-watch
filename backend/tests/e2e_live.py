"""End-to-end test against a RUNNING server (not part of the unit suite).

    DW_E2E_BASE=http://127.0.0.1:8091 DW_E2E_ADMIN_EMAIL=... DW_E2E_ADMIN_PASSWORD=... \
        .venv/Scripts/python tests/e2e_live.py

Exercises every user-facing flow over HTTP with real cookies, including one live page fetch
for "add article". Creates a throwaway journalist (deleted at the end) and leaves an audit
trail of what it did in the output. Exit code = number of failed checks.
"""
import os
import secrets
import sys
import time

import httpx

BASE = os.environ.get("DW_E2E_BASE", "http://127.0.0.1:8091")
ADMIN = (os.environ["DW_E2E_ADMIN_EMAIL"], os.environ["DW_E2E_ADMIN_PASSWORD"])
LIVE_URL = os.environ.get("DW_E2E_LIVE_URL", "https://libyareview.com/")
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    return cond


def client():
    return httpx.Client(base_url=BASE, timeout=60, follow_redirects=False)


def main():
    a = client()
    # ---------------- health + static
    r = a.get("/health")
    check("health ok", r.status_code == 200 and r.json()["ok"], r.text[:200])
    check("SPA served", a.get("/").status_code == 200 and "<div id=\"root\">" in a.get("/").text)
    check("geo served", a.get("/geo/libya_districts.geojson").status_code == 200)
    check("api requires auth", a.get("/api/meta").status_code == 401)
    check("bad login rejected", a.post("/api/auth/login", json={"email": ADMIN[0], "password": "wrong-password"}).status_code == 401)

    # ---------------- admin login + invite
    r = a.post("/api/auth/login", json={"email": ADMIN[0], "password": ADMIN[1]})
    check("admin login", r.status_code == 200 and r.json()["role"] == "admin", r.text[:200])
    email = f"e2e-{secrets.token_hex(4)}@example.org"
    r = a.post("/api/admin/invites", json={"email": email, "role": "journalist"})
    token = r.json().get("invite_path", "").split("/")[-1]
    check("invite created", r.status_code == 200 and token)

    j = client()
    r = j.post("/api/auth/accept-invite", json={"token": token, "password": "e2e-password-123", "display_name": "E2E Journalist"})
    check("invite accepted", r.status_code == 200 and r.json()["role"] == "journalist", r.text[:200])
    check("invite single-use", client().post("/api/auth/accept-invite", json={"token": token, "password": "e2e-password-123", "display_name": "x"}).status_code == 400)
    check("journalist blocked from admin", j.get("/api/admin/users").status_code == 403)
    r = j.patch("/api/me", json={"ack_tracking_notice": True})
    check("tracking notice ack", r.status_code == 200 and r.json()["tracking_notice_ack"])

    # ---------------- reading the data
    meta = j.get("/api/meta").json()
    themes = {t["slug"]: t for t in meta["themes"]}
    regions = {r["slug"]: r for r in meta["regions"]}
    check("meta: 22 districts", sum(1 for r in meta["regions"] if r["level"] == "district") == 22)
    check("meta: gender themes present", sum(1 for t in meta["themes"] if t.get("group") == "gender") == 7)
    check("meta: weeks scored", len(meta["weeks"]) >= 12, str(len(meta["weeks"])))
    check("meta: events timeline", len(meta.get("events", [])) >= 10)
    lens = next(l["key"] for l in meta["lenses"] if l["available"])
    cells = j.get("/api/cells", params={"lens": lens}).json()["cells"]
    check("cells returned", len(cells) > 0, lens)
    scored = [c for c in cells if not c["insufficient"]]
    check("some cells scored", len(scored) > 0)
    check("insufficient cells have no gap", all(c["gap"] is None for c in cells if c["insufficient"]))
    nat = regions["national"]["id"]
    tid = scored[0]["theme_id"] if scored else themes["economy"]["id"]
    g = j.get("/api/gap", params={"theme_id": tid, "region_id": nat, "lens": lens}).json()
    check("gap detail has articles", g["articles"]["total"] > 0)
    check("gap articles are relevant + tagged", all(tid in a_["theme_ids"] for a_ in g["articles"]["items"][:50]))
    net = j.get("/api/network", params={"weeks": 4}).json()
    check("network has outlets + edges", any(n["type"] == "outlet" for n in net["nodes"]) and len(net["edges"]) > 0)
    w = sum(e["weight"] for e in net["edges"] if e["kind"] == "outlet_theme")
    check("network edge weights positive", w > 0)
    cl = j.get("/api/clusters").json()
    check("clusters named", len(cl["clusters"]) > 0 and all(c["name"] for c in cl["clusters"]))
    check("cluster shares sum to ~1", abs(sum(c["share"] for c in cl["clusters"]) - 1) < 0.02)
    per = j.get("/api/clusters/periods").json()
    check("cluster periods", len(per["periods"]) >= 1)
    mon = j.get("/api/coverage-monthly", params={"theme_id": themes["gender_violence"]["id"]}).json()
    check("gender monthly history spans years", len({m["month"][:4] for m in mon}) >= 3, str([m["month"] for m in mon][:3]))
    check("sources health", len(j.get("/api/sources/health").json()) >= 8)
    check("outlets list", len(j.get("/api/outlets").json()) > 10)
    check("trends", j.get("/api/cells/trends", params={"lens": lens}).status_code == 200)

    # ---------------- feedback flows
    wk = meta["latest_week"]
    r = j.post("/api/gap/vote", json={"theme_id": tid, "region_id": nat, "week": wk, "lens": lens, "vote": "real", "note": "e2e"})
    check("vote real", r.status_code == 200)
    r = j.post("/api/gap/vote", json={"theme_id": tid, "region_id": nat, "week": wk, "lens": lens, "vote": "covered"})
    check("covered vote needs link", r.status_code == 400)
    r = j.post("/api/items/preview", json={"url": LIVE_URL})
    check("live page metadata fetch", r.status_code == 200 and r.json().get("title"), r.text[:200])
    check("SSRF blocked", j.post("/api/items/preview", json={"url": "http://127.0.0.1:8091/health"}).status_code == 400)
    r = j.post("/api/gap/vote", json={"theme_id": tid, "region_id": nat, "week": wk, "lens": lens, "vote": "covered", "covered_url": LIVE_URL})
    covered_id = r.json().get("covered_item_id") if r.status_code == 200 else None
    check("covered vote adds coverage item", covered_id is not None, r.text[:200])
    item = g["articles"]["items"][0]
    r = j.post(f"/api/items/{item['id']}/correction", json={"region_id": regions["sabha"]["id"], "region_relevant": True})
    check("correction: add place", r.status_code == 200 and regions["sabha"]["id"] in r.json()["region_ids"])
    r = j.post(f"/api/items/{item['id']}/correction", json={"region_id": regions["sabha"]["id"], "region_relevant": False})
    check("correction: remove place", r.status_code == 200 and regions["sabha"]["id"] not in r.json()["region_ids"])
    r = j.post(f"/api/items/{item['id']}/assessment", json={"accuracy": 3, "depth": 2, "local_sourcing": 1, "note": "e2e"})
    check("assessment saved", r.status_code == 200 and j.get(f"/api/items/{item['id']}").json()["assessments"]["mine"]["depth"] == 2)
    key = f"{tid}:{nat}"
    c1 = j.post("/api/comments", json={"object_type": "gap", "object_key": key, "body": "e2e comment @Admin", "tag": "source_tip"}).json()
    c2 = j.post("/api/comments", json={"object_type": "gap", "object_key": key, "body": "e2e reply", "parent_id": c1["id"]})
    check("comment + reply", c2.status_code == 200 and c1["mentions"] == ["Admin"])
    r = j.post("/api/gap/claim", json={"theme_id": tid, "region_id": nat, "status": "working"})
    check("claim working", r.status_code == 200)
    r = j.post("/api/suggestions", json={"kind": "gap", "payload": {"theme_id": themes["gender_mobility_morality"]["id"], "region_id": regions["sabha"]["id"], "note": "e2e flag"}})
    check("gap suggestion", r.status_code == 200)

    # ---------------- outlets: propose (journalist) -> approve (admin), history kept
    outlets = j.get("/api/outlets").json()
    o = next(x for x in outlets if x["domain"] == "libyareview.com")
    bad = j.post(f"/api/outlets/{o['id']}/categories", json={"dimension": "reach", "value": "national", "confidence": "likely", "evidence_url": "nope"})
    check("category without evidence rejected", bad.status_code in (400, 422))
    r = j.post(f"/api/outlets/{o['id']}/categories", json={"dimension": "reach", "value": "national", "confidence": "likely", "evidence_url": "https://example.org/e2e-evidence"})
    check("journalist proposes category", r.status_code == 200 and r.json()["status"] == "proposed")
    pid = next(h["id"] for h in a.get(f"/api/outlets/{o['id']}/history").json() if h["status"] == "proposed")
    check("admin approves", a.post(f"/api/outlets/categories/{pid}/review", json={"approve": True}).status_code == 200)

    # ---------------- admin: theme preview, alerts, learning
    r = a.post("/api/themes/preview", json={"name_en": "Preview test", "en_terms": ["women candidates"], "ar_terms": ["المرشحات"], "exclude": []})
    check("theme preview", r.status_code == 200 and "matched" in r.json())
    alerts = a.get("/api/admin/alerts").json()
    check("alerts listed", len(alerts["alerts"]) >= 60)
    r = a.post("/api/admin/alerts", json={"lines": "district:ghat:en https://evil.example/feed"})
    check("alerts reject non-Google feed", r.status_code == 200 and r.json()["attached"] == 0)
    lrn = a.get("/api/admin/learning").json()
    check("learning page", "labels" in lrn and "rule_confirmation" in lrn)
    check("suggestions queue", a.get("/api/admin/suggestions").status_code == 200)

    # ---------------- behaviour log + opt-out + export + delete
    ev = [{"type": "impression", "object_type": "gap", "object_key": key, "context": {"position": 0}},
          {"type": "dwell", "object_type": "gap", "object_key": key, "context": {"seconds": 25}}]
    check("implicit events stored", j.post("/api/events", json={"session_id": "e2e", "events": ev}).json()["stored"] == 2)
    j.patch("/api/me", json={"tracking_opt_out": True})
    check("opt-out drops implicit", j.post("/api/events", json={"events": ev}).json()["stored"] == 0)
    exp = j.get("/api/me/export").json()
    check("export has my data", len(exp["votes"]) >= 1 and len(exp["comments"]) >= 2 and len(exp["events"]) >= 2)

    # ---------------- jobs
    check("run rss job", a.post("/api/admin/run/rss").status_code == 200)
    time.sleep(1)
    check("recompute job queued", a.post("/api/admin/run/recompute").status_code == 200)

    check("delete account", j.delete("/api/me").status_code == 200)
    check("deleted user locked out", j.get("/api/me").status_code == 401)
    check("logout", a.post("/api/auth/logout").status_code == 200 and a.get("/api/me").status_code == 401)

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return len(failed)


if __name__ == "__main__":
    sys.exit(main())
