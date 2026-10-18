"""AI answers audit providers: request shape, parsing of documented response shapes, status mapping,
fallbacks and cost arithmetic. No network: Anthropic gets a fake client fed SDK-validated fixtures,
OpenAI gets an httpx MockTransport."""
import copy
import json
from datetime import date
from pathlib import Path

import anthropic
import httpx
import pytest
from anthropic.types import Message

from app.ai_audit import providers as P

FIX = Path(__file__).resolve().parent / "fixtures" / "ai_audit"
TODAY = date(2026, 10, 19)
LOCATION = {"city": "Tripoli", "region": "Tripoli", "country": "LY", "timezone": "Africa/Tripoli"}
FULL_LOC = {"type": "approximate", **LOCATION}
OPENAI_KEY = "sk-test-not-a-real-key-0123456789"


def fixture(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def msg(name):
    """A fixture as the SDK's own Message object: fails if the fixture drifts from the SDK schema."""
    return Message.model_validate(fixture(name))


def cfg(key, **over):
    base = {"max_searches": 2, "date_line": True, "location": dict(LOCATION), "weekly_cap_usd": 1.0}
    return {**base, **P.load_prices()[key], **over}


def api_error(cls, status, message):
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    body = {"type": "error", "error": {"type": "invalid_request_error", "message": message}}
    return cls(message, response=httpx.Response(status, request=req, json=body), body=body)


class FakeMessages:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def create(self, **kw):
        self.calls.append(copy.deepcopy(kw))
        item = self.script.pop(0)
        if callable(item):
            item = item(kw)
        if isinstance(item, Exception):
            raise item
        return item


class FakeModels:
    def __init__(self, supported=None):
        self.supported = supported or {}
        self.calls = []

    def retrieve(self, model):
        self.calls.append(model)
        if model not in self.supported:
            raise api_error(anthropic.NotFoundError, 404, f"model: {model}")
        ok = self.supported[model]
        return {"id": model, "capabilities": {"server_tools": {
            "supported": ok, "web_search": {"supported": ok}, "code_execution": {"supported": ok}}}}


class FakeClient:
    def __init__(self, script, supported=None):
        self.messages = FakeMessages(script)
        self.models = FakeModels(supported)


# ---------------------------------------------------------------- Anthropic

def test_anthropic_parses_queries_results_and_citations():
    client = FakeClient([msg("anthropic_ok.json")], {"claude-haiku-5-5": True})
    ans = P.AnthropicProvider(client=client).ask("What is the current security situation in Libya?", "en",
                                                 today=TODAY, cfg=cfg("anthropic"))
    assert ans.status == "ok" and ans.error is None
    assert ans.model == "claude-haiku-5-5"
    assert ans.queries == ["Libya security situation October 2026", "Tripoli clashes 2026"]
    # every result, deduplicated by URL in order of first appearance; the Reuters link came back twice
    assert [s.url for s in ans.searched] == [
        "https://libyaobserver.ly/news/security-update-tripoli",
        "https://www.reuters.com/world/africa/libya-talks-2026-10-14/",
        "https://en.wikipedia.org/wiki/Libya",
        "https://libyaherald.com/2026/10/calm-returns/",
    ]
    assert [s.rank for s in ans.searched] == [1, 2, 3, 4]
    assert ans.searched[0].title == "Security update from Tripoli" and ans.searched[0].date == "October 15, 2026"
    assert ans.searched[1].date == "October 14, 2026"          # filled from its second appearance
    cited = {s.url: s for s in ans.cited}
    assert len(ans.cited) == 2
    assert cited["https://libyaobserver.ly/news/security-update-tripoli"].citations == 2
    assert cited["https://libyaobserver.ly/news/security-update-tripoli"].rank == 1
    assert cited["https://www.reuters.com/world/africa/libya-talks-2026-10-14/"].citations == 1
    assert ans.searches == 2 and ans.input_tokens == 21345 and ans.output_tokens == 812
    assert ans.location_sent == FULL_LOC
    assert "capital has been calm" in ans.answer_text
    # cited_text and the thinking block never reach the answer object
    assert "CITED-TEXT-MUST-NOT-BE-KEPT" not in repr(ans)
    assert "needs recent news" not in repr(ans)


def test_anthropic_request_carries_only_the_date_line_question_and_tool():
    client = FakeClient([msg("anthropic_ok.json"), msg("anthropic_ok.json")], {"claude-haiku-5-5": True})
    prov = P.AnthropicProvider(client=client)
    prov.ask("ما هو الوضع الأمني الحالي في ليبيا؟", "ar", today=TODAY, cfg=cfg("anthropic"))
    kw = client.messages.calls[0]
    assert kw["model"] == "claude-haiku-5-5"
    assert kw["system"] == "Today's date is 2026-10-19."
    assert kw["messages"] == [{"role": "user", "content": "ما هو الوضع الأمني الحالي في ليبيا؟"}]
    assert kw["tools"] == [{"type": "web_search_20250305", "name": "web_search", "max_uses": 2,
                            "user_location": FULL_LOC}]
    assert kw["max_tokens"] == 4000
    assert "thinking" not in kw and "output_config" not in kw     # provider defaults, as the owner sees them
    prov.ask("q", "en", today=TODAY, cfg=cfg("anthropic", date_line=False))
    assert "system" not in client.messages.calls[1]


def test_anthropic_no_search():
    client = FakeClient([msg("anthropic_no_search.json")], {"claude-haiku-5-5": True})
    ans = P.AnthropicProvider(client=client).ask("q", "en", today=TODAY, cfg=cfg("anthropic"))
    assert ans.status == "no_search"
    assert ans.queries == [] and ans.searched == [] and ans.cited == [] and ans.searches == 0
    assert ans.input_tokens == 1180 and ans.answer_text.startswith("Libya has had")


def test_anthropic_refusal():
    client = FakeClient([msg("anthropic_refusal.json")], {"claude-haiku-5-5": True})
    ans = P.AnthropicProvider(client=client).ask("q", "en", today=TODAY, cfg=cfg("anthropic"))
    assert ans.status == "refused"
    assert "general_harms" in ans.error
    assert len(client.messages.calls) == 1                          # a refusal is never retried


def test_anthropic_too_many_requests_inside_a_200_is_rate_limited():
    client = FakeClient([msg("anthropic_rate_limited.json")], {"claude-haiku-5-5": True})
    ans = P.AnthropicProvider(client=client).ask("q", "en", today=TODAY, cfg=cfg("anthropic"))
    assert ans.status == "rate_limited"
    assert ans.queries == ["Kufra news"] and ans.searched == [] and ans.searches == 0


def test_anthropic_search_over_max_uses_is_not_a_query():
    data = fixture("anthropic_ok.json")
    data["content"][7:7] = [
        {"type": "server_tool_use", "id": "srvtoolu_third", "name": "web_search", "input": {"query": "third try"}},
        {"type": "web_search_tool_result", "tool_use_id": "srvtoolu_third",
         "content": {"type": "web_search_tool_result_error", "error_code": "max_uses_exceeded"}},
    ]
    client = FakeClient([Message.model_validate(data)], {"claude-haiku-5-5": True})
    ans = P.AnthropicProvider(client=client).ask("q", "en", today=TODAY, cfg=cfg("anthropic"))
    assert ans.status == "ok" and ans.error is None
    assert ans.queries == ["Libya security situation October 2026", "Tripoli clashes 2026"]
    assert ans.searches == 2


def test_anthropic_http_429_is_rate_limited():
    client = FakeClient([api_error(anthropic.RateLimitError, 429, "rate limit")], {"claude-haiku-5-5": True})
    ans = P.AnthropicProvider(client=client).ask("q", "en", today=TODAY, cfg=cfg("anthropic"))
    assert ans.status == "rate_limited" and "429" in ans.error


def test_anthropic_location_fallback_drops_the_country_and_remembers():
    def reject_ly(kw):
        if "country" in kw["tools"][0]["user_location"]:
            return api_error(anthropic.BadRequestError, 400,
                             "tools.0.user_location.country: unsupported country code 'LY'")
        return msg("anthropic_ok.json")

    client = FakeClient([reject_ly, reject_ly, reject_ly], {"claude-haiku-5-5": True})
    prov = P.AnthropicProvider(client=client)
    ans = prov.ask("q", "en", today=TODAY, cfg=cfg("anthropic"))
    assert ans.status == "ok"
    assert ans.location_sent == {"type": "approximate", "city": "Tripoli", "timezone": "Africa/Tripoli"}
    assert [c["tools"][0]["user_location"].get("country") for c in client.messages.calls] == ["LY", None]
    prov.ask("q2", "en", today=TODAY, cfg=cfg("anthropic"))         # same run: no second wasted call
    assert len(client.messages.calls) == 3
    assert "country" not in client.messages.calls[2]["tools"][0]["user_location"]


def test_anthropic_model_fallback_when_the_tool_is_rejected():
    def tool_rejected(kw):
        if kw["model"] == "claude-haiku-5-5":
            return api_error(anthropic.BadRequestError, 400, "web_search_20250305 is not supported on this model")
        return msg("anthropic_ok.json").model_copy(update={"model": "claude-haiku-4-5"})

    client = FakeClient([tool_rejected, tool_rejected, tool_rejected], {})   # Models API cannot tell
    prov = P.AnthropicProvider(client=client)
    ans = prov.ask("q", "en", today=TODAY, cfg=cfg("anthropic"))
    assert ans.status == "ok" and ans.model == "claude-haiku-4-5"
    assert [c["model"] for c in client.messages.calls] == ["claude-haiku-5-5", "claude-haiku-4-5"]
    assert prov.next_model(cfg("anthropic")) == "claude-haiku-4-5"
    prov.ask("q2", "en", today=TODAY, cfg=cfg("anthropic"))
    assert client.messages.calls[-1]["model"] == "claude-haiku-4-5"


def test_anthropic_models_api_capability_skips_a_model_without_web_search():
    client = FakeClient([msg("anthropic_ok.json")], {"claude-haiku-5-5": False, "claude-haiku-4-5": True})
    ans = P.AnthropicProvider(client=client).ask("q", "en", today=TODAY, cfg=cfg("anthropic"))
    assert ans.status == "ok"
    assert [c["model"] for c in client.messages.calls] == ["claude-haiku-4-5"]


def test_anthropic_other_400_is_an_error_without_fallback():
    client = FakeClient([api_error(anthropic.BadRequestError, 400, "web search is not enabled for this organization")],
                        {"claude-haiku-5-5": True})
    ans = P.AnthropicProvider(client=client).ask("q", "en", today=TODAY, cfg=cfg("anthropic"))
    assert ans.status == "error" and ans.error.startswith("HTTP 400")
    assert len(client.messages.calls) == 1


def test_anthropic_pause_turn_is_continued_with_the_paused_content():
    client = FakeClient([msg("anthropic_pause_1.json"), msg("anthropic_pause_2.json")], {"claude-haiku-5-5": True})
    ans = P.AnthropicProvider(client=client).ask("q", "en", today=TODAY, cfg=cfg("anthropic"))
    assert ans.status == "ok"
    assert ans.queries == ["Libya elections news", "Libya municipal elections 2026"]
    assert [s.url for s in ans.searched] == ["https://hnec.ly/news/1", "https://www.alwasat.ly/news/libya/elections"]
    assert [(s.url, s.citations, s.date) for s in ans.cited] == [("https://hnec.ly/news/1", 1, "October 12, 2026")]
    assert ans.searches == 2 and ans.input_tokens == 23000 and ans.output_tokens == 700
    second = client.messages.calls[1]
    assert second["messages"][0] == {"role": "user", "content": "q"}
    assert second["messages"][1]["role"] == "assistant"
    assert [b.type for b in second["messages"][1]["content"]] == ["server_tool_use", "web_search_tool_result"]
    assert second["tools"] == client.messages.calls[0]["tools"]


def test_anthropic_pause_turn_is_bounded():
    client = FakeClient([msg("anthropic_pause_1.json")] * (P.MAX_CONTINUATIONS + 1), {"claude-haiku-5-5": True})
    ans = P.AnthropicProvider(client=client).ask("q", "en", today=TODAY, cfg=cfg("anthropic"))
    assert len(client.messages.calls) == P.MAX_CONTINUATIONS + 1
    assert ans.status == "error" and "paused" in ans.error
    assert ans.searches == P.MAX_CONTINUATIONS + 1                  # cost of what ran is still reported


def test_anthropic_pause_turn_is_not_continued_past_the_budget():
    # the runner passes cap minus spent; one more request (2 searches = USD 0.02 alone) would not fit
    client = FakeClient([msg("anthropic_pause_1.json")] * 4, {"claude-haiku-5-5": True})
    ans = P.AnthropicProvider(client=client).ask("q", "en", today=TODAY, cfg=cfg("anthropic", answer_budget_usd=0.025))
    assert len(client.messages.calls) == 1
    assert ans.status == "error" and "weekly cap" in ans.error and ans.searches >= 1
    # with room left it continues as usual
    client = FakeClient([msg("anthropic_pause_1.json"), msg("anthropic_pause_2.json")], {"claude-haiku-5-5": True})
    ans = P.AnthropicProvider(client=client).ask("q", "en", today=TODAY, cfg=cfg("anthropic", answer_budget_usd=0.5))
    assert ans.status == "ok" and len(client.messages.calls) == 2


def test_a_dearer_fallback_model_is_not_started_past_the_budget():
    def tool_rejected(kw):
        if kw["model"] == "claude-haiku-5-5":
            return api_error(anthropic.BadRequestError, 400, "web_search_20250305 is not supported on this model")
        return msg("anthropic_ok.json").model_copy(update={"model": "claude-haiku-4-5"})

    # Haiku 5.5 fits USD 0.05 (about 0.025); Haiku 4.5 would not (about 0.07): it is never called
    client = FakeClient([tool_rejected, tool_rejected], {})
    ans = P.AnthropicProvider(client=client).ask("q", "en", today=TODAY, cfg=cfg("anthropic", answer_budget_usd=0.05))
    assert [c["model"] for c in client.messages.calls] == ["claude-haiku-5-5"]
    assert ans.status == "error" and "weekly cap" in ans.error


def test_timeouts_are_flagged_cost_unknown():
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    client = FakeClient([anthropic.APITimeoutError(request=req)], {"claude-haiku-5-5": True})
    ans = P.AnthropicProvider(client=client).ask("q", "en", today=TODAY, cfg=cfg("anthropic"))
    assert ans.status == "error" and ans.cost_unknown is True
    client = FakeClient([api_error(anthropic.RateLimitError, 429, "rate limit")], {"claude-haiku-5-5": True})
    assert P.AnthropicProvider(client=client).ask("q", "en", today=TODAY, cfg=cfg("anthropic")).cost_unknown is False


def sdk_client(handler):
    """The real anthropic SDK over a mock transport (the SDK ships its own httpx fork, httpx2)."""
    try:
        import httpx2 as sdk_httpx
    except ImportError:  # older SDKs use httpx itself
        sdk_httpx = httpx
    return anthropic.Anthropic(api_key="test-key-not-real", max_retries=0,
                               http_client=sdk_httpx.Client(transport=sdk_httpx.MockTransport(handler))), sdk_httpx


def test_anthropic_through_the_real_sdk_pause_turn_and_location_fallback():
    pages = [fixture("anthropic_pause_1.json"), fixture("anthropic_pause_2.json")]
    bodies = []

    def handler(request):
        if request.url.path.startswith("/v1/models/"):
            return sdk_httpx.Response(200, json={
                "type": "model", "id": request.url.path.rsplit("/", 1)[1], "display_name": "Claude",
                "created_at": "2026-10-07T00:00:00Z",
                "capabilities": {"server_tools": {"supported": True, "web_search": {"supported": True},
                                                  "code_execution": {"supported": True}}}})
        body = json.loads(request.content)
        bodies.append(body)
        if "country" in body["tools"][0]["user_location"]:
            return sdk_httpx.Response(400, json={"type": "error", "error": {
                "type": "invalid_request_error", "message": "tools.0.user_location.country: unsupported value 'LY'"}})
        return sdk_httpx.Response(200, json=pages.pop(0))

    client, sdk_httpx = sdk_client(handler)
    ans = P.AnthropicProvider(client=client).ask("What is the latest news on elections in Libya?", "en",
                                                 today=TODAY, cfg=cfg("anthropic"))
    assert ans.status == "ok" and ans.searches == 2 and ans.input_tokens == 23000
    assert ans.location_sent == {"type": "approximate", "city": "Tripoli", "timezone": "Africa/Tripoli"}
    assert len(bodies) == 3                                         # LY refused, then first page, then continuation
    cont = bodies[2]["messages"]
    assert cont[1]["role"] == "assistant"
    assert [b["type"] for b in cont[1]["content"]] == ["server_tool_use", "web_search_tool_result"]
    assert cont[1]["content"][1]["content"][0]["encrypted_content"] == "EqgfCioIARgBIiQpause1"   # sent back unchanged
    assert bodies[2]["tools"] == bodies[1]["tools"]


def test_anthropic_without_key_is_unavailable(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    prov = P.AnthropicProvider()
    assert prov.available() is False
    ans = prov.ask("q", "en", today=TODAY, cfg=cfg("anthropic"))
    assert ans.status == "error" and "not set" in ans.error
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-0000000000")
    assert P.AnthropicProvider().available() is True


# ---------------------------------------------------------------- OpenAI

def openai_http(responses):
    """httpx client whose transport answers from a list of (status, json) and records each request."""
    seen = []
    queue = list(responses)

    def handler(request):
        seen.append(request)
        status, body = queue.pop(0)
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_openai_parses_queries_sources_and_citations(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", OPENAI_KEY)
    http, seen = openai_http([(200, fixture("openai_ok.json"))])
    ans = P.OpenAIProvider(http=http).ask("ما هو الوضع الأمني الحالي في ليبيا؟", "ar", today=TODAY,
                                          cfg=cfg("openai"))
    assert ans.status == "ok" and ans.error is None
    assert ans.model == "gpt-6-luna"
    assert ans.queries == ["الوضع الأمني في ليبيا أكتوبر 2026", "ليبيا الوضع الأمني", "طرابلس اشتباكات"]
    # sources only (open_page is not a source), pseudo-sources dropped, deduplicated
    assert [s.url for s in ans.searched] == [
        "https://www.alwasat.ly/news/libya/1",
        "https://www.aljazeera.net/news/2026/10/16/libya",
        "https://libyaobserver.ly/ar/news/3",
    ]
    assert all(s.title is None for s in ans.searched)
    assert [(s.url, s.citations, s.title) for s in ans.cited] == [
        ("https://www.alwasat.ly/news/libya/1?utm_source=openai", 2, "بوابة الوسط"),
        ("https://www.aljazeera.net/news/2026/10/16/libya", 1, "الجزيرة نت"),
    ]
    assert ans.searches == 2                                        # search actions, not open_page
    assert ans.input_tokens == 18000 and ans.output_tokens == 950
    assert ans.location_sent == FULL_LOC
    assert "هدوءا" in ans.answer_text


def test_openai_request_body(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", OPENAI_KEY)
    http, seen = openai_http([(200, fixture("openai_ok.json"))])
    P.OpenAIProvider(http=http).ask("What is the latest news from Kufra?", "en", today=TODAY, cfg=cfg("openai"))
    req = seen[0]
    assert str(req.url) == "https://api.openai.com/v1/responses"
    assert req.headers["authorization"] == f"Bearer {OPENAI_KEY}"
    body = json.loads(req.content)
    assert body["model"] == "gpt-6-luna"
    assert body["input"] == "What is the latest news from Kufra?"
    assert body["instructions"] == "Today's date is 2026-10-19."
    assert body["tools"] == [{"type": "web_search", "user_location": FULL_LOC, "search_context_size": "medium"}]
    assert body["include"] == ["web_search_call.action.sources"]
    assert body["max_tool_calls"] == 2
    assert body["store"] is False
    assert body["reasoning"] == {"effort": "low"}
    assert "filters" not in json.dumps(body)


def test_openai_no_search(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", OPENAI_KEY)
    http, _ = openai_http([(200, fixture("openai_no_search.json"))])
    ans = P.OpenAIProvider(http=http).ask("q", "en", today=TODAY, cfg=cfg("openai", date_line=False))
    assert ans.status == "no_search" and ans.searches == 0 and ans.searched == [] and ans.cited == []


def test_openai_date_line_off_sends_no_instructions(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", OPENAI_KEY)
    http, seen = openai_http([(200, fixture("openai_no_search.json"))])
    P.OpenAIProvider(http=http).ask("q", "en", today=TODAY, cfg=cfg("openai", date_line=False))
    assert "instructions" not in json.loads(seen[0].content)


def test_openai_refusal(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", OPENAI_KEY)
    http, _ = openai_http([(200, fixture("openai_refusal.json"))])
    ans = P.OpenAIProvider(http=http).ask("q", "en", today=TODAY, cfg=cfg("openai"))
    assert ans.status == "refused"


def test_openai_429_is_rate_limited(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", OPENAI_KEY)
    body = {"error": {"message": "Rate limit reached for gpt-6-luna on requests per min.",
                      "type": "requests", "param": None, "code": "rate_limit_exceeded"}}
    http, _ = openai_http([(429, body)])
    ans = P.OpenAIProvider(http=http).ask("q", "en", today=TODAY, cfg=cfg("openai"))
    assert ans.status == "rate_limited" and "429" in ans.error


def test_openai_errors_never_carry_the_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", OPENAI_KEY)
    body = {"error": {"message": f"Incorrect API key provided: {OPENAI_KEY}. You can find your API key at ...",
                      "type": "invalid_request_error", "param": None, "code": "invalid_api_key"}}
    http, _ = openai_http([(401, body)])
    ans = P.OpenAIProvider(http=http).ask("q", "en", today=TODAY, cfg=cfg("openai"))
    assert ans.status == "error"
    assert OPENAI_KEY not in ans.error and "sk-test" not in ans.error
    assert "q" != ans.error and "user_location" not in ans.error   # no request echo


def test_openai_without_key_is_unavailable_and_makes_no_call(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    http, seen = openai_http([])
    prov = P.OpenAIProvider(http=http)
    assert prov.available() is False
    ans = prov.ask("q", "en", today=TODAY, cfg=cfg("openai"))
    assert ans.status == "error" and "not set" in ans.error and seen == []


def test_openai_timeout_is_an_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", OPENAI_KEY)

    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    ans = P.OpenAIProvider(http=http).ask("q", "en", today=TODAY, cfg=cfg("openai"))
    assert ans.status == "error" and "ReadTimeout" in ans.error
    assert ans.cost_unknown is True        # may still be billed: the runner charges the estimate


# ---------------------------------------------------------------- prices, registry

def test_estimate_usd_arithmetic():
    prices = P.load_prices()
    # Haiku 5.5: 2 searches x $10/1000 + 30k x $0.10/M + 1.5k x $0.50/M
    assert P.estimate_usd(prices, "anthropic", "claude-haiku-5-5", 2, 30_000, 1_500) == pytest.approx(0.02375)
    # over the 100k-token step the whole request pays $0.50 / $2.50
    assert P.estimate_usd(prices, "anthropic", "claude-haiku-5-5", 2, 150_000, 1_500) == pytest.approx(
        0.02 + 0.075 + 0.00375)
    assert P.estimate_usd(prices, "anthropic", "claude-haiku-4-5", 2, 30_000, 1_500) == pytest.approx(0.0575)
    assert P.estimate_usd(prices, "openai", "gpt-6-luna", 2, 30_000, 1_500) == pytest.approx(0.02375)
    assert P.estimate_usd(prices, "openai", "gpt-6-luna-2026-05-18", 1, 0, 0) == pytest.approx(0.01)   # snapshot id
    # an unknown model is costed at the dearest listed rate, never the cheapest
    assert P.estimate_usd(prices, "anthropic", "claude-unknown", 0, 1_000_000, 0) == pytest.approx(1.0)
    assert P.estimate_usd(prices, "openai", "gpt-6-luna", 0, 0, 0) == 0


def test_a_full_week_fits_the_cap():
    """2 providers x 8 questions x 2 languages at the config estimate (30k in, 1.5k out, 2 searches)."""
    prices = P.load_prices()
    week = sum(P.estimate_usd(prices, k, P.load_prices()[k]["models"][0]["id"], 2, 30_000, 1_500) * 16
               for k in ("anthropic", "openai"))
    assert week == pytest.approx(0.76)
    assert week <= 1.0


def test_price_file_is_complete():
    prices = P.load_prices()
    assert isinstance(prices["as_of"], str)
    assert prices["anthropic"]["tool"] == "web_search_20250305"
    for key in ("anthropic", "openai"):
        block = prices[key]
        assert block["search_per_1000_usd"] == 10.0
        assert block["models"] and all({"id", "input_per_mtok", "output_per_mtok"} <= set(m) for m in block["models"])
        assert block["sources"] and all(u.startswith(("https://platform.claude.com/", "https://developers.openai.com/"))
                                        for u in block["sources"])
    assert prices["anthropic"]["models"][0]["id"] == "claude-haiku-5-5"
    assert prices["openai"]["models"][0]["id"] == "gpt-6-luna"


def test_get_providers_follows_the_config():
    both = P.get_providers({"providers": {"anthropic": {"enabled": True}, "openai": {"enabled": True}}})
    assert list(both) == ["anthropic", "openai"]
    assert both["anthropic"].label == "Claude (Anthropic)" and both["openai"].label == "ChatGPT (OpenAI)"
    assert list(P.get_providers({"providers": {"anthropic": {"enabled": False}, "openai": {"enabled": True}}})) == ["openai"]
    assert P.get_providers({}) == {}


def test_safe_message_redacts_keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "abcdefgh-secret-value")
    out = P.safe_message("bad key abcdefgh-secret-value and sk-ant-api03-XYZ123 and sk-proj-abc***def " + "x" * 500)
    assert "abcdefgh-secret-value" not in out and "sk-ant" not in out and "sk-proj" not in out
    assert len(out) <= 300
