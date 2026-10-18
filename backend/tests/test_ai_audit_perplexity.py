"""AI answers audit, Perplexity (Agent API, web_search tool): request shape, parsing of the documented
response shapes, status mapping, fallbacks, prices, and the runner with three assistants under one weekly
cap. No network: the provider gets an httpx MockTransport. Fixture shapes follow the response examples on
docs.perplexity.ai (web-search tool page, output-control page, API reference), read 2026-10-18. The error
bodies follow the documented ErrorInfo {message, code, type}; Perplexity publishes no code values, so the
codes in perplexity_failed.json are illustrative."""
import copy
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import func, select

from app import i18n
from app.ai_audit import providers as P
from app.ai_audit import runner
from app.models import AiAnswer, AiRun, AiSource, Country, SourceRun, utcnow

FIX = Path(__file__).resolve().parent / "fixtures" / "ai_audit"
TODAY = date(2026, 10, 19)
LOCATION = {"city": "Tripoli", "region": "Tripoli", "country": "LY", "timezone": "Africa/Tripoli"}
SENT_LOC = {"country": "LY", "region": "Tripoli", "city": "Tripoli"}
KEY = "pplx-test-not-a-real-key-0123456789"


def fixture(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def cfg(**over):
    base = {"max_searches": 2, "date_line": True, "location": dict(LOCATION), "weekly_cap_usd": 1.0}
    return {**base, **P.load_prices()["perplexity"], **over}


def pplx_http(responses):
    """httpx client whose transport answers from a list of (status, json[, headers]) and records requests."""
    seen = []
    queue = list(responses)

    def handler(request):
        seen.append(request)
        item = queue.pop(0)
        status, body = item[0], item[1]
        headers = item[2] if len(item) > 2 else None
        return httpx.Response(status, json=body, headers=headers)

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def provider(responses, sleeps=None):
    http, seen = pplx_http(responses)
    slept = sleeps if sleeps is not None else []
    return P.PerplexityProvider(http=http, sleep=slept.append), seen


@pytest.fixture()
def key(monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", KEY)


# ---------------------------------------------------------------- parsing

def test_parses_queries_results_and_marker_citations(key):
    prov, seen = provider([(200, fixture("perplexity_ok.json"))])
    ans = prov.ask("What is the current security situation in Libya?", "en", today=TODAY, cfg=cfg())
    assert ans.status == "ok" and ans.error is None and ans.cost_unknown is False
    assert ans.model == "perplexity/sonar"
    assert ans.queries == ["Libya security situation October 2026", "Tripoli security news", "Tripoli clashes 2026"]
    # every result of both searches, deduplicated by URL in order of first appearance
    assert [s.url for s in ans.searched] == [
        "https://libyaobserver.ly/news/security-update-tripoli",
        "https://www.reuters.com/world/africa/libya-talks-2026-10-14/",
        "https://en.wikipedia.org/wiki/Libya",
        "https://libyaherald.com/2026/10/calm-returns/",
    ]
    assert [s.rank for s in ans.searched] == [1, 2, 3, 4]
    assert ans.searched[0].title == "Security update from Tripoli" and ans.searched[0].date == "2026-10-15"
    assert ans.searched[2].date == "2026-10-10"            # no publication date: last_updated
    # [1][4] ... [2] ... [1][5] ... [9]: id 5 is the Reuters link again, id 9 is no result
    assert [(s.url, s.citations, s.rank) for s in ans.cited] == [
        ("https://libyaobserver.ly/news/security-update-tripoli", 2, 1),
        ("https://libyaherald.com/2026/10/calm-returns/", 1, 2),
        ("https://www.reuters.com/world/africa/libya-talks-2026-10-14/", 2, 3),
    ]
    assert ans.cited[0].title == "Security update from Tripoli"   # filled from the search result
    assert ans.searches == 2 and ans.input_tokens == 9120 and ans.output_tokens == 640
    assert ans.location_sent == SENT_LOC
    assert "calm this week" in ans.answer_text
    assert "SNIPPET-MUST-NOT-BE-KEPT" not in repr(ans)    # result snippets are page text: never read
    assert len(seen) == 1


def test_request_body(key):
    prov, seen = provider([(200, fixture("perplexity_ok.json"))])
    prov.ask("ما هو الوضع الأمني الحالي في ليبيا؟", "ar", today=TODAY, cfg=cfg())
    req = seen[0]
    assert str(req.url) == "https://api.perplexity.ai/v1/agent"
    assert req.headers["authorization"] == f"Bearer {KEY}"
    body = json.loads(req.content)
    assert body == {
        "model": "perplexity/sonar",
        "input": "ما هو الوضع الأمني الحالي في ليبيا؟",
        "instructions": "Today's date is 2026-10-19.",
        "tools": [{"type": "web_search", "user_location": SENT_LOC, "search_type": "web", "max_results": 10,
                   "max_tokens": 2000}],
        "max_steps": 2,
        "max_tool_calls": 2,
        "max_output_tokens": 4000,
        "store": False,
    }
    # no preset (it would pick an OpenAI model), no filters, no language setting, no fields the tool lacks
    for absent in ("preset", "filters", "language_preference", "timezone", "approximate", "background"):
        assert absent not in req.content.decode("utf-8")


def test_source_typed_markers_and_ids_repeated_across_searches(key):
    data = fixture("perplexity_ok.json")
    data["output"][1]["results"][0]["id"] = 1      # the second search numbers from 1 again
    data["output"][2]["content"][0]["text"] = "Calm returned.[web:1] Talks resumed.[web:2][web:4]"
    ans = P.parse_perplexity(data, "perplexity/sonar", SENT_LOC)
    # [web:1] points at two different URLs: skipped, never guessed. [web:4] is nobody now.
    assert [(s.url, s.citations) for s in ans.cited] == [("https://www.reuters.com/world/africa/libya-talks-2026-10-14/", 1)]


def test_url_citation_annotations_win_over_markers(key):
    data = fixture("perplexity_ok.json")
    data["output"][2]["content"][0]["annotations"] = [
        {"type": "url_citation", "url": "https://libyaherald.com/2026/10/calm-returns/", "title": "Calm returns",
         "start_index": 0, "end_index": 20}]
    ans = P.parse_perplexity(data, "perplexity/sonar", SENT_LOC)
    assert [(s.url, s.citations, s.title) for s in ans.cited] == [
        ("https://libyaherald.com/2026/10/calm-returns/", 1, "Calm returns")]


def test_no_search_and_no_date_line(key):
    prov, seen = provider([(200, fixture("perplexity_no_search.json"))])
    ans = prov.ask("q", "ar", today=TODAY, cfg=cfg(date_line=False))
    assert ans.status == "no_search" and ans.searches == 0 and ans.searched == [] and ans.cited == []
    assert ans.input_tokens == 410 and ans.output_tokens == 95 and ans.answer_text.startswith("ليبيا")
    assert "instructions" not in json.loads(seen[0].content)


def test_answer_without_markers_has_no_cited_links(key):
    data = fixture("perplexity_ok.json")
    data["output"][2]["content"][0]["text"] = "The capital has been calm this week."
    ans = P.parse_perplexity(data, "perplexity/sonar", SENT_LOC)
    assert ans.status == "ok" and len(ans.searched) == 4 and ans.cited == []


def test_failed_response_is_an_error(key):
    prov, _ = provider([(200, fixture("perplexity_failed.json"))])
    ans = prov.ask("q", "en", today=TODAY, cfg=cfg())
    assert ans.status == "error" and "server_error" in ans.error and ans.searched == []


def test_content_filter_is_a_refusal(key):
    # Perplexity documents no refusal signal; the Open Responses incomplete_details reason is the one mapped
    data = fixture("perplexity_no_search.json")
    data["status"], data["incomplete_details"] = "incomplete", {"reason": "content_filter"}
    assert P.parse_perplexity(data, "perplexity/sonar", SENT_LOC).status == "refused"
    data["incomplete_details"] = {"reason": "max_output_tokens"}
    assert P.parse_perplexity(data, "perplexity/sonar", SENT_LOC).status == "no_search"   # cut short, still an answer


def test_unfinished_response_is_an_error_with_unknown_cost(key):
    data = fixture("perplexity_no_search.json")
    data["status"] = "in_progress"
    ans = P.parse_perplexity(data, "perplexity/sonar", SENT_LOC)
    assert ans.status == "error" and ans.cost_unknown is True


def test_http_400_is_an_error_without_resend(key):
    prov, seen = provider([(400, fixture("perplexity_error_400.json"))])
    ans = prov.ask("q", "en", today=TODAY, cfg=cfg())
    assert ans.status == "error" and ans.error.startswith("HTTP 400") and "validation failed" in ans.error
    assert len(seen) == 1 and ans.location_sent == SENT_LOC


def test_429_is_rate_limited_and_not_retried(key):
    sleeps = []
    prov, seen = provider([(429, fixture("perplexity_rate_limited.json"), {"Retry-After": "1"})], sleeps)
    ans = prov.ask("q", "en", today=TODAY, cfg=cfg())
    assert ans.status == "rate_limited" and "429" in ans.error and "Too Many Requests" in ans.error
    assert len(seen) == 1 and sleeps == []


def test_without_key_it_is_unavailable_and_makes_no_call(monkeypatch):
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    prov, seen = provider([])
    assert prov.available() is False
    ans = prov.ask("q", "en", today=TODAY, cfg=cfg())
    assert ans.status == "error" and ans.error == "PERPLEXITY_API_KEY is not set" and seen == []
    monkeypatch.setenv("PERPLEXITY_API_KEY", KEY)
    assert P.PerplexityProvider().available() is True


def test_location_fallback_drops_the_country_waits_and_remembers(key):
    rejected = {"error": {"message": "Invalid user_location: unsupported country code"}}
    sleeps = []
    prov, seen = provider([(400, rejected), (200, fixture("perplexity_ok.json")),
                           (200, fixture("perplexity_ok.json"))], sleeps)
    ans = prov.ask("q", "en", today=TODAY, cfg=cfg())
    assert ans.status == "ok" and ans.location_sent == {"region": "Tripoli", "city": "Tripoli"}
    assert [json.loads(r.content)["tools"][0]["user_location"] for r in seen] == [
        SENT_LOC, {"region": "Tripoli", "city": "Tripoli"}]
    assert sleeps == [P.PERPLEXITY_RESEND_GAP]          # Tier 0: 1 request per second
    prov.ask("q", "en", today=TODAY, cfg=cfg())         # the next answer goes without the country at once
    assert len(seen) == 3 and "country" not in json.loads(seen[2].content)["tools"][0]["user_location"]
    assert sleeps == [P.PERPLEXITY_RESEND_GAP]


def test_a_rejected_max_tool_calls_is_dropped_once_and_max_steps_stays(key):
    rejected = {"error": {"message": "Unknown parameter: max_tool_calls"}}
    prov, seen = provider([(400, rejected), (200, fixture("perplexity_ok.json")),
                           (200, fixture("perplexity_ok.json"))])
    assert prov.ask("q", "en", today=TODAY, cfg=cfg()).status == "ok"
    bodies = [json.loads(r.content) for r in seen]
    assert bodies[0]["max_tool_calls"] == 2 and "max_tool_calls" not in bodies[1] and bodies[1]["max_steps"] == 2
    prov.ask("q", "en", today=TODAY, cfg=cfg())
    assert "max_tool_calls" not in json.loads(seen[2].content)


def test_model_fallback_and_a_dearer_model_never_started_past_the_budget(key):
    models = [{"id": "perplexity/sonar", "input_per_mtok": 0.25, "output_per_mtok": 2.5},
              {"id": "openai/gpt-6-luna", "input_per_mtok": 0.10, "output_per_mtok": 0.50}]
    prov, seen = provider([(404, {"error": {"message": "model not found: perplexity/sonar"}}),
                           (200, fixture("perplexity_ok.json"))])
    c = cfg(models=models, estimate={"input_tokens": 60000, "output_tokens": 4000})
    assert prov.next_model(c) == "perplexity/sonar"
    prov.ask("q", "en", today=TODAY, cfg=c)
    assert [json.loads(r.content)["model"] for r in seen] == ["perplexity/sonar", "openai/gpt-6-luna"]
    assert prov.next_model(c) == "openai/gpt-6-luna"
    dear = [{"id": "perplexity/sonar", "input_per_mtok": 0.25, "output_per_mtok": 2.5},
            {"id": "perplexity/expensive", "input_per_mtok": 5.0, "output_per_mtok": 25.0}]
    prov, seen = provider([(404, {"error": {"message": "model not found"}})])
    ans = prov.ask("q", "en", today=TODAY, cfg=cfg(models=dear, answer_budget_usd=0.05,
                                                   estimate={"input_tokens": 60000, "output_tokens": 4000}))
    assert ans.status == "error" and "not tried" in ans.error and len(seen) == 1


def test_timeout_is_an_error_with_unknown_cost(key):
    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    prov = P.PerplexityProvider(http=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda s: None)
    ans = prov.ask("q", "en", today=TODAY, cfg=cfg())
    assert ans.status == "error" and "ReadTimeout" in ans.error and ans.cost_unknown is True


def test_errors_never_carry_the_key(key):
    body = {"error": {"message": f"Invalid API key {KEY} provided", "type": "authentication_error"}}
    prov, _ = provider([(401, body)])
    ans = prov.ask("q", "en", today=TODAY, cfg=cfg())
    assert ans.status == "error" and "401" in ans.error
    assert KEY not in ans.error and "pplx-test" not in ans.error and "user_location" not in ans.error
    assert "pplx-" not in P.safe_message("leaked pplx-AbCdEf123456 here")
    assert "pplx-AbCdEf123456" not in runner._scrub("leaked pplx-AbCdEf123456 here")


# ---------------------------------------------------------------- prices, config, registry

def test_price_block_is_complete_and_dated():
    prices = P.load_prices()
    block = prices["perplexity"]
    assert prices["as_of"] == "2026-10-18"
    assert block["search_per_1000_usd"] == 2.5 and block["tool"] == "web_search"
    assert block["models"][0] == {"id": "perplexity/sonar", "input_per_mtok": 0.25, "output_per_mtok": 2.5}
    assert block["request"]["max_output_tokens"] == 4000
    assert block["sources"] and all(u.startswith("https://docs.perplexity.ai/") for u in block["sources"])


def test_the_estimate_comes_from_perplexity_prices():
    prices = P.load_prices()
    c = runner.load_config()
    # 2 searches x $2.50/1000 + 60k x $0.25/M + 4k x $2.50/M
    assert P.estimate_usd(prices, "perplexity", "perplexity/sonar", 2, 60_000, 4_000) == pytest.approx(0.03)
    assert runner._estimate(P, prices, "perplexity", c, P.PerplexityProvider()) == pytest.approx(0.03)
    assert runner._estimate(P, prices, "anthropic", c) == pytest.approx(0.028)   # each its own rates
    # the merged cfg ask() receives prices the same way (the first live run's regression, for Perplexity)
    ask_cfg = {**runner._ask_cfg(c, prices, "perplexity"), "answer_budget_usd": 1.0}
    block = P._provider_block(ask_cfg, "perplexity")
    assert P._model_ids(block, "x") == ["perplexity/sonar"]
    assert P.estimate_usd(ask_cfg, "perplexity", "perplexity/sonar", 2, 60000, 4000) == pytest.approx(0.03)
    assert P._model_fits(ask_cfg, block, "perplexity", "perplexity/sonar", 2, 4000, 1.0)
    assert not P._model_fits(ask_cfg, block, "perplexity", "perplexity/sonar", 2, 4000, 0.029)
    # the fixture answer: 2 searches, 9,120 in, 640 out
    assert P.estimate_usd(prices, "perplexity", "perplexity/sonar", 2, 9120, 640) == pytest.approx(0.00888)


def test_config_registry_labels_and_health_lines():
    c = runner.load_config()
    assert c["providers"]["perplexity"] == {"enabled": True} and c["weekly_cap_usd"] == 1.0
    assert runner.known_keys(c) == ["anthropic", "openai", "perplexity"]
    made = P.get_providers(c)
    assert list(made) == ["anthropic", "openai", "perplexity"]
    assert made["perplexity"].label == "Perplexity (API)" == runner.LABELS["perplexity"]
    assert runner.KEY_NAMES["perplexity"] == "PERPLEXITY_API_KEY"
    from app.collectors import EXTRA_HEALTH, STALE_HOURS
    assert EXTRA_HEALTH["ai_audit_perplexity"] == "AI answers audit: Perplexity"
    assert STALE_HOURS["ai_audit_perplexity"] == 192
    cat = i18n.load()
    assert cat["Perplexity (API)"].startswith("Perplexity (")
    assert cat["AI answers audit: Perplexity"] == "تدقيق إجابات الذكاء الاصطناعي: Perplexity"


# ---------------------------------------------------------------- runner: three assistants, one cap

class Fake:
    """Claude or ChatGPT stand-in: 2 searches, 20k in, 1k out (USD 0.0225 at the listed rates)."""

    def __init__(self, key, log):
        self.key, self.label, self.log = key, runner.LABELS[key], log

    def available(self):
        return True

    def ask(self, question, lang, *, today, cfg):
        self.log.append((self.key, question, lang))
        src = [SimpleNamespace(url="https://libyaobserver.ly/news/1", title="T", date=None, rank=1, citations=1)]
        return SimpleNamespace(status="ok", model="claude-haiku-5-5" if self.key == "anthropic" else "gpt-6-luna",
                               queries=["q"], searched=src, cited=src, answer_text="hello", input_tokens=20000,
                               output_tokens=1000, searches=2, location_sent={"city": "Tripoli"}, error=None)


class LoggedPerplexity(P.PerplexityProvider):
    def __init__(self, log):
        http, self.seen = pplx_http([(200, fixture("perplexity_ok.json"))] * 48)
        super().__init__(http=http, sleep=lambda s: None)
        self.log = log

    def ask(self, question, lang, *, today, cfg):
        self.log.append((self.key, question, lang))
        return super().ask(question, lang, today=today, cfg=cfg)


@pytest.fixture()
def week(monkeypatch, key):
    monkeypatch.setattr(runner, "PACE_SECONDS", 0)


def libya(db) -> Country:
    return db.scalar(select(Country).where(Country.iso2 == "LY"))


def three(log):
    return {"anthropic": Fake("anthropic", log), "openai": Fake("openai", log), "perplexity": LoggedPerplexity(log)}


def test_three_assistants_interleave_and_share_one_cap(db, week):
    log = []
    provs = three(log)
    res = runner.run_week(db, libya(db), providers=provs)
    qs = runner.questions(libya(db))
    assert len(log) == 48
    assert log == [(k, q[lang], lang) for q in qs for lang in ("ar", "en") for k in ("anthropic", "openai", "perplexity")]
    assert {r["provider"]: r["status"] for r in res["runs"]} == {"anthropic": "ok", "openai": "ok", "perplexity": "ok"}
    run = db.scalar(select(AiRun).where(AiRun.provider == "perplexity"))
    assert run.model == "perplexity/sonar" and run.tool == "web_search"
    assert run.cost_usd == pytest.approx(16 * 0.00888)            # priced at Perplexity's own rates
    assert run.usage == {"input_tokens": 16 * 9120, "output_tokens": 16 * 640, "searches": 32}
    assert run.price_basis["search_per_1000_usd"] == 2.5 and "perplexity/sonar" in run.price_basis["models"]
    assert run.settings["location_sent"] == SENT_LOC
    ans = db.scalar(select(AiAnswer).where(AiAnswer.run_id == run.id, AiAnswer.lang == "ar"))
    assert ans.n_searched == 4 and ans.n_cited == 3 and ans.status == "ok"
    assert db.scalar(select(func.count(AiSource.id)).where(AiSource.answer_id == ans.id)) == 7
    total = runner.spent_this_week(db, runner.week_start_of(utcnow().date()))
    assert total == pytest.approx(2 * 16 * 0.0225 + 16 * 0.00888) and total <= 1.0
    health = {r.source_key: r.status for r in db.scalars(select(SourceRun))}
    assert health == {"ai_audit_anthropic": "ok", "ai_audit_openai": "ok", "ai_audit_perplexity": "ok"}
    # the request each answer sent carried the question and the week's date line
    body = json.loads(provs["perplexity"].seen[0].content)
    assert body["input"] == qs[0]["ar"] and body["instructions"].startswith("Today's date is ")


def test_the_cap_stops_all_three_evenly(db, week):
    log = []
    res = runner.run_week(db, libya(db), providers=three(log), cap=0.08)
    # Claude: 0 + 0.028 fits (spends 0.0225); ChatGPT: 0.0225 + 0.028 fits (0.045 spent); Perplexity:
    # 0.045 + 0.030 fits (spends 0.00888); Claude again: 0.05388 + 0.028 > 0.08, and the rest is over_budget
    assert [k for k, _q, _l in log] == ["anthropic", "openai", "perplexity"]
    assert db.scalar(select(func.count(AiAnswer.id)).where(AiAnswer.status == "over_budget")) == 45
    assert {r["status"] for r in res["runs"]} == {"over_budget"}
    assert runner.spent_this_week(db, runner.week_start_of(utcnow().date())) <= 0.08


def test_perplexity_is_checked_against_its_own_estimate(db, week):
    """At cap 0.074 Perplexity's USD 0.030 estimate no longer fits after the first two answers (0.045 spent),
    where Claude's USD 0.028 would have: the runner prices Perplexity from its own block."""
    log = []
    runner.run_week(db, libya(db), providers=three(log), cap=0.074)
    assert [k for k, _q, _l in log] == ["anthropic", "openai"]
    assert db.scalar(select(AiRun.cost_usd).where(AiRun.provider == "perplexity")) == 0


def test_perplexity_waits_for_its_key(db, monkeypatch):
    monkeypatch.setattr(runner, "PACE_SECONDS", 0)
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    log = []
    provs = three(log)
    res = runner.run_week(db, libya(db), providers=provs)
    assert {"provider": "perplexity", "reason": "awaiting_key"} in res["skipped"]
    assert len(log) == 32 and provs["perplexity"].seen == []
    run = db.scalar(select(AiRun).where(AiRun.provider == "perplexity"))
    assert run.status == "awaiting_key" and "PERPLEXITY_API_KEY" in run.error
    sr = db.scalar(select(SourceRun).where(SourceRun.source_key == "ai_audit_perplexity"))
    assert sr.status == "awaiting_key" and "PERPLEXITY_API_KEY" in sr.error
    plan = runner.run_week(db, libya(db), providers=copy.copy(provs), dry_run=True, force=True)
    later = {w["provider"]: w for w in plan["awaiting_key"]}
    assert later["perplexity"]["answers"] == 16 and later["perplexity"]["estimated_usd"] == pytest.approx(16 * 0.03)
