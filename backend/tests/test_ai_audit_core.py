"""AI answers audit, core: the read-only matcher, the weekly runner (cap, order, keys, one run a week,
nothing stored that should not be, unscored) and the API (who sees what)."""
import json
import sys
import types
from datetime import timedelta
from types import SimpleNamespace

import pytest
import yaml
from sqlalchemy import func, select, text

from app import settings
from app.ai_audit import matcher as M
from app.ai_audit import runner
from app.db import Base
from app.models import AiAnswer, AiRun, AiSource, CellWeek, Country, Item, ItemTheme, Outlet, SourceRun, utcnow
from tests.conftest import login

PRICES = {
    "as_of": "2026-10-18",
    "anthropic": {"tool": "web_search_20250305", "search_per_1000_usd": 10.0,
                  "models": [{"id": "claude-haiku-5-5", "input_per_mtok": 0.10, "output_per_mtok": 0.50}]},
    "openai": {"tool": "web_search", "search_per_1000_usd": 10.0,
               "models": [{"id": "gpt-6-luna", "input_per_mtok": 0.10, "output_per_mtok": 0.50}]},
}
EST = 0.028        # one answer for the budget check: 2 searches + 60k in + 4k out at the rates above
ACTUAL = 0.0225    # one fake answer: 2 searches + 20k in + 1k out

SECRET_ANSWER = "ZZ-ANSWER-TEXT-never-stored"
QUERY_MARK = "zzquery private name"
URL_MARK = "private-person-slug"
TITLE_MARK = "Zz Private Title"


def fake_estimate(prices, key, model, searches, tin, tout):
    return round(searches * 0.01 + tin * 0.10 / 1e6 + tout * 0.50 / 1e6, 6)


@pytest.fixture(autouse=True)
def fake_prices(monkeypatch):
    """The runner reads prices and costs through app.ai_audit.providers (another agent's module): pin
    them, and stand in a module if it is missing."""
    try:
        import app.ai_audit.providers as P
    except ImportError:
        P = types.ModuleType("app.ai_audit.providers")
        monkeypatch.setitem(sys.modules, "app.ai_audit.providers", P)
        import app.ai_audit as pkg
        monkeypatch.setattr(pkg, "providers", P, raising=False)
    monkeypatch.setattr(P, "load_prices", lambda: PRICES, raising=False)
    monkeypatch.setattr(P, "estimate_usd", fake_estimate, raising=False)
    monkeypatch.setattr(runner, "PACE_SECONDS", 0)
    return P


def config(**over) -> dict:
    cfg = yaml.safe_load((settings.CONFIG_DIR / "ai_audit.yaml").read_text(encoding="utf-8"))
    cfg.update(over)
    return cfg


@pytest.fixture()
def cfg(monkeypatch):
    state = {"cfg": config()}
    monkeypatch.setattr(runner, "load_config", lambda: state["cfg"])
    return state


class Src(SimpleNamespace):
    pass


class FakeProvider:
    """Same interface as providers.AnthropicProvider / OpenAIProvider."""

    def __init__(self, key, log=None, available=True, status="ok", raise_with=None):
        self.key = key
        self.label = runner.LABELS[key]
        self._available = available
        self.status = status
        self.raise_with = raise_with
        self.calls = []
        self.log = log if log is not None else []

    def available(self):
        return self._available

    def ask(self, question, lang, *, today, cfg):
        self.calls.append((question, lang))
        self.log.append((self.key, question, lang))
        if self.raise_with:
            raise RuntimeError(self.raise_with)
        st = self.status(len(self.calls)) if callable(self.status) else self.status
        n = len(self.calls)
        searched = [Src(url=f"https://www.google.com/url?q=https://www.libyaobserver.ly/news/item-{n}%3Futm_source%3Dopenai",
                        title=f"{TITLE_MARK} {n}", date="2026-10-17", rank=1, citations=0),
                    Src(url=f"https://www.hrw.org/ar/news/2026/10/{n}", title=None, date=None, rank=2, citations=0),
                    Src(url=f"https://unknown-site.ly/{URL_MARK}-{n}", title=None, date=None, rank=3, citations=0),
                    Src(url=f"https://www.facebook.com/some.private.person/posts/{n}", title="Person post", date=None,
                        rank=4, citations=0),
                    Src(url="oai-weather", title=None, date=None, rank=5, citations=0)]
        cited = [Src(url=f"https://libyaobserver.ly/news/item-{n}?srsltid=XYZ", title=f"{TITLE_MARK} {n}", date=None,
                     rank=1, citations=2),
                 Src(url=f"https://unknown-site.ly/{URL_MARK}-{n}", title=None, date=None, rank=2, citations=1)]
        if st in ("refused", "error", "rate_limited"):
            searched, cited = [], []
        return SimpleNamespace(status=st, model="claude-haiku-5-5" if self.key == "anthropic" else "gpt-6-luna",
                               queries=[f"{QUERY_MARK} {lang}"], searched=searched, cited=cited,
                               answer_text=SECRET_ANSWER + (" مرحبا بكم في ليبيا" if lang == "ar" else " hello"),
                               input_tokens=20000, output_tokens=1000, searches=2 if st == "ok" else 0,
                               location_sent={"city": "Tripoli", "country": "LY"}, error=None)


def libya(db) -> Country:
    return db.scalar(select(Country).where(Country.iso2 == "LY"))


def outlet(db, domain) -> Outlet:
    return db.scalar(select(Outlet).where(Outlet.domain == domain))


# ---------------------------------------------------------------- matcher
def test_matcher_unwraps_redirects_and_amp_and_drops_tracking(db):
    m = M.Matcher(db)
    lo = outlet(db, "libyaobserver.ly")
    r = m.match("https://www.google.com/url?q=https://www.libyaobserver.ly/news/x%3Futm_source%3Dopenai%26srsltid%3Dabc%26id%3D7")
    assert (r.outlet_id, r.match, r.domain) == (lo.id, "exact", "libyaobserver.ly")
    assert r.url == "https://libyaobserver.ly/news/x?id=7"
    aw = outlet(db, "alwasat.ly")
    r = m.match("https://www.google.com/amp/s/www.alwasat.ly/news/libya/123/amp")
    assert (r.outlet_id, r.url) == (aw.id, "https://alwasat.ly/news/libya/123")
    r = m.match("https://www-alwasat-ly.cdn.ampproject.org/c/s/www.alwasat.ly/news/9?utm_campaign=x")
    assert (r.outlet_id, r.url) == (aw.id, "https://alwasat.ly/news/9")
    assert m.match("oai-sports") is None and m.match("") is None


def test_matcher_parent_domain_longest_suffix_never_a_registry(db):
    db.add_all([Outlet(name="CNN", domain="cnn.com", languages=["en"]),
                Outlet(name="junk", domain="co.uk", languages=[])])   # a bad register row must not swallow .co.uk
    db.commit()
    m = M.Matcher(db)
    cnn = outlet(db, "cnn.com")
    r = m.match("https://arabic.cnn.com/middle-east/article/2026/10/17/libya")
    assert (r.outlet_id, r.match, r.domain, r.lang) == (cnn.id, "parent", "cnn.com", "ar")   # ar from arabic.
    r = m.match("https://www.someunknownpaper.co.uk/world/libya")
    assert (r.outlet_id, r.match, r.domain) == (None, "unknown", "someunknownpaper.co.uk")


def test_matcher_path_outlet_before_host(db):
    m = M.Matcher(db)
    r = m.match("https://www.hrw.org/ar/news/2026/10/01/libya")
    assert (r.outlet_id, r.match, r.domain, r.lang) == (outlet(db, "hrw.org/ar").id, "path", "hrw.org/ar", "ar")
    r = m.match("https://www.hrw.org/news/2026/10/01/libya", "Libya: migrants held")
    assert (r.outlet_id, r.match, r.lang) == (outlet(db, "hrw.org").id, "exact", "en")


def test_matcher_social_account_family_and_unlisted_platform_only(db):
    lo = outlet(db, "libyaobserver.ly")
    db.add(Outlet(name="lyobserver", domain="facebook.com/lyobserver", languages=["en"],
                  external={"parent": "libyaobserver.ly"}))
    db.commit()
    acct = outlet(db, "facebook.com/lyobserver")
    m = M.Matcher(db)
    r = m.match("https://m.facebook.com/LyObserver/posts/123", "Observer post")
    assert (r.outlet_id, r.family_id, r.match, r.domain) == (acct.id, lo.id, "social", "facebook.com/lyobserver")
    r = m.match("https://www.facebook.com/some.private.person/posts/9", "رسالة من شخص")
    assert (r.outlet_id, r.domain, r.url, r.keep_title, r.lang) == (None, "facebook.com", "https://facebook.com/", False, "ar")
    r = m.match("https://twitter.com/someone_private/status/1")
    assert (r.domain, r.url) == ("x.com", "https://x.com/")
    r = m.match("https://someone.medium.com/my-story")
    assert (r.outlet_id, r.domain, r.url) == (None, "medium.com", "https://medium.com/")


def test_matcher_language_title_then_url_then_outlet(db):
    m = M.Matcher(db)
    bbc = outlet(db, "bbc.com")   # registered as BBC Arabic, languages [ar]
    assert m.match("https://www.bbc.com/news/world-africa-1", "Libya floods: what we know").lang == "en"
    assert m.match("https://www.bbc.com/arabic/articles/c1").lang == "ar"
    r = m.match("https://www.bbc.com/news/world-africa-1")
    assert (r.outlet_id, r.lang) == (bbc.id, "ar")   # no title, no marker: the outlet's languages
    assert m.match("https://unknown-paper.com/a").lang == "und"


def test_matcher_never_creates_outlets_and_rematch_picks_up_register_changes(db, cfg):
    before = db.scalar(select(func.count(Outlet.id)))
    m = M.Matcher(db)
    assert m.match("https://brand-new-libyan-site.ly/news/1").outlet_id is None
    runner.run_week(db, libya(db), providers={"anthropic": FakeProvider("anthropic")}, limit=2)
    assert db.scalar(select(func.count(Outlet.id))) == before
    rows = db.scalars(select(AiSource).where(AiSource.domain == "unknown-site.ly")).all()
    assert rows and all(r.outlet_id is None and r.match == "unknown" for r in rows)
    db.add(Outlet(name="Unknown Site", domain="unknown-site.ly", languages=["ar"]))
    db.commit()
    res = M.rematch(db)
    assert res["changed"] >= len(rows)
    new = outlet(db, "unknown-site.ly")
    assert all(r.outlet_id == new.id and r.match == "exact" for r in
               db.scalars(select(AiSource).where(AiSource.domain == "unknown-site.ly")))


# ---------------------------------------------------------------- runner
def test_full_week_is_interleaved_question_language_provider(db, cfg):
    log = []
    a, o = FakeProvider("anthropic", log), FakeProvider("openai", log)
    res = runner.run_week(db, libya(db), providers={"anthropic": a, "openai": o})
    qs = runner.questions(libya(db))
    assert len(qs) == 8 and len(log) == 32
    expected = [(k, q[lang], lang) for q in qs for lang in ("ar", "en") for k in ("anthropic", "openai")]
    assert log == expected
    assert {r["provider"]: r["status"] for r in res["runs"]} == {"anthropic": "ok", "openai": "ok"}
    run = db.scalar(select(AiRun).where(AiRun.provider == "anthropic"))
    assert run.cost_usd == pytest.approx(16 * ACTUAL)
    assert run.usage == {"input_tokens": 16 * 20000, "output_tokens": 16 * 1000, "searches": 32}
    assert run.price_basis["as_of"] == "2026-10-18" and "claude-haiku-5-5" in run.price_basis["models"]
    assert run.settings["location_sent"] == {"city": "Tripoli", "country": "LY"} and run.settings["max_searches"] == 2
    assert "fly_region" in run.settings and run.week_start.weekday() == 0
    ans = db.scalar(select(AiAnswer).where(AiAnswer.run_id == run.id, AiAnswer.lang == "ar"))
    assert ans.answer_lang == "en" or ans.answer_lang == "ar"
    assert ans.question_version == runner.question_version(qs[0]) and ans.answer_chars > 0
    assert ans.n_searched == 4 and ans.n_cited == 2   # oai-weather dropped
    cited = db.scalar(select(AiSource).where(AiSource.answer_id == ans.id, AiSource.role == "cited",
                                             AiSource.domain == "libyaobserver.ly"))
    assert cited.citations == 2 and "srsltid" not in cited.url
    health = {r.source_key: r.status for r in db.scalars(select(SourceRun))}
    assert health == {"ai_audit_anthropic": "ok", "ai_audit_openai": "ok"}


def test_cap_stops_the_run_and_records_the_rest_as_over_budget(db, cfg):
    log = []
    a, o = FakeProvider("anthropic", log), FakeProvider("openai", log)
    res = runner.run_week(db, libya(db), providers={"anthropic": a, "openai": o}, cap=0.1)
    # 4 answers fit (0.0675 spent + 0.028 estimate <= 0.1; the fifth would not), balanced across both
    assert len(a.calls) == 2 and len(o.calls) == 2
    assert [x[2] for x in log] == ["ar", "ar", "en", "en"]
    assert db.scalar(select(func.count(AiAnswer.id)).where(AiAnswer.status == "over_budget")) == 28
    assert {r["provider"]: r["status"] for r in res["runs"]} == {"anthropic": "over_budget", "openai": "over_budget"}
    assert runner.spent_this_week(db, runner.week_start_of(utcnow().date())) <= 0.1
    assert {r.status for r in db.scalars(select(SourceRun))} == {"partial"}
    # the weekly cap covers every assistant: a second, forced run this week has no room left
    res = runner.run_week(db, libya(db), providers={"anthropic": FakeProvider("anthropic")}, cap=0.1, force=True)
    assert res["runs"][0]["status"] == "over_budget" and res["runs"][0]["answers"] == 0


def test_awaiting_key_records_the_run_and_the_health_line(db, cfg):
    a, o = FakeProvider("anthropic"), FakeProvider("openai", available=False)
    res = runner.run_week(db, libya(db), providers={"anthropic": a, "openai": o})
    assert not o.calls and len(a.calls) == 16
    assert {"provider": "openai", "reason": "awaiting_key"} in res["skipped"]
    run = db.scalar(select(AiRun).where(AiRun.provider == "openai"))
    assert run.status == "awaiting_key" and "OPENAI_API_KEY" in run.error
    sr = db.scalar(select(SourceRun).where(SourceRun.source_key == "ai_audit_openai"))
    assert sr.status == "awaiting_key" and "OPENAI_API_KEY" in sr.error
    # once the key is set the same week, the assistant runs (a run with no call does not block it)
    o2 = FakeProvider("openai")
    runner.run_week(db, libya(db), providers={"openai": o2})
    assert len(o2.calls) == 16
    assert db.scalar(select(func.count(AiRun.id)).where(AiRun.provider == "openai")) == 1   # the row was reused


def test_one_run_per_week_unless_forced(db, cfg):
    runner.run_week(db, libya(db), providers={"anthropic": FakeProvider("anthropic")}, limit=2)
    again = FakeProvider("anthropic")
    res = runner.run_week(db, libya(db), providers={"anthropic": again})
    assert not again.calls and {"provider": "anthropic", "reason": "already_run"} in res["skipped"]
    forced = FakeProvider("anthropic")
    res = runner.run_week(db, libya(db), providers={"anthropic": forced}, force=True, limit=2)
    assert len(forced.calls) == 2
    runs = db.scalars(select(AiRun).order_by(AiRun.id)).all()
    assert [r.forced for r in runs] == [False, True]


def test_disabled_provider_and_dry_run_write_nothing(db, cfg, fake_prices, monkeypatch):
    cfg["cfg"] = config(providers={"anthropic": {"enabled": True}, "openai": {"enabled": False}})
    made = FakeProvider("anthropic")
    monkeypatch.setattr(fake_prices, "get_providers", lambda c: {"anthropic": made}, raising=False)
    plan = runner.run_week(db, libya(db), dry_run=True)
    assert len(plan["planned"]) == 16 and plan["estimated_usd"] == pytest.approx(16 * EST, abs=1e-4)
    assert {"provider": "openai", "reason": "disabled"} in plan["skipped"]
    assert plan["cap_usd"] == 1.0 and plan["spent_this_week_usd"] == 0 and plan["fits_cap"] == 16
    assert not made.calls and db.scalar(select(func.count(AiRun.id))) == 0
    assert db.scalar(select(func.count(SourceRun.id))) == 0
    runner.run_week(db, libya(db), limit=1)
    assert db.scalar(select(AiRun.status).where(AiRun.provider == "openai")) == "disabled"


def test_answer_text_is_never_stored_and_the_audit_stays_unscored(db, cfg):
    counts = lambda: [db.scalar(select(func.count()).select_from(t)) for t in (Item, ItemTheme, CellWeek, Outlet)]  # noqa: E731
    before = counts()
    runner.run_week(db, libya(db), providers={"anthropic": FakeProvider("anthropic"), "openai": FakeProvider("openai")})
    assert counts() == before
    dump = []
    for table in Base.metadata.sorted_tables:
        for row in db.execute(text(f'SELECT * FROM "{table.name}"')):
            dump.append(json.dumps([str(v) for v in row], ensure_ascii=False))
    blob = "\n".join(dump)
    assert QUERY_MARK in blob                       # the scan sees stored data (queries are kept, admin-only)
    assert SECRET_ANSWER not in blob and "مرحبا بكم" not in blob
    assert "some.private.person" not in blob and "Person post" not in blob   # unlisted account: platform only


def test_refusals_in_a_row_stop_an_assistant_and_errors_are_scrubbed(db, cfg, monkeypatch):
    refuser = FakeProvider("anthropic", status="refused")
    res = runner.run_week(db, libya(db), providers={"anthropic": refuser})
    assert len(refuser.calls) == runner.STOP_AFTER
    run = db.get(AiRun, res["runs"][0]["run_id"])
    assert run.status == "partial" and run.settings["stopped"] == {"reason": "refused", "n": 3}
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-TESTKEYabcdef123456")
    broken = FakeProvider("openai", raise_with="boom with sk-proj-TESTKEYabcdef123456 inside")
    res = runner.run_week(db, libya(db), providers={"openai": broken}, limit=2)
    run = db.get(AiRun, res["runs"][0]["run_id"])
    assert run.status == "error" and "boom" in run.error and "TESTKEY" not in run.error
    assert "TESTKEY" not in (db.scalar(select(SourceRun.error).where(SourceRun.source_key == "ai_audit_openai")) or "")


def test_unknown_cost_is_charged_the_estimate_and_the_budget_reaches_the_provider(db, cfg):
    seen = []

    class TimesOut(FakeProvider):
        def ask(self, question, lang, *, today, cfg):
            seen.append(cfg["answer_budget_usd"])
            ans = super().ask(question, lang, today=today, cfg=cfg)
            ans.status, ans.searches, ans.input_tokens, ans.output_tokens = "error", 0, 0, 0
            ans.searched, ans.cited, ans.cost_unknown = [], [], True
            return ans

    runner.run_week(db, libya(db), providers={"anthropic": TimesOut("anthropic")}, limit=2, cap=0.5)
    run = db.scalar(select(AiRun))
    assert run.cost_usd == pytest.approx(2 * EST)          # a timeout is never free in the ledger
    assert seen == [pytest.approx(0.5), pytest.approx(0.5 - EST)]
    # a provider that raises is charged the same way
    runner.run_week(db, libya(db), providers={"openai": FakeProvider("openai", raise_with="boom")}, limit=1)
    assert db.scalar(select(AiRun.cost_usd).where(AiRun.provider == "openai")) == pytest.approx(EST)


def test_force_never_overlaps_a_run_still_going(db, cfg):
    runner.run_week(db, libya(db), providers={"anthropic": FakeProvider("anthropic")}, limit=1)
    run = db.scalar(select(AiRun))
    run.status = "running"          # as another process (a CLI run) would leave it while it works
    db.commit()
    forced = FakeProvider("anthropic")
    res = runner.run_week(db, libya(db), providers={"anthropic": forced}, force=True, limit=1)
    assert not forced.calls and {"provider": "anthropic", "reason": "running"} in res["skipped"]


def test_dry_run_shows_what_an_assistant_waiting_for_its_key_would_add(db, cfg):
    plan = runner.run_week(db, libya(db), dry_run=True, providers={
        "anthropic": FakeProvider("anthropic", available=False), "openai": FakeProvider("openai", available=False)})
    assert plan["planned"] == [] and {s["reason"] for s in plan["skipped"]} == {"awaiting_key"}
    assert [(w["provider"], w["answers"]) for w in plan["awaiting_key"]] == [("anthropic", 16), ("openai", 16)]
    assert plan["awaiting_key"][0]["estimated_usd"] == pytest.approx(16 * EST, abs=1e-4)


# ---------------------------------------------------------------- API
def _seed_week(db):
    """A run with answers, and a counted Al Wasat article (a Libyan outlet nobody cites)."""
    runner.run_week(db, libya(db), providers={"anthropic": FakeProvider("anthropic"),
                                              "openai": FakeProvider("openai", available=False)}, limit=2)
    aw = outlet(db, "alwasat.ly")
    db.add(Item(country_id=libya(db).id, kind="article", source_key="rss", dedupe_key="url:https://alwasat.ly/n/1",
                url="https://alwasat.ly/n/1", title="خبر", published_at=utcnow() - timedelta(days=1), outlet_id=aw.id,
                relevant=True))
    db.commit()


def test_summary_hidden_from_journalists_until_visible_to_team(client, users, db, cfg):
    _seed_week(db)
    login(client, "j@example.org", "journo-password-1")
    assert client.get("/api/ai-audit/summary").json() == {"visible": False}
    lo = outlet(db, "libyaobserver.ly")
    assert client.get(f"/api/outlets/{lo.id}").json()["ai_cited_4w"] is None
    login(client, "admin@example.org", "admin-password-1")
    r = client.get("/api/ai-audit/summary").json()
    assert r["visible"] is True and r["n_answers"] == 2 and r["status"]["openai"] == "awaiting_key"
    assert client.get(f"/api/outlets/{lo.id}").json()["ai_cited_4w"] == 2
    cfg["cfg"] = config(visible_to="team")
    login(client, "j@example.org", "journo-password-1")
    r = client.get("/api/ai-audit/summary", params={"weeks": 12, "provider": "anthropic", "lang": "ar"}).json()
    assert r["visible"] is True and r["weeks"] == 12 and r["n_answers"] == 1
    p = r["providers"][0]
    assert p["key"] == "anthropic" and p["answers"] == 1 and p["cited_per_answer"] == {"median": 2, "min": 2, "max": 2}
    assert p["cited_scope"]["libyan"] == 1 and p["cited_scope"]["unregistered"] == 1
    assert p["query_lang"]["en"] + p["query_lang"]["other"] + p["query_lang"]["ar"] == 1
    top = {t["domain"]: t for t in r["top_outlets"]}
    assert top["libyaobserver.ly"]["outlet_id"] == lo.id and top["libyaobserver.ly"]["by_provider"] == {"anthropic": 1}
    assert top["unknown-site.ly"]["outlet_id"] is None and top["unknown-site.ly"]["name"] == "unknown-site.ly"
    never = {n["domain"]: n for n in r["never_cited"]}
    assert "alwasat.ly" in never and never["alwasat.ly"]["articles_12w"] == 1
    assert never["alwasat.ly"]["appeared_in_results"] is False and "libyaobserver.ly" not in never
    assert r["coverage_scope"]["libyan"] >= 1
    assert client.get(f"/api/outlets/{lo.id}").json()["ai_cited_4w"] == 2
    assert client.get("/api/ai-audit/summary", params={"weeks": 5}).status_code == 400
    assert client.get("/api/ai-audit/summary", params={"provider": "gemini"}).status_code == 400


def test_non_admins_never_receive_queries_urls_or_titles(client, users, db, cfg):
    _seed_week(db)
    cfg["cfg"] = config(visible_to="team")
    login(client, "j@example.org", "journo-password-1")
    run_id = db.scalar(select(AiRun.id).where(AiRun.provider == "anthropic"))
    lo = outlet(db, "libyaobserver.ly")
    seen = []
    for weeks in (4, 12):
        for lang in ("all", "ar", "en"):
            seen.append(client.get("/api/ai-audit/summary", params={"weeks": weeks, "lang": lang}).text)
    seen.append(client.get(f"/api/outlets/{lo.id}").text)
    seen.append(client.get("/api/sources/health").text)
    for path in ("/api/admin/ai-audit/runs", f"/api/admin/ai-audit/answers?run_id={run_id}",
                 "/api/admin/ai-audit/unknown-domains"):
        r = client.get(path)
        assert r.status_code == 403
        seen.append(r.text)
    r = client.post("/api/admin/ai-audit/run", json={"dry_run": True})
    assert r.status_code == 403
    blob = "\n".join(seen)
    for mark in (QUERY_MARK, URL_MARK, TITLE_MARK, "/news/item-", "hrw.org/ar/news", "unknown-site.ly/", "facebook.com/"):
        assert mark not in blob, mark


def test_admin_routes_runs_answers_unknown_domains_and_dry_run(client, users, db, cfg, fake_prices, monkeypatch):
    _seed_week(db)
    login(client, "admin@example.org", "admin-password-1")
    runs = client.get("/api/admin/ai-audit/runs").json()
    assert runs["cap_usd"] == 1.0 and runs["week_cost_usd"] == pytest.approx(2 * ACTUAL, abs=1e-4)
    assert runs["ytd_cost_usd"] >= runs["week_cost_usd"]
    by = {r["provider"]: r for r in runs["runs"]}
    assert by["anthropic"]["answers"] == 2 and by["anthropic"]["status"] == "ok"
    assert by["openai"]["status"] == "awaiting_key" and "OPENAI_API_KEY" in by["openai"]["error"]
    ar = client.get("/api/admin/ai-audit/runs", headers={"X-Lang": "ar"}).json()
    note = {r["provider"]: r for r in ar["runs"]}["openai"]["error"]
    assert "OPENAI_API_KEY" in note and "المفتاح" in note
    answers = client.get("/api/admin/ai-audit/answers", params={"run_id": by["anthropic"]["id"]}).json()
    assert [a["lang"] for a in answers] == ["ar", "en"]
    assert answers[0]["question"].startswith("ما ") and answers[1]["question"].startswith("What")
    assert QUERY_MARK in answers[0]["queries"][0]
    cited = {c["domain"]: c for c in answers[0]["cited"]}
    assert cited["libyaobserver.ly"]["outlet_name"] == "Libya Observer" and cited["libyaobserver.ly"]["citations"] == 2
    assert TITLE_MARK in cited["libyaobserver.ly"]["title"]
    unknown = client.get("/api/admin/ai-audit/unknown-domains").json()
    assert unknown[0] == {"domain": "unknown-site.ly", "cited": 2, "searched": 2, "ly": True}
    assert all(u["domain"] != "facebook.com" for u in unknown)
    assert client.get("/api/admin/ai-audit/answers", params={"run_id": 99999}).status_code == 404
    monkeypatch.setattr(fake_prices, "get_providers",
                        lambda c: {"anthropic": FakeProvider("anthropic"), "openai": FakeProvider("openai")}, raising=False)
    plan = client.post("/api/admin/ai-audit/run", json={"dry_run": True, "force": True}).json()
    assert len(plan["planned"]) == 32 and plan["planned"][0] == {"provider": "anthropic", "question_key": "security", "lang": "ar"}
    assert plan["estimated_usd"] == pytest.approx(32 * EST, abs=1e-4) and plan["cap_usd"] == 1.0
    assert plan["spent_this_week_usd"] == pytest.approx(2 * ACTUAL, abs=1e-4)
    plan = client.post("/api/admin/ai-audit/run", json={"dry_run": True}).json()
    assert {"provider": "anthropic", "reason": "already_run"} in plan["skipped"] and len(plan["planned"]) == 16
    assert client.post("/api/admin/ai-audit/run", json={"provider": "gemini"}).status_code == 400
    assert db.scalar(select(func.count(AiRun.id))) == 2   # dry runs wrote nothing


def test_summary_labels_and_health_lines_speak_arabic(client, users, db, cfg):
    _seed_week(db)
    login(client, "admin@example.org", "admin-password-1")
    r = client.get("/api/ai-audit/summary", headers={"X-Lang": "ar"}).json()
    assert r["providers"][0]["label"] == "Claude (من شركة Anthropic)"
    health = {h["key"]: h for h in client.get("/api/sources/health", headers={"X-Lang": "ar"}).json()}
    assert health["ai_audit_anthropic"]["label"].startswith("تدقيق إجابات الذكاء الاصطناعي")
    assert health["ai_audit_openai"]["status"] == "awaiting_key" and "OPENAI_API_KEY" in health["ai_audit_openai"]["error"]


def test_summary_names_only_the_platform_for_an_unregistered_hosted_blog():
    from app.api import ai_audit as api
    assert api._public_domain("some-person.blogspot.com") == "blogspot.com"
    assert api._public_domain("jane.substack.com") == "substack.com"
    assert api._public_domain("unknown-site.ly") == "unknown-site.ly"



def test_a_failed_run_that_spent_nothing_does_not_block_the_week():
    from app.models import AiRun
    free = AiRun(provider="anthropic", status="error", cost_usd=0.0, usage={"searches": 0})
    paid = AiRun(provider="anthropic", status="error", cost_usd=0.02, usage={"searches": 2})
    assert runner._blocking([free]) is None
    assert runner._blocking([paid]) == "already_run"
    assert runner._blocking([free, paid]) == "already_run"
