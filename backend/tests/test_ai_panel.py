"""AI answers audit, the logged origins: the journalist panel (answers asked in the apps on the team's own
phones) and supervised browser sessions. The links are matched by the audit's own matcher; the three origins
(api, panel, browser) are never counted together; nobody but admins sees a full link, and nobody but the
author (and admins, as "a team member") sees who logged an entry; entries never touch the weekly cap or the
scored tables."""
import json
from datetime import timedelta

import pytest
import yaml
from sqlalchemy import create_engine, func, inspect, select, text

from app import settings
from app.ai_audit import runner
from app.api import ai_panel as P
from app.auth import create_user
from app.db import Base, init_db
from app.models import AiAnswer, AiRun, AiSource, CellWeek, Country, Item, ItemTheme, Outlet, utcnow
from tests.conftest import login

URL_MARK = "private-slug-zz"
PASTE = (f"Sources the app showed:\n"
         f"1. https://www.libyaobserver.ly/news/x?utm_source=chatgpt.com, and\n"
         f"2. (https://www.hrw.org/ar/news/2026/10/1)\n"
         f"3. https://unknown-site.ly/{URL_MARK}\n"
         f"4. https://www.facebook.com/some.private.person/posts/7\n"
         f"www.no-scheme.ly ftp://files.example.ly/a mailto:x@example.org\n"
         f"https://libyaobserver.ly/news/x   (the same link again)")


def config(**over) -> dict:
    cfg = yaml.safe_load((settings.CONFIG_DIR / "ai_audit.yaml").read_text(encoding="utf-8"))
    cfg.update(over)
    return cfg


@pytest.fixture()
def cfg(monkeypatch):
    state = {"cfg": config()}
    monkeypatch.setattr(runner, "load_config", lambda: state["cfg"])
    return state


@pytest.fixture()
def team(db, users):
    """admin, journalist, a second journalist, a viewer."""
    admin, j = users
    j2 = create_user(db, "j2@example.org", "journo-password-2", "Second Journo")
    v = create_user(db, "v@example.org", "viewer-password-1", "Viewer Person", "viewer")
    db.commit()
    return admin, j, j2, v


def libya(db) -> Country:
    return db.scalar(select(Country).where(Country.iso2 == "LY"))


def outlet(db, domain) -> Outlet:
    return db.scalar(select(Outlet).where(Outlet.domain == domain))


def entry(**over) -> dict:
    body = {"question_key": "security", "lang": "ar", "app": "chatgpt_app", "asked_in": "LY", "no_sources": False,
            "links": PASTE}
    body.update(over)
    return body


def as_j(client):
    login(client, "j@example.org", "journo-password-1")


def as_j2(client):
    login(client, "j2@example.org", "journo-password-2")


def as_admin(client):
    login(client, "admin@example.org", "admin-password-1")


def api_answer(db, week=None) -> AiRun:
    """A developer-API answer, written as the runner writes one (no provider call)."""
    week = week or runner.week_start_of(utcnow().date())
    run = AiRun(country_id=libya(db).id, provider="anthropic", week_start=week, status="ok", model="claude-haiku-5-5",
                cost_usd=0.03, usage={"searches": 2}, settings={}, price_basis={})
    db.add(run)
    db.flush()
    q = runner.questions(libya(db))[0]
    a = AiAnswer(run_id=run.id, question_key=q["key"], question_version=q["version"], lang="en", status="ok",
                 queries=["zz api query"], n_searched=2, n_cited=1, searches=2, cost_usd=0.03)
    db.add(a)
    db.flush()
    lo = outlet(db, "libyaobserver.ly")
    db.add_all([AiSource(answer_id=a.id, role="searched", rank=1, url="https://libyaobserver.ly/api-searched", domain="libyaobserver.ly",
                         outlet_id=lo.id, family_id=lo.id, match="exact", lang="en"),
                AiSource(answer_id=a.id, role="searched", rank=2, url="https://alwasat.ly/api-searched", domain="alwasat.ly",
                         outlet_id=outlet(db, "alwasat.ly").id, family_id=outlet(db, "alwasat.ly").id, match="exact", lang="ar"),
                AiSource(answer_id=a.id, role="cited", rank=1, url="https://libyaobserver.ly/api-cited", domain="libyaobserver.ly",
                         outlet_id=lo.id, family_id=lo.id, match="exact", lang="en", citations=1)])
    db.commit()
    return run


# ---------------------------------------------------------------- links in pasted text
def test_only_http_links_are_taken_from_the_text_each_once():
    urls = P.extract_urls(PASTE)
    assert urls == ["https://www.libyaobserver.ly/news/x?utm_source=chatgpt.com", "https://www.hrw.org/ar/news/2026/10/1",
                    f"https://unknown-site.ly/{URL_MARK}", "https://www.facebook.com/some.private.person/posts/7"]
    glued = P.extract_urls("https://a.ly/1,https://b.ly/2;https://c.ly/3\u060chttps://d.ly/4")
    assert glued == ["https://a.ly/1", "https://b.ly/2", "https://c.ly/3", "https://d.ly/4"]
    assert P.extract_urls("\u200fhttps://e.ly/x\u200e\u060c [title](https://f.ly/y) **https://g.ly/z**.") == [
        "https://e.ly/x", "https://f.ly/y", "https://g.ly/z"]
    assert P.extract_urls("see https://en.wikipedia.org/wiki/Libya_(disambiguation).") == [
        "https://en.wikipedia.org/wiki/Libya_(disambiguation)"]
    assert P.extract_urls("HTTPS://H.LY/a https://localhost/x http://. https://x") == ["HTTPS://H.LY/a"]
    # a Google redirect keeps its target inside one link (the matcher unwraps it)
    assert P.extract_urls("https://www.google.com/url?q=https://alwasat.ly/n/1") == ["https://www.google.com/url?q=https://alwasat.ly/n/1"]
    assert P.extract_urls(["https://a.ly/1", "https://a.ly/1?utm_campaign=x"]) == ["https://a.ly/1"]


# ---------------------------------------------------------------- the week
def test_the_week_lists_the_questions_both_languages_the_apps_and_only_my_entries(client, team, db, cfg):
    as_j(client)
    w = client.get("/api/ai-panel/week").json()
    assert w["week_start"] == runner.week_start_of(utcnow().date()).isoformat()
    assert len(w["questions"]) == 8 and set(w["questions"][0]) == {"key", "theme", "en", "ar"}
    assert w["questions"][0]["ar"].startswith("ما ") and w["questions"][0]["en"].startswith("What")
    assert [a["key"] for a in w["apps"]] == list(P.APPS) and w["apps"][2]["label"] == "Google AI Overview or AI Mode"
    assert (w["limit"], w["used"], w["mine"], w["can_log_browser"], w["can_log"]) == (40, 0, [], False, True)
    ar = client.get("/api/ai-panel/week", headers={"X-Lang": "ar"}).json()
    assert {a["key"]: a["label"] for a in ar["apps"]}["chatgpt_app"] == "تطبيق ChatGPT"
    r = client.post("/api/ai-panel/entries", json=entry()).json()
    as_j2(client)
    client.post("/api/ai-panel/entries", json=entry(app="gemini_app", lang="en"))
    as_j(client)
    w = client.get("/api/ai-panel/week").json()
    assert w["used"] == 1 and [m["id"] for m in w["mine"]] == [r["id"]]
    m = w["mine"][0]
    assert (m["question_key"], m["lang"], m["app"], m["asked_in"], m["no_sources"], m["origin"]) == (
        "security", "ar", "chatgpt_app", "LY", False, "panel")
    assert (m["links"], m["matched"], m["unknown"]) == (4, 2, 2) and m["created_at"]
    as_admin(client)
    assert client.get("/api/ai-panel/week").json()["can_log_browser"] is True


# ---------------------------------------------------------------- logging
def test_an_entry_keeps_only_the_links_matched_to_the_register(client, team, db, cfg):
    admin, j, j2, v = team
    as_j(client)
    r = client.post("/api/ai-panel/entries", json=entry())
    assert r.status_code == 200, r.text
    assert r.json() == {"id": r.json()["id"], "links": 4, "matched": 2, "unknown": 2}
    db.expire_all()
    run = db.scalar(select(AiRun).where(AiRun.origin == "panel"))
    assert (run.provider, run.model, run.cost_usd, run.week_start.weekday()) == ("chatgpt_app", None, 0.0, 0)
    a = db.get(AiAnswer, r.json()["id"])
    assert (a.origin, a.status, a.logged_by, a.asked_in, a.lang, a.queries, a.n_searched, a.n_cited, a.cost_usd) == (
        "panel", "ok", j.id, "LY", "ar", [], 0, 4, 0.0)
    assert a.answer_lang is None and a.answer_chars is None
    assert a.question_version == runner.questions(libya(db))[0]["version"]
    rows = db.scalars(select(AiSource).where(AiSource.answer_id == a.id).order_by(AiSource.rank)).all()
    assert {x.role for x in rows} == {"cited"} and [x.rank for x in rows] == [1, 2, 3, 4]
    by = {x.domain: x for x in rows}
    assert by["libyaobserver.ly"].outlet_id == outlet(db, "libyaobserver.ly").id
    assert by["libyaobserver.ly"].url == "https://libyaobserver.ly/news/x"       # tracking dropped
    assert (by["hrw.org/ar"].match, by["hrw.org/ar"].lang) == ("path", "ar")
    assert by["unknown-site.ly"].outlet_id is None and by["unknown-site.ly"].match == "unknown"
    assert by["facebook.com"].url == "https://facebook.com/" and by["facebook.com"].title is None   # platform only
    assert all(x.title is None and x.citations == 0 for x in rows)
    assert not db.scalar(select(func.count(AiSource.id)).where(AiSource.url.like("%some.private.person%")))
    # a second entry for the same app and week hangs off the same run; another app gets its own
    client.post("/api/ai-panel/entries", json=entry(lang="en"))
    client.post("/api/ai-panel/entries", json=entry(app="meta_ai", asked_in="other"))
    assert db.scalar(select(func.count(AiRun.id)).where(AiRun.origin == "panel")) == 2


def test_no_sources_shown_means_zero_links(client, team, db, cfg):
    as_j(client)
    r = client.post("/api/ai-panel/entries", json=entry(no_sources=True)).json()
    assert (r["links"], r["matched"], r["unknown"]) == (0, 0, 0)
    a = db.get(AiAnswer, r["id"])
    assert a.status == "no_sources" and a.n_cited == 0
    assert not db.scalar(select(func.count(AiSource.id)).where(AiSource.answer_id == a.id))
    r = client.post("/api/ai-panel/entries", json=entry(no_sources=True, links="")).json()
    assert r["links"] == 0


def test_bad_entries_are_refused_in_the_interface_language(client, team, db, cfg):
    as_j(client)
    post = lambda **kw: client.post("/api/ai-panel/entries", json=entry(**kw))  # noqa: E731
    assert post(links="no links here, www.alwasat.ly only").status_code == 400
    assert post(question_key="weather").status_code == 400
    assert post(app="myspace").status_code == 400
    assert post(lang="fr").status_code == 400
    assert post(asked_in=None).status_code == 400
    assert post(asked_in="London").status_code == 400          # London is for browser sessions
    assert post(origin="api").status_code == 400               # API answers come only from the runner
    many = "\n".join(f"https://site{i}.ly/a" for i in range(31))
    assert post(links=many).status_code == 400
    assert post(links="\n".join(f"https://site{i}.ly/a" for i in range(30))).status_code == 200
    assert post(links="https://a.ly/" + "x" * 41000).status_code == 400
    r = client.post("/api/ai-panel/entries", json=entry(links="nothing"), headers={"X-Lang": "ar"})
    assert r.status_code == 400 and r.json()["detail"].startswith("يُرجى لصق رابط")
    r = client.post("/api/ai-panel/entries", json=entry(links=many), headers={"X-Lang": "ar"})
    assert r.json()["detail"] == "الحد الأقصى 30 رابطًا لكل إدخال."
    login(client, "v@example.org", "viewer-password-1")
    assert post().status_code == 403
    client.post("/api/auth/logout")
    assert post().status_code == 401
    assert db.scalar(select(func.count(AiAnswer.id))) == 1


def test_forty_entries_a_week_per_person(client, team, db, cfg):
    admin, j, j2, v = team
    m = P.Matcher(db)
    for i in range(P.WEEKLY_LIMIT - 1):
        P.log_entry(db, libya(db), user_id=j.id, is_admin=False, origin="panel", question_key="security", lang="ar",
                    app="chatgpt_app", asked_in="LY", no_sources=True, links="", matcher=m)
    as_j(client)
    assert client.post("/api/ai-panel/entries", json=entry()).status_code == 200
    r = client.post("/api/ai-panel/entries", json=entry())
    assert r.status_code == 429 and "40" in r.json()["detail"]
    assert client.get("/api/ai-panel/week").json()["used"] == 40
    # last week's entries do not count, nor do another person's
    old = P.log_entry(db, libya(db), user_id=j2.id, is_admin=False, origin="panel", question_key="security", lang="ar",
                      app="chatgpt_app", asked_in="LY", no_sources=True, links="", today=utcnow().date() - timedelta(days=7))
    assert db.get(AiRun, db.get(AiAnswer, old["id"]).run_id).week_start < runner.week_start_of(utcnow().date())
    as_j2(client)
    assert client.post("/api/ai-panel/entries", json=entry()).status_code == 200
    # deleting an entry frees its place
    as_j(client)
    mine = client.get("/api/ai-panel/week").json()["mine"]
    assert client.delete(f"/api/ai-panel/entries/{mine[0]['id']}").status_code == 200
    assert client.post("/api/ai-panel/entries", json=entry()).status_code == 200


def test_only_admins_log_a_browser_session_and_it_is_asked_from_london(client, team, db, cfg):
    as_j(client)
    r = client.post("/api/ai-panel/entries", json=entry(origin="browser"))
    assert r.status_code == 403
    assert client.post("/api/ai-panel/entries", json=entry(origin="browser"), headers={"X-Lang": "ar"}).json()["detail"] == \
        "تسجيل جلسات المتصفح متاح للمشرفين فقط."
    as_admin(client)
    r = client.post("/api/ai-panel/entries", json=entry(origin="browser", asked_in="LY", app="claude_app"))
    assert r.status_code == 200
    a = db.get(AiAnswer, r.json()["id"])
    run = db.get(AiRun, a.run_id)
    assert (a.origin, a.asked_in, run.origin, run.provider) == ("browser", "London", "browser", "claude_app")
    # the same app's panel entry is a different run
    r = client.post("/api/ai-panel/entries", json=entry(app="claude_app"))
    assert db.get(AiAnswer, r.json()["id"]).run_id != run.id


def test_only_the_author_or_an_admin_deletes_an_entry(client, team, db, cfg):
    as_j(client)
    mine = client.post("/api/ai-panel/entries", json=entry()).json()["id"]
    as_j2(client)
    theirs = client.post("/api/ai-panel/entries", json=entry(app="gemini_app")).json()["id"]
    assert client.delete(f"/api/ai-panel/entries/{mine}").status_code == 403
    login(client, "v@example.org", "viewer-password-1")
    assert client.delete(f"/api/ai-panel/entries/{mine}").status_code == 403
    as_j(client)
    assert client.delete(f"/api/ai-panel/entries/{mine}").status_code == 200
    assert db.get(AiAnswer, mine) is None
    assert not db.scalar(select(func.count(AiSource.id)).where(AiSource.answer_id == mine))
    assert db.scalar(select(func.count(AiRun.id)).where(AiRun.provider == "chatgpt_app")) == 0   # the empty run went too
    assert client.delete(f"/api/ai-panel/entries/{mine}").status_code == 404
    as_admin(client)
    assert client.delete(f"/api/ai-panel/entries/{theirs}").status_code == 200
    # a developer-API answer is not an entry
    api_id = db.scalar(select(AiAnswer.id).where(AiAnswer.run_id == api_answer(db).id))
    assert client.delete(f"/api/ai-panel/entries/{api_id}").status_code == 404
    assert db.get(AiAnswer, api_id) is not None


# ---------------------------------------------------------------- the summary: one origin at a time
def _three_origins(client, db):
    api_answer(db)
    as_j(client)
    client.post("/api/ai-panel/entries", json=entry())                                       # LO + HRW matched
    client.post("/api/ai-panel/entries", json=entry(app="gemini_app", lang="en", asked_in="other",
                                                    links="https://www.libyaobserver.ly/news/y"))
    client.post("/api/ai-panel/entries", json=entry(app="gemini_app", no_sources=True))
    as_admin(client)
    client.post("/api/ai-panel/entries", json=entry(origin="browser", app="chatgpt_app",
                                                    links="https://alwasat.ly/news/1 https://alwasat.ly/news/2"))


def test_the_summary_never_mixes_the_three_origins(client, team, db, cfg):
    _three_origins(client, db)
    as_admin(client)
    api = client.get("/api/ai-audit/summary").json()
    assert api["origin"] == "api" and api["n_answers"] == 1 and api["asked_in"] is None
    assert not {p["key"] for p in api["providers"]} & set(P.APPS)
    anth = next(p for p in api["providers"] if p["key"] == "anthropic")
    assert anth["answers"] == 1 and anth["searched_per_answer"]["median"] == 2
    assert {t["domain"]: t["cited"] for t in api["top_outlets"]} == {"libyaobserver.ly": 1}
    assert "status" in api and api["status"]["anthropic"] == "ok"

    panel = client.get("/api/ai-audit/summary", params={"origin": "panel"}).json()
    assert panel["origin"] == "panel" and panel["n_answers"] == 3 and panel["status"] == {}
    assert panel["asked_in"] == {"LY": 2, "other": 1, "London": 0}
    by = {p["key"]: p for p in panel["providers"]}
    assert set(by) == {"chatgpt_app", "gemini_app"}          # apps with no entries are left out
    g = by["gemini_app"]
    assert (g["label"], g["answers"], g["no_sources"], g["searched_per_answer"], g["query_lang"]) == ("Gemini", 2, 1, None, None)
    assert g["cited_per_answer"] == {"median": 0.5, "min": 0, "max": 1} and g["asked_in"] == {"LY": 1, "other": 1, "London": 0}
    assert by["chatgpt_app"]["cited_scope"]["unregistered"] == 2 and by["chatgpt_app"]["cited_lang"]["ar"] >= 1
    top = {t["domain"]: t for t in panel["top_outlets"]}
    assert top["libyaobserver.ly"]["cited"] == 2 and top["libyaobserver.ly"]["searched"] is None
    assert top["libyaobserver.ly"]["by_provider"] == {**{k: 0 for k in P.APPS}, "chatgpt_app": 1, "gemini_app": 1}
    assert "alwasat.ly" not in top                                           # the browser session's links
    assert all(n["appeared_in_results"] is None for n in panel["never_cited"])

    browser = client.get("/api/ai-audit/summary", params={"origin": "browser"}).json()
    assert browser["n_answers"] == 1 and browser["asked_in"] == {"LY": 0, "other": 0, "London": 1}
    assert {t["domain"]: t["cited"] for t in browser["top_outlets"]} == {"alwasat.ly": 2}
    assert [p["key"] for p in browser["providers"]] == ["chatgpt_app"]

    one = client.get("/api/ai-audit/summary", params={"origin": "panel", "provider": "gemini_app", "lang": "en"}).json()
    assert one["n_answers"] == 1
    assert client.get("/api/ai-audit/summary", params={"origin": "panel", "provider": "anthropic"}).status_code == 400
    assert client.get("/api/ai-audit/summary", params={"provider": "gemini_app"}).status_code == 400
    assert client.get("/api/ai-audit/summary", params={"origin": "phones"}).status_code == 400
    # the outlet panel's line counts developer-API citations only
    assert client.get(f"/api/outlets/{outlet(db, 'libyaobserver.ly').id}").json()["ai_cited_4w"] == 1
    assert client.get(f"/api/outlets/{outlet(db, 'alwasat.ly').id}").json()["ai_cited_4w"] == 0


def test_entries_never_touch_the_cap_or_the_scored_tables(client, team, db, cfg):
    counts = lambda: [db.scalar(select(func.count()).select_from(t)) for t in (Item, ItemTheme, CellWeek, Outlet)]  # noqa: E731
    before = counts()
    week = runner.week_start_of(utcnow().date())
    _three_origins(client, db)
    db.expire_all()
    assert counts() == before
    assert runner.spent_this_week(db, week) == pytest.approx(0.03)          # the API answer only
    assert {r.cost_usd for r in db.scalars(select(AiRun).where(AiRun.origin != "api"))} == {0.0}
    # the runner's one-run-a-week check never sees an app run as an assistant's run
    assert runner._week_runs(db, libya(db).id, week, "anthropic")[0].origin == "api"
    assert all(r.provider in P.APPS for r in db.scalars(select(AiRun).where(AiRun.origin.in_(P.LOGGED))))
    # even a logged run under an assistant's key would not block that assistant's weekly run
    db.add(AiRun(country_id=libya(db).id, provider="openai", origin="panel", week_start=week, status="ok", cost_usd=0.0))
    db.commit()
    assert runner._week_runs(db, libya(db).id, week, "openai") == []
    db.execute(text("DELETE FROM ai_run WHERE provider = 'openai' AND origin = 'panel'"))
    db.commit()
    as_admin(client)
    runs = client.get("/api/admin/ai-audit/runs").json()
    assert runs["week_cost_usd"] == pytest.approx(0.03)
    by = {(r["origin"], r["provider"]): r for r in runs["runs"]}
    assert set(by) == {("api", "anthropic"), ("panel", "chatgpt_app"), ("panel", "gemini_app"), ("browser", "chatgpt_app")}
    assert by[("panel", "gemini_app")]["answers"] == 2 and by[("panel", "gemini_app")]["no_sources"] == 1
    assert by[("panel", "gemini_app")]["label"] == "Gemini" and by[("panel", "gemini_app")]["cost_usd"] == 0
    only = client.get("/api/admin/ai-audit/runs", params={"origin": "browser"}).json()["runs"]
    assert [(r["origin"], r["provider"]) for r in only] == [("browser", "chatgpt_app")]
    assert client.get("/api/admin/ai-audit/runs", params={"origin": "x"}).status_code == 400


# ---------------------------------------------------------------- who sees what
def test_non_admins_never_see_links_titles_or_who_logged_what(client, team, db, cfg):
    _three_origins(client, db)
    cfg["cfg"] = config(visible_to="team")
    as_j2(client)
    seen = [client.get("/api/ai-audit/summary", params={"origin": o, "weeks": w}).text
            for o in ("api", "panel", "browser") for w in (4, 12)]
    week = client.get("/api/ai-panel/week").json()
    assert week["mine"] == [] and week["used"] == 0               # another person's entries are not listed
    seen.append(json.dumps(week, ensure_ascii=False))
    panel_run = db.scalar(select(AiRun.id).where(AiRun.origin == "panel", AiRun.provider == "chatgpt_app"))
    for path in ("/api/admin/ai-audit/runs", f"/api/admin/ai-audit/answers?run_id={panel_run}",
                 "/api/admin/ai-audit/unknown-domains?origin=panel"):
        r = client.get(path)
        assert r.status_code == 403
        seen.append(r.text)
    blob = "\n".join(seen)
    for mark in (URL_MARK, "/news/x", "/news/y", "hrw.org/ar/news", "alwasat.ly/news", "api-cited", "zz api query",
                 "Journo", "j@example.org", "logged_by", "some.private.person"):
        assert mark not in blob, mark
    # the author sees counts of their own entries, never someone else's
    as_j(client)
    mine = client.get("/api/ai-panel/week").json()["mine"]
    assert len(mine) == 3 and all(isinstance(m["links"], int) for m in mine)


def test_admins_see_the_links_of_an_entry_but_not_who_logged_it(client, team, db, cfg):
    admin, j, j2, v = team
    _three_origins(client, db)
    as_admin(client)
    panel_run = db.scalar(select(AiRun.id).where(AiRun.origin == "panel", AiRun.provider == "chatgpt_app"))
    r = client.get("/api/admin/ai-audit/answers", params={"run_id": panel_run})
    rows = r.json()
    assert len(rows) == 1
    a = rows[0]
    assert (a["origin"], a["asked_in"], a["status"], a["queries"], a["searched"]) == ("panel", "LY", "ok", [], [])
    assert a["author"] == "A team member" and a["mine"] is False and "logged_by" not in a and a["created_at"]
    assert {c["domain"] for c in a["cited"]} == {"libyaobserver.ly", "hrw.org/ar", "unknown-site.ly", "facebook.com"}
    assert any(URL_MARK in c["url"] for c in a["cited"])
    assert "Journo" not in r.text and "j@example.org" not in r.text
    ar = client.get("/api/admin/ai-audit/answers", params={"run_id": panel_run}, headers={"X-Lang": "ar"}).json()
    assert ar[0]["author"] == "أحد أعضاء الفريق"
    browser_run = db.scalar(select(AiRun.id).where(AiRun.origin == "browser"))
    b = client.get("/api/admin/ai-audit/answers", params={"run_id": browser_run}).json()[0]
    assert b["mine"] is True and b["asked_in"] == "London"
    api_run = db.scalar(select(AiRun.id).where(AiRun.origin == "api"))
    x = client.get("/api/admin/ai-audit/answers", params={"run_id": api_run}).json()[0]
    assert (x["origin"], x["author"], x["mine"]) == ("api", None, False) and x["queries"] == ["zz api query"]
    # one origin at a time here too: the developer-API list by default, the panel's on request
    assert client.get("/api/admin/ai-audit/unknown-domains").json() == []
    unknown = {u["domain"]: u for u in client.get("/api/admin/ai-audit/unknown-domains", params={"origin": "panel"}).json()}
    assert unknown["unknown-site.ly"]["cited"] == 1 and unknown["unknown-site.ly"]["ly"] is True
    assert client.get("/api/admin/ai-audit/unknown-domains", params={"origin": "browser"}).json() == []
    assert client.get("/api/admin/ai-audit/unknown-domains", params={"origin": "all"}).status_code == 400


# ---------------------------------------------------------------- the person's own data
def test_delete_me_keeps_the_entries_without_the_person_and_export_lists_them(client, team, db, cfg):
    admin, j, j2, v = team
    as_j(client)
    client.post("/api/ai-panel/entries", json=entry())
    client.post("/api/ai-panel/entries", json=entry(app="meta_ai", lang="en", no_sources=True, asked_in="other"))
    exp = client.get("/api/me/export").json()["ai_answer_entries"]
    assert len(exp) == 2
    e = exp[0]
    assert (e["question_key"], e["lang"], e["app"], e["asked_in"], e["origin"]) == ("security", "ar", "chatgpt_app", "LY", "panel")
    assert e["question"].startswith("ما ") and "https://libyaobserver.ly/news/x" in e["links"] and len(e["links"]) == 4
    assert exp[1]["links"] == [] and exp[1]["no_sources"] is True and exp[1]["question"].startswith("What")
    as_j2(client)
    assert client.get("/api/me/export").json()["ai_answer_entries"] == []
    as_j(client)
    assert client.delete("/api/me").json()["ok"]
    db.expire_all()
    assert db.scalar(select(func.count(AiAnswer.id)).where(AiAnswer.logged_by == j.id)) == 0
    assert db.scalar(select(func.count(AiAnswer.id)).where(AiAnswer.origin == "panel")) == 2   # the evidence stays


# ---------------------------------------------------------------- CLI import (supervised browser session)
def test_cli_import_of_a_browser_session(db, team, tmp_path, capsys):
    admin, j, j2, v = team
    items = [{"question_key": "security", "lang": "ar", "app": "chatgpt_app",
              "links": ["https://www.libyaobserver.ly/news/1", "https://unknown-site.ly/z"]},
             {"question_key": "economy", "lang": "en", "app": "google_ai", "links": "", "no_sources": True}]
    res = P.import_entries(db, items, origin="browser", dry_run=True)
    assert (res["entries"], res["links"], res["matched"], res["unknown"], res["stored"]) == (2, 2, 1, 1, 0)
    assert db.scalar(select(func.count(AiAnswer.id))) == 0
    bad = P.import_entries(db, items + [{"question_key": "nope", "lang": "ar", "app": "chatgpt_app", "links": "https://a.ly"}])
    assert bad["stored"] == 0 and bad["errors"] == ["entry 3: Unknown question"]
    assert db.scalar(select(func.count(AiAnswer.id))) == 0         # one bad entry stores none
    path = tmp_path / "session.json"
    path.write_text(json.dumps(items), encoding="utf-8")
    from app.cli import main
    assert main(["ai-panel-import", str(path), "--origin", "browser", "--by", "admin@example.org"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert (out["stored"], out["links"], out["matched"]) == (2, 2, 1)
    db.expire_all()
    rows = db.scalars(select(AiAnswer).order_by(AiAnswer.id)).all()
    assert [(a.origin, a.asked_in, a.status, a.logged_by) for a in rows] == [
        ("browser", "London", "ok", admin.id), ("browser", "London", "no_sources", admin.id)]
    assert {db.get(AiRun, a.run_id).provider for a in rows} == {"chatgpt_app", "google_ai"}
    # a panel import needs asked_in; an unknown account stores nothing
    assert P.import_entries(db, items, origin="panel")["errors"][0].startswith("entry 1: Say where")
    assert P.import_entries(db, items, by="nobody@example.org")["errors"] == ["no active account nobody@example.org"]


# ---------------------------------------------------------------- start-up on an existing database
def test_existing_tables_get_the_new_columns_at_start_up(tmp_path):
    eng = create_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    with eng.begin() as conn:
        conn.execute(text('CREATE TABLE ai_run (id INTEGER PRIMARY KEY, country_id INTEGER, provider VARCHAR(20), '
                          'week_start DATE, status VARCHAR(14))'))
        conn.execute(text("CREATE TABLE ai_answer (id INTEGER PRIMARY KEY, run_id INTEGER, status VARCHAR(14))"))
        conn.execute(text("INSERT INTO ai_run (id, provider, status) VALUES (1, 'anthropic', 'ok')"))
        conn.execute(text("INSERT INTO ai_answer (id, run_id, status) VALUES (1, 1, 'ok')"))
    init_db(bind=eng)
    insp = inspect(eng)
    assert "origin" in {c["name"] for c in insp.get_columns("ai_run")}
    assert {"origin", "logged_by", "asked_in"} <= {c["name"] for c in insp.get_columns("ai_answer")}
    with eng.connect() as conn:
        assert conn.execute(text("SELECT origin FROM ai_run")).scalar() == "api"
        assert conn.execute(text("SELECT origin, logged_by, asked_in FROM ai_answer")).one() == ("api", None, None)
    eng.dispose()
    assert Base.metadata.tables["ai_run"].c.origin.server_default.arg == "api"
