"""The two assistants the AI answers audit asks: Claude (Anthropic Messages API, web search server tool)
and ChatGPT (OpenAI Responses API, hosted web_search tool).

Each provider asks one question in a new conversation and returns a ProviderAnswer: the assistant's own
search queries, every result its search tool returned ("searched"), the links its answer cites ("cited"),
token and search usage, and the location it sent. What the request carries is fixed by the owner's
decisions (docs/research/ai_answers_audit_scope.md section 4):
- a one-line system prompt with today's date (when cfg date_line is true) and nothing else; the question
  is the only user message; the assistant is never asked to cite; no domain filters;
- at most cfg max_searches searches (Anthropic max_uses, OpenAI max_tool_calls);
- an explicit location (Tripoli, Libya). OpenAI defaults to the United States without one. Anthropic may
  reject the country code LY with a 400; the provider then resends city and timezone only and records
  what it sent.

Privacy: answer_text stays in memory so the runner can measure the answer's language and length; it is
never stored, and Anthropic's cited_text is never read into a Source. Errors are short and never carry a
key or the request. Domain matching is not done here (that is the core matcher's job): URLs come back as
the API gave them, minus OpenAI's real-time pseudo-sources.

The facts these adapters rely on, with the pages they were read on, are in config/ai_audit_prices.yaml."""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date

import yaml

from .. import settings

log = logging.getLogger("desert_watch.ai_audit")

PRICES_FILE = "ai_audit_prices.yaml"
DEFAULT_LOCATION = {"city": "Tripoli", "region": "Tripoli", "country": "LY", "timezone": "Africa/Tripoli"}
DEFAULT_MAX_SEARCHES = 2

ANTHROPIC_TOOL = "web_search_20250305"     # basic web search: every result reaches the model (no dynamic filtering)
ANTHROPIC_TIMEOUT = 120.0
ANTHROPIC_MAX_TOKENS = 4000                # Haiku 5.5 thinks by default and thinking counts toward max_tokens
MAX_CONTINUATIONS = 3                      # pause_turn continuations per answer

OPENAI_URL = "https://api.openai.com/v1/responses"
OPENAI_TIMEOUT = 120.0
OPENAI_MAX_OUTPUT_TOKENS = 4000
PSEUDO_SOURCES = ("oai-sports", "oai-weather", "oai-finance")   # real-time feeds listed among sources
OPENAI_POLICY_CODES = {"bio_policy", "misalignment_policy_violation", "invalid_prompt"}


@dataclass
class Source:
    url: str
    title: str | None = None
    date: str | None = None
    rank: int = 0           # 1-based order of first appearance in this answer
    citations: int = 0      # cited links: number of citation spans pointing at the URL


@dataclass
class ProviderAnswer:
    status: str             # ok | no_search | refused | rate_limited | error
    model: str
    queries: list[str] = field(default_factory=list)
    searched: list[Source] = field(default_factory=list)
    cited: list[Source] = field(default_factory=list)
    answer_text: str = ""   # in memory only, never stored
    input_tokens: int = 0
    output_tokens: int = 0
    searches: int = 0       # billed searches (Anthropic) or search calls (OpenAI)
    location_sent: dict = field(default_factory=dict)
    error: str | None = None
    # True when a request may have been billed but its usage never came back (a timeout or a dropped
    # connection after sending). The runner then charges the pre-call estimate, so the cap stays safe.
    cost_unknown: bool = False


# ---------------------------------------------------------------- prices

def load_prices() -> dict:
    """config/ai_audit_prices.yaml as a dict ({} when the file is missing)."""
    path = settings.CONFIG_DIR / PRICES_FILE
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _price_block(prices: dict, provider_key: str) -> dict:
    if isinstance(prices.get(provider_key), dict):
        return prices[provider_key]
    if isinstance(prices.get("providers"), dict) and isinstance(prices["providers"].get(provider_key), dict):
        return prices["providers"][provider_key]
    return prices if "models" in prices else {}


def model_rates(prices: dict, provider_key: str, model: str) -> dict:
    """The price entry for a model: exact id, else a listed id the reported model starts with (a dated
    snapshot of it), else the most expensive listed entry so an unknown model is never under-costed."""
    models = [m for m in (_price_block(prices, provider_key).get("models") or []) if isinstance(m, dict)]
    if not models:
        raise KeyError(f"no prices for provider {provider_key!r}")
    for m in models:
        if m.get("id") == model:
            return m
    for m in sorted(models, key=lambda m: -len(str(m.get("id", "")))):
        if model and str(model).startswith(str(m.get("id"))):
            return m
    return max(models, key=lambda m: (float(m.get("input_per_mtok", 0)), float(m.get("output_per_mtok", 0))))


def estimate_usd(prices: dict, provider_key: str, model: str, searches: int, input_tokens: int,
                 output_tokens: int) -> float:
    """Dollar cost of one answer: searches x the per-search fee + tokens at the model's rates. When the
    model has a long-context step and input_tokens is above it, the higher rates apply to everything (an
    over-estimate when the tokens came from several pause_turn requests, each priced on its own)."""
    block = _price_block(prices, provider_key)
    rates = model_rates(prices, provider_key, model)
    rin, rout = float(rates.get("input_per_mtok", 0)), float(rates.get("output_per_mtok", 0))
    long = rates.get("long_context") or {}
    if long and int(input_tokens or 0) > int(long.get("above_input_tokens", 0) or 0):
        rin = float(long.get("input_per_mtok", rin))
        rout = float(long.get("output_per_mtok", rout))
    cost = (int(searches or 0) * float(block.get("search_per_1000_usd", 0)) / 1000.0
            + int(input_tokens or 0) * rin / 1_000_000 + int(output_tokens or 0) * rout / 1_000_000)
    return round(cost, 6)


# ---------------------------------------------------------------- shared helpers

_KEYLIKE = re.compile(r"\b(?:sk-[A-Za-z0-9_\-*]{3,}|sess-[A-Za-z0-9_\-]{8,})")
_KEY_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY")


def safe_message(msg, limit: int = 300) -> str:
    """One short line with any key (or key-looking string) removed."""
    s = " ".join(str(msg or "").split())
    for name in _KEY_ENV:
        v = os.environ.get(name)
        if v and len(v) >= 8:
            s = s.replace(v, "[redacted]")
    return _KEYLIKE.sub("[redacted]", s)[:limit]


def _as_dict(obj) -> dict:
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    return dict(getattr(obj, "__dict__", {}) or {})


def _location(loc: dict | None) -> dict:
    loc = loc or DEFAULT_LOCATION
    out = {"type": "approximate"}
    for k in ("city", "region", "country", "timezone"):
        if loc.get(k):
            out[k] = str(loc[k])
    return out


def _location_without_country(loc: dict) -> dict:
    out = {"type": "approximate"}
    for k in ("city", "timezone"):
        if loc.get(k):
            out[k] = loc[k]
    return out


def _provider_block(cfg: dict, key: str) -> dict:
    """The provider's block from ai_audit_prices.yaml: merged into cfg at top level (the runner's shape),
    nested under cfg[key], or read from the file."""
    cfg = cfg or {}
    if cfg.get("models"):
        return cfg
    if isinstance(cfg.get(key), dict) and cfg[key].get("models"):
        return cfg[key]
    return _price_block(load_prices(), key)


def _model_ids(block: dict, default: str) -> list[str]:
    ids = [str(m["id"]) for m in (block.get("models") or []) if isinstance(m, dict) and m.get("id")]
    return ids or [default]


def _date_line(cfg: dict, today: date) -> str | None:
    return f"Today's date is {today.strftime('%Y-%m-%d')}." if (cfg or {}).get("date_line", True) else None


def _max_searches(cfg: dict) -> int:
    try:
        return max(1, int((cfg or {}).get("max_searches", DEFAULT_MAX_SEARCHES)))
    except (TypeError, ValueError):
        return DEFAULT_MAX_SEARCHES


class _Collector:
    """Searched and cited links, deduplicated by exact URL in order of first appearance."""

    def __init__(self):
        self.searched: dict[str, Source] = {}
        self.cited: dict[str, Source] = {}

    def search_result(self, url, title=None, date_=None):
        if not url:
            return
        if url not in self.searched:
            self.searched[url] = Source(url=url, title=title or None, date=date_ or None, rank=len(self.searched) + 1)
        else:
            s = self.searched[url]
            s.title, s.date = s.title or title or None, s.date or date_ or None

    def citation(self, url, title=None):
        if not url:
            return
        if url not in self.cited:
            hit = self.searched.get(url)
            self.cited[url] = Source(url=url, title=title or (hit.title if hit else None),
                                     date=hit.date if hit else None, rank=len(self.cited) + 1)
        self.cited[url].citations += 1


def _unique(items) -> list[str]:
    seen, out = set(), []
    for q in items:
        q = str(q).strip() if q is not None else ""
        if q and q not in seen:
            seen.add(q)
            out.append(q)
    return out


# ---------------------------------------------------------------- Anthropic

def _anthropic_error_text(e) -> str:
    body = getattr(e, "body", None)
    if isinstance(body, dict):
        err = body.get("error") if isinstance(body.get("error"), dict) else body
        if err.get("message"):
            return safe_message(err["message"])
    return safe_message(getattr(e, "message", None) or str(e) or type(e).__name__)


def _is_location_error(msg: str) -> bool:
    m = msg.lower()
    return "user_location" in m or "country" in m


def _is_tool_rejection(msg: str) -> bool:
    m = msg.lower()
    if "not enabled" in m or "disabled" in m:      # the organisation switched web search off: no model will do
        return False
    return ("web_search" in m or "web search" in m or "tool" in m) and any(
        w in m for w in ("not supported", "does not support", "unsupported", "not available", "not compatible"))


class AnthropicProvider:
    key = "anthropic"
    label = "Claude (Anthropic)"

    def __init__(self, client=None):
        self._client = client
        self._injected = client is not None
        self._no_country = False           # LY was rejected once: send city + timezone from then on
        self._rejected: set[str] = set()   # models that refused the web search tool
        self._capability: dict[str, bool | None] = {}

    def available(self) -> bool:
        return self._injected or bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))

    def next_model(self, cfg: dict) -> str:
        """The model the next ask() will try first (for the runner's pre-call estimate)."""
        ids = _model_ids(_provider_block(cfg, self.key), "claude-haiku-5-5")
        return next((m for m in ids if m not in self._rejected), ids[-1])

    def _get_client(self):
        if self._client is None:
            import anthropic
            # No SDK retries: a timed-out request may still be billed, and a silent retry would double the
            # cost with no usage coming back. A failed answer is recorded and the run moves on.
            self._client = anthropic.Anthropic(timeout=ANTHROPIC_TIMEOUT, max_retries=0)
        return self._client

    def _supports_web_search(self, model: str) -> bool | None:
        """Models API capabilities.server_tools.web_search.supported; None when it cannot be read."""
        if model not in self._capability:
            try:
                info = _as_dict(self._get_client().models.retrieve(model))
                caps = (info.get("capabilities") or {}).get("server_tools") or {}
                ws = caps.get("web_search") or {}
                self._capability[model] = ws.get("supported") if isinstance(ws.get("supported"), bool) else None
            except Exception as e:  # noqa: BLE001 - unknown is fine: the call itself will tell
                log.info("ai audit: capability check for %s failed: %s", model, safe_message(e))
                self._capability[model] = None
        return self._capability[model]

    def ask(self, question: str, lang: str, *, today: date, cfg: dict) -> ProviderAnswer:
        block = _provider_block(cfg, self.key)
        models = _model_ids(block, "claude-haiku-5-5")
        request = block.get("request") or {}
        max_tokens = int(request.get("max_tokens") or ANTHROPIC_MAX_TOKENS)
        full_loc = _location((cfg or {}).get("location"))
        system = _date_line(cfg, today)
        max_uses = _max_searches(cfg)
        budget = (cfg or {}).get("answer_budget_usd")   # the runner's cap minus spent, for continuations
        if not self.available():
            return ProviderAnswer(status="error", model=models[0], error="ANTHROPIC_API_KEY is not set")
        last_error, last_loc = None, full_loc
        for model in models:
            if model in self._rejected:
                continue
            if self._supports_web_search(model) is False:
                self._rejected.add(model)
                last_error = f"{model} does not support web search (Models API)"
                continue
            if budget is not None and not _model_fits(cfg, block, self.key, model, max_uses, max_tokens, budget):
                # a fallback model can cost several times the first one: never start it past the cap
                return ProviderAnswer(status="error", model=model, location_sent=last_loc,
                                      error=f"{model} not tried: one answer could pass the weekly cap")
            while True:
                loc = _location_without_country(full_loc) if self._no_country else full_loc
                last_loc = loc
                try:
                    return self._answer(model, question, loc, max_uses, max_tokens, system, block, budget)
                except Exception as e:  # noqa: BLE001 - every failure becomes a status
                    status = getattr(e, "status_code", None)
                    msg = _anthropic_error_text(e)
                    if status == 400 and _is_location_error(msg) and "country" in loc and not self._no_country:
                        log.warning("ai audit: Anthropic rejected the location; resending without the country (%s)", msg)
                        self._no_country = True
                        continue
                    if status == 404 or (status == 400 and _is_tool_rejection(msg)):
                        log.warning("ai audit: %s refused the web search tool; trying the next model (%s)", model, msg)
                        self._rejected.add(model)
                        last_error = f"{model}: {msg}"
                        break
                    return _anthropic_failure(model, loc, e, msg)
        return ProviderAnswer(status="error", model=models[-1], location_sent=last_loc,
                              error=safe_message(last_error or "no listed model accepts the web search tool"))

    def _answer(self, model, question, loc, max_uses, max_tokens, system, block=None, budget=None) -> ProviderAnswer:
        client = self._get_client()
        tool = {"type": ANTHROPIC_TOOL, "name": "web_search", "max_uses": max_uses, "user_location": loc}
        user = {"role": "user", "content": question}
        kw = {"model": model, "max_tokens": max_tokens, "messages": [user], "tools": [tool]}
        if system:
            kw["system"] = system
        resp = client.messages.create(**kw)            # a failure here goes to ask() (fallbacks)
        pages = [_as_dict(resp)]
        content = list(getattr(resp, "content", None) or pages[0].get("content") or [])
        error = None
        unknown = False
        continued = 0
        while pages[-1].get("stop_reason") == "pause_turn":
            if continued >= MAX_CONTINUATIONS:
                error = f"still paused after {MAX_CONTINUATIONS} continuations"
                break
            if budget is not None and not _continuation_fits(block, model, pages, max_uses, max_tokens, budget):
                error = "paused and not continued: one more request could pass the weekly cap"
                break
            continued += 1
            try:
                resp = client.messages.create(**dict(kw, messages=[user, {"role": "assistant", "content": content}]))
            except Exception as e:  # noqa: BLE001 - keep what the first requests returned (and cost)
                error = f"continuation failed: {_anthropic_error_text(e)}"
                unknown = getattr(e, "status_code", None) is None    # a timeout may still be billed
                break
            page = _as_dict(resp)
            pages.append(page)
            content += list(getattr(resp, "content", None) or page.get("content") or [])
        ans = parse_anthropic(pages, model, loc, error)
        ans.cost_unknown = unknown
        return ans


def _pages_usage(pages: list[dict]) -> tuple[int, int, int, int]:
    """(input tokens, output tokens, billed searches, the last request's input + output) over the pages."""
    tin = tout = searches = last = 0
    for page in pages:
        u = page.get("usage") or {}
        pin = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
        pout = int(u.get("output_tokens") or 0)
        tin, tout, last = tin + pin, tout + pout, pin + pout
        searches += int((u.get("server_tool_use") or {}).get("web_search_requests") or 0)
    return tin, tout, searches, last


def _model_fits(cfg: dict, block: dict, key: str, model: str, max_uses: int, max_tokens: int, budget) -> bool:
    """Whether one answer from this model, sized as the runner's pre-call estimate (config estimate input
    tokens, max_uses searches, max_tokens out), fits the budget the runner gave this answer."""
    try:
        tin = int(((cfg or {}).get("estimate") or {}).get("input_tokens", 30000))
        return estimate_usd(block or {}, key, model, max_uses, tin, max_tokens) <= float(budget) + 1e-6
    except Exception:  # noqa: BLE001 - no prices to judge by: spend nothing
        return False


def _continuation_fits(block, model: str, pages: list[dict], max_uses: int, max_tokens: int, budget) -> bool:
    """Whether the answer so far plus one more full request (the whole context sent again, max_uses more
    searches, max_tokens out) stays within the budget the runner gave this answer (cap minus spent)."""
    try:
        tin, tout, searches, last = _pages_usage(pages)
        so_far = estimate_usd(block or {}, AnthropicProvider.key, model, searches, tin, tout)
        more = estimate_usd(block or {}, AnthropicProvider.key, model, max_uses, last, max_tokens)
        return so_far + more <= float(budget) + 1e-9
    except Exception:  # noqa: BLE001 - no prices to judge by: spend nothing more
        return False


def _anthropic_failure(model, loc, e, msg) -> ProviderAnswer:
    status = getattr(e, "status_code", None)
    if status == 429:
        st, err = "rate_limited", f"HTTP 429: {msg}"
    elif status is not None:
        st, err = "error", f"HTTP {status}: {msg}"
    else:
        st, err = "error", f"{type(e).__name__}: {msg}"
    log.warning("ai audit: Anthropic call failed (%s)", err)
    # no HTTP status: a timeout or a dropped connection, after which the request may still be billed
    return ProviderAnswer(status=st, model=model, location_sent=loc, error=safe_message(err),
                          cost_unknown=status is None)


def parse_anthropic(pages: list[dict], model: str, loc: dict, error: str | None = None) -> ProviderAnswer:
    """One answer from the Messages API response(s): the first, then any pause_turn continuations."""
    col = _Collector()
    uses, texts, search_errors = [], [], []
    error_by_use: dict[str, str] = {}
    ok_results = 0
    tin = tout = billed = 0
    billed_seen = False
    for page in pages:
        for b in page.get("content") or []:
            b = _as_dict(b)
            t = b.get("type")
            if t == "server_tool_use" and b.get("name") == "web_search":
                uses.append((b.get("id"), (b.get("input") or {}).get("query")))
            elif t == "web_search_tool_result":
                c = b.get("content")
                if isinstance(c, list):
                    ok_results += 1
                    for r in c:
                        r = _as_dict(r)
                        if r.get("type", "web_search_result") == "web_search_result":
                            col.search_result(r.get("url"), r.get("title"), r.get("page_age"))
                elif isinstance(c, dict):
                    code = c.get("error_code") or "unknown"
                    search_errors.append(code)
                    error_by_use[b.get("tool_use_id")] = code
            elif t == "text":
                texts.append(b.get("text") or "")
                for cit in b.get("citations") or []:
                    cit = _as_dict(cit)
                    if cit.get("type") == "web_search_result_location":
                        col.citation(cit.get("url"), cit.get("title"))   # cited_text is never read
        u = page.get("usage") or {}
        tin += int(u.get("input_tokens") or 0) + int(u.get("cache_creation_input_tokens") or 0) \
            + int(u.get("cache_read_input_tokens") or 0)
        tout += int(u.get("output_tokens") or 0)
        stu = u.get("server_tool_use") or {}
        if "web_search_requests" in stu:
            billed_seen = True
            billed += int(stu.get("web_search_requests") or 0)
    if not billed_seen:
        billed = ok_results
    errors = [c for c in search_errors if c != "max_uses_exceeded"]
    # a search refused for going over max_uses never ran: the assistant wrote it, but it is not a search made
    queries = [q for uid, q in uses if error_by_use.get(uid) != "max_uses_exceeded"]
    used_tool = bool(uses)
    stop = pages[-1].get("stop_reason") if pages else None
    if stop == "refusal":
        cat = (pages[-1].get("stop_details") or {}).get("category")
        status, error = "refused", error or f"model declined ({cat or 'no category'})"
    elif error:
        status = "error"
    elif not ok_results and "too_many_requests" in errors:
        status, error = "rate_limited", "web search: too_many_requests"
    elif not ok_results and errors:
        status, error = "error", "web search failed: " + ", ".join(sorted(set(errors)))
    elif not used_tool:
        status = "no_search"
    else:
        status = "ok"
    if stop == "max_tokens":
        log.info("ai audit: %s answer reached max_tokens", model)
    return ProviderAnswer(
        status=status, model=str((pages[0].get("model") if pages else None) or model),
        queries=_unique(queries), searched=list(col.searched.values()), cited=list(col.cited.values()),
        answer_text="\n".join(t for t in texts if t), input_tokens=tin, output_tokens=tout, searches=billed,
        location_sent=dict(loc), error=safe_message(error) if error else None)


# ---------------------------------------------------------------- OpenAI

def _real_source(s: dict) -> str | None:
    """A source's URL, or None for OpenAI's real-time pseudo-sources (oai-sports, oai-weather, oai-finance)
    and anything that is not an http(s) URL."""
    if s.get("type") not in (None, "url"):
        return None
    url = str(s.get("url") or "").strip()
    name = str(s.get("name") or "")
    if any(p in url or p in name for p in PSEUDO_SOURCES):
        return None
    return url if url.lower().startswith(("http://", "https://")) else None


def _openai_error(resp) -> tuple[str | None, str]:
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        body = None
    err = body.get("error") if isinstance(body, dict) and isinstance(body.get("error"), dict) else {}
    return err.get("code") or err.get("type"), safe_message(err.get("message") or f"HTTP {resp.status_code}")


class OpenAIProvider:
    key = "openai"
    label = "ChatGPT (OpenAI)"

    def __init__(self, http=None):
        self._http = http
        self._rejected: set[str] = set()

    def available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def next_model(self, cfg: dict) -> str:
        ids = _model_ids(_provider_block(cfg, self.key), "gpt-6-luna")
        return next((m for m in ids if m not in self._rejected), ids[-1])

    def _post(self, body: dict, key: str):
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        if self._http is not None:
            return self._http.post(OPENAI_URL, json=body, headers=headers, timeout=OPENAI_TIMEOUT)
        import httpx
        with httpx.Client(timeout=OPENAI_TIMEOUT) as http:
            return http.post(OPENAI_URL, json=body, headers=headers)

    def ask(self, question: str, lang: str, *, today: date, cfg: dict) -> ProviderAnswer:
        block = _provider_block(cfg, self.key)
        models = _model_ids(block, "gpt-6-luna")
        request = block.get("request") or {}
        loc = _location((cfg or {}).get("location"))
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            return ProviderAnswer(status="error", model=models[0], error="OPENAI_API_KEY is not set")
        tool = {"type": "web_search", "user_location": loc,
                "search_context_size": request.get("search_context_size") or "medium"}
        body = {
            "input": question,
            "tools": [tool],
            "tool_choice": "auto",
            "include": ["web_search_call.action.sources"],
            "max_tool_calls": _max_searches(cfg),
            "reasoning": {"effort": request.get("reasoning_effort") or "low"},
            "max_output_tokens": int(request.get("max_output_tokens") or OPENAI_MAX_OUTPUT_TOKENS),
            "store": False,
        }
        line = _date_line(cfg, today)
        if line:
            body["instructions"] = line
        last_error = None
        for model in models:
            if model in self._rejected:
                continue
            try:
                resp = self._post(dict(body, model=model), key)
            except Exception as e:  # noqa: BLE001 - timeouts and connection errors become a status
                err = f"{type(e).__name__}: {safe_message(e)}"
                log.warning("ai audit: OpenAI call failed (%s)", err)
                # a timeout may still be billed: the runner charges the pre-call estimate
                return ProviderAnswer(status="error", model=model, location_sent=loc, error=safe_message(err),
                                      cost_unknown=True)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except Exception:  # noqa: BLE001
                    return ProviderAnswer(status="error", model=model, location_sent=loc,
                                          error="response was not JSON", cost_unknown=True)
                return parse_openai(data, model, loc)
            code, msg = _openai_error(resp)
            if resp.status_code == 404 or code == "model_not_found" or (
                    resp.status_code == 400 and "model" in msg.lower() and ("web_search" in msg or "tool" in msg.lower())):
                log.warning("ai audit: OpenAI model %s refused (%s); trying the next model", model, msg)
                self._rejected.add(model)
                last_error = f"{model}: {msg}"
                continue
            if resp.status_code == 429 and code != "insufficient_quota":
                status = "rate_limited"
            elif code in OPENAI_POLICY_CODES:      # e.g. invalid_prompt: the prompt was flagged by policy
                status = "refused"
            else:
                status = "error"
            err = f"HTTP {resp.status_code}" + (f" {code}" if code else "") + f": {msg}"
            log.warning("ai audit: OpenAI call failed (%s)", err)
            return ProviderAnswer(status=status, model=model, location_sent=loc, error=safe_message(err))
        return ProviderAnswer(status="error", model=models[-1], location_sent=loc,
                              error=safe_message(last_error or "no listed model accepts the web search tool"))


def parse_openai(data: dict, model: str, loc: dict) -> ProviderAnswer:
    """One answer from a Responses API response with include=["web_search_call.action.sources"]."""
    col = _Collector()
    queries, texts = [], []
    calls = failed_calls = 0
    refused = False
    pending_cites = []
    for item in data.get("output") or []:
        t = item.get("type")
        if t == "web_search_call":
            action = item.get("action") or {}
            if action.get("type") not in (None, "search"):
                continue                     # open_page / find_in_page: not a search, not billed as one
            calls += 1
            if item.get("status") == "failed":
                failed_calls += 1
            queries.extend(action.get("queries") or [])
            queries.append(action.get("query"))
            for s in action.get("sources") or []:
                url = _real_source(s if isinstance(s, dict) else {"url": s})
                if url:
                    col.search_result(url, s.get("title") if isinstance(s, dict) else None)
        elif t == "message":
            for c in item.get("content") or []:
                if c.get("type") == "output_text":
                    texts.append(c.get("text") or "")
                    for a in c.get("annotations") or []:
                        if a.get("type") == "url_citation" and a.get("url"):
                            pending_cites.append((a["url"], a.get("title")))
                elif c.get("type") == "refusal":
                    refused = True
    for url, title in pending_cites:            # after every search, so cited links pick up searched data
        col.citation(url, title)
    usage = data.get("usage") or {}
    err = data.get("error") if isinstance(data.get("error"), dict) else {}
    code = err.get("code")
    incomplete = (data.get("incomplete_details") or {}).get("reason")
    error = None
    if refused or code in OPENAI_POLICY_CODES or incomplete == "content_filter":
        status = "refused"
        error = f"model declined ({code or incomplete or 'refusal'})"
    elif code == "rate_limit_exceeded":
        status, error = "rate_limited", f"{code}: {err.get('message') or ''}"
    elif data.get("status") in ("failed", "cancelled") or code:
        status, error = "error", f"{code or data.get('status')}: {err.get('message') or ''}"
    elif calls and failed_calls == calls and not col.searched:
        status, error = "error", "web search failed"
    elif not calls:
        status = "no_search"
    else:
        status = "ok"
    if incomplete == "max_output_tokens":
        log.info("ai audit: %s answer reached max_output_tokens", model)
    return ProviderAnswer(
        status=status, model=str(data.get("model") or model), queries=_unique(queries),
        searched=list(col.searched.values()), cited=list(col.cited.values()),
        answer_text="\n".join(t for t in texts if t), input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0), searches=calls, location_sent=dict(loc),
        error=safe_message(error) if error else None)


# ---------------------------------------------------------------- registry

PROVIDERS = (AnthropicProvider, OpenAIProvider)


def get_providers(cfg: dict) -> dict:
    """The providers switched on in config/ai_audit.yaml (providers: {anthropic: {enabled: true}, ...}),
    in a fixed order: Claude, then ChatGPT. A provider that is not listed is off."""
    block = (cfg or {}).get("providers") or {}
    out = {}
    for cls in PROVIDERS:
        conf = block.get(cls.key)
        enabled = conf if isinstance(conf, bool) else bool((conf or {}).get("enabled"))
        if enabled:
            out[cls.key] = cls()
    return out
