"""The weekly AI answers audit (docs/research/ai_answers_audit_scope.md; settings in config/ai_audit.yaml).

Every question in the country config (ai_audit.questions) is asked in Arabic and in English, one new
conversation each, ordered question, then language, then assistant, so a stop leaves the assistants and
languages evenly covered. Before each answer: spent this week (every assistant, every country) plus the
estimate for one answer must stay within the weekly cap, or the remaining answers are recorded as
over_budget and the run stops.

What is kept: the assistant's own search queries (admin-only), the links its search returned and the links
the answer cited, matched read-only to the outlet register (matcher.py), the answer's language and length.
The answer text itself only passes through memory and is never stored.

Unscored: the audit writes only ai_run, ai_answer and ai_source (plus source_run for the health strip),
never Item, ItemTheme or CellWeek. Provider calls run outside the scheduler's job lock; each answer's rows
are written in a short transaction that waits for the lock (see _writing)."""
import hashlib
import logging
import os
import re
import threading
import time
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

import yaml
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import settings
from ..collectors.base import AwaitingKey, RunResult, run_collector
from ..i18n import N_
from ..models import AiAnswer, AiRun, AiSource, Country, utcnow
from ..textnorm import detect_lang
from .matcher import Matcher, clean_url

log = logging.getLogger("desert_watch.ai_audit")

PROVIDER_KEYS = ("anthropic", "openai", "perplexity")
# The same English labels as providers.py, here so the API can translate them without importing the SDKs.
LABELS = {"anthropic": N_("Claude (Anthropic)"), "openai": N_("ChatGPT (OpenAI)"), "perplexity": N_("Perplexity (API)")}
KEY_NAMES = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "perplexity": "PERPLEXITY_API_KEY"}
LANGS = ("ar", "en")
ANSWER_STATUSES = ("ok", "no_search", "refused", "rate_limited", "error")
COUNTED = ("ok", "no_search")          # an answer came back, with or without a search
FAILED = ("rate_limited", "error")
STOP_AFTER = 3            # refused or rate-limited answers in a row end an assistant's run (as collectors.base)
MAX_MINUTES = 15          # per assistant per run
PACE_SECONDS = 1.0        # at least this long between two calls to the same assistant
WRITE_WAIT_SECONDS = 900  # an answer's write waits this long for the scheduler's lock, then writes anyway
STALE_RUNNING = timedelta(hours=2)

# Run notes. Stored English; the admin API rebuilds them from the run's status, translated.
AWAITING_KEY = N_("Set the {key} secret to start this audit.")
DISABLED = N_("Switched off in config/ai_audit.yaml.")
OVER_BUDGET = N_("The weekly cap was reached: the remaining answers were not asked.")
STOPPED_REFUSED = N_("Stopped after {n} refused or rate-limited answers in a row.")
STOPPED_TIME = N_("Stopped after {n} minutes.")

_ACTIVE = threading.Lock()   # one run at a time in this process (the schedule and the Admin button)


# ---------------------------------------------------------------- config
def load_config() -> dict:
    with open(settings.CONFIG_DIR / "ai_audit.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def enabled_keys(cfg: dict) -> list[str]:
    return [k for k, v in (cfg.get("providers") or {}).items() if (v or {}).get("enabled")]


def known_keys(cfg: dict) -> list[str]:
    return list(dict.fromkeys([*PROVIDER_KEYS, *(cfg.get("providers") or {})]))


def question_version(q: dict) -> str:
    return hashlib.sha1((q["en"] + q["ar"]).encode("utf-8")).hexdigest()[:8]


def questions(country: Country) -> list[dict]:
    """The country's question set (config ai_audit.questions), each with its version."""
    out = []
    for q in ((country.config or {}).get("ai_audit") or {}).get("questions") or []:
        if q.get("key") and q.get("en") and q.get("ar"):
            out.append({**q, "version": question_version(q)})
    return out


def week_start_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def spent_this_week(s: Session, week: date) -> float:
    return float(s.scalar(select(func.coalesce(func.sum(AiRun.cost_usd), 0.0)).where(AiRun.week_start == week)) or 0.0)


def is_busy() -> bool:
    return _ACTIVE.locked()


def _scrub(text: str) -> str:
    """Error text with anything that looks like a key removed (keys are never stored or logged)."""
    for name in KEY_NAMES.values():
        v = os.environ.get(name)
        if v and len(v) >= 8:
            text = text.replace(v, "[key]")
    text = re.sub(r"\b(sk|key|token|pplx)-[A-Za-z0-9_\-]{6,}", r"\1-[redacted]", text)
    return re.sub(r"(?i)(bearer|x-api-key[\"']?\s*[:=])\s*\S+", r"\1 [redacted]", text)[:1000]


@contextmanager
def _writing(lock):
    """A short write. Waits for the scheduler's job lock (a full recompute can hold it a while), then
    writes anyway after WRITE_WAIT_SECONDS: SQLite's busy timeout still keeps the writes apart."""
    got = False
    if lock is not None:
        got = lock.acquire(timeout=WRITE_WAIT_SECONDS)
        if not got:
            log.warning("ai_audit: job lock still held after %ss, writing anyway", WRITE_WAIT_SECONDS)
    try:
        yield
    finally:
        if got:
            lock.release()


def _ask_cfg(cfg: dict, prices: dict, key: str) -> dict:
    """What Provider.ask() receives: config/ai_audit.yaml merged with the provider's price block."""
    return {**cfg, **(prices.get(key) or {})}


def _estimate(P, prices: dict, key: str, cfg: dict, provider=None) -> float:
    """One answer's cost for the budget check: the config's token estimate, max_searches searches, and the
    rates of the model the provider will try next (its next_model(), after a fallback a dearer one), else
    the first listed model."""
    e = cfg.get("estimate") or {}
    model = None
    if provider is not None and callable(getattr(provider, "next_model", None)):
        try:
            model = provider.next_model(_ask_cfg(cfg, prices, key))
        except Exception:  # noqa: BLE001 - the listed model is a fine estimate
            model = None
    model = model or (((prices.get(key) or {}).get("models") or [{}])[0] or {}).get("id")
    return float(P.estimate_usd(prices, key, model, int(cfg.get("max_searches", 2)),
                                int(e.get("input_tokens", 30000)), int(e.get("output_tokens", 1500))))


# ---------------------------------------------------------------- runs of the week
def _week_runs(s: Session, country_id: int, week: date, key: str) -> list[AiRun]:
    # developer-API runs only: a panel or browser run (api/ai_panel.py) never blocks or counts as one
    return s.scalars(select(AiRun).where(AiRun.country_id == country_id, AiRun.week_start == week,
                                         AiRun.provider == key, or_(AiRun.origin == "api", AiRun.origin.is_(None)))
                     .order_by(AiRun.id.desc())).all()


def _blocking(runs: list[AiRun], force: bool = False) -> str | None:
    """'running' or 'already_run' when this week's runs rule out another one. A run that made no call
    (awaiting_key, disabled) does not count. A run left 'running' for hours was interrupted: it still
    counts, since it may have spent money; an admin can force another. A run that failed having spent
    nothing does not count either. `force` passes 'already_run' but
    never a run still going (another process, such as a CLI run, could be spending the same cap)."""
    for r in runs:
        if r.status in ("awaiting_key", "disabled"):
            continue
        if r.status == "error" and not (r.cost_usd or 0) and not int((r.usage or {}).get("searches") or 0):
            continue   # failed before spending anything (a config or network fault): it may run again
        if r.status == "running" and r.started_at and utcnow() - r.started_at < STALE_RUNNING:
            return "running"
        if force:
            continue
        return "already_run"
    return None


def _resolve(cfg: dict, providers) -> tuple[dict, list[str], list[dict]]:
    """(provider objects to use, keys switched off in config, unknown keys as skipped entries).
    `providers`: None (every enabled one), a key, a list of keys, or {key: object} (tests inject fakes)."""
    if isinstance(providers, dict):
        return dict(providers), [], []
    wanted = known_keys(cfg) if providers is None else ([providers] if isinstance(providers, str) else list(providers))
    enabled = enabled_keys(cfg)
    objs = {}
    if any(k in enabled for k in wanted):
        from . import providers as P
        objs = P.get_providers(cfg)
    active = {k: objs[k] for k in wanted if k in enabled and k in objs}
    disabled = [k for k in wanted if k in known_keys(cfg) and k not in enabled]
    unknown = [{"provider": k, "reason": "unknown_provider"} for k in wanted
               if k not in known_keys(cfg) or (k in enabled and k not in objs)]
    return active, disabled, unknown


def _new_run(s: Session, country: Country, week: date, key: str, status: str, *, force: bool, reuse: bool,
             prices: dict, cfg: dict) -> AiRun:
    """This week's run row for an assistant. A row left by a week that made no call (awaiting_key,
    disabled) is reused, so a week keeps one row per assistant unless a run is forced."""
    old = next(iter(_week_runs(s, country.id, week, key)), None)
    run = old if reuse and old is not None and old.status in ("awaiting_key", "disabled") else None
    if run is None:
        run = AiRun(country_id=country.id, provider=key, week_start=week)
        s.add(run)
    block = prices.get(key) or {}
    first = ((block.get("models") or [{}])[0] or {})
    run.model, run.tool = first.get("id"), block.get("tool") or "web_search"
    run.started_at, run.finished_at, run.status, run.forced = utcnow(), None, status, force
    run.settings = {"max_searches": cfg.get("max_searches"), "fly_region": os.environ.get("FLY_REGION"),
                    "date_line": bool(cfg.get("date_line")), "location_sent": None}
    run.usage = {"input_tokens": 0, "output_tokens": 0, "searches": 0}
    run.cost_usd, run.price_basis, run.error = 0.0, {"as_of": str(prices.get("as_of") or "")}, None
    if status == "awaiting_key":
        run.error = AWAITING_KEY.format(key=KEY_NAMES.get(key, key.upper() + "_API_KEY"))
        run.finished_at = utcnow()
    elif status == "disabled":
        run.error, run.finished_at = DISABLED, utcnow()
    s.flush()
    return run


# ---------------------------------------------------------------- one answer
def _sources(matcher: Matcher, items, role: str) -> list[AiSource]:
    """Rows for the links of one role, one per link (the same link twice is kept once, at its best rank;
    citation counts add up). Non-web entries (OpenAI's oai-* feeds) are dropped."""
    rows: dict[str, AiSource] = {}
    for i, src in enumerate(items or []):
        url = getattr(src, "url", None) or ""
        title = getattr(src, "title", None)
        m = matcher.match(url, title)
        if m is None:
            continue
        spans = int(getattr(src, "citations", 0) or 0)
        key = clean_url(url)
        if key in rows:
            if role == "cited":
                rows[key].citations += max(spans, 1)
            continue
        when = getattr(src, "date", None)
        rows[key] = AiSource(role=role, rank=int(getattr(src, "rank", 0) or 0) or i + 1, url=m.url[:2000],
                             domain=m.domain[:200], outlet_id=m.outlet_id, family_id=m.family_id, match=m.match,
                             title=(str(title)[:1000] if (m.keep_title and title) else None), lang=m.lang,
                             date=str(when)[:40] if when else None,
                             citations=max(spans, 1) if role == "cited" else 0)
    return list(rows.values())


def _charge(run: AiRun, cost: float) -> None:
    run.cost_usd = round(float(run.cost_usd or 0) + cost, 6)


def _store_answer(s: Session, matcher: Matcher, P, prices: dict, run: AiRun, q: dict, lang: str, ans, err: str | None,
                  st: dict, est: float = 0.0) -> str:
    """Writes one answer (not its text) and its links, and adds its usage and cost to the run. When the
    cost cannot be known (the call raised, or timed out after sending: cost_unknown) the answer is charged
    the pre-call estimate `est`, so the weekly cap still counts it."""
    if ans is None:
        s.add(AiAnswer(run_id=run.id, question_key=q["key"], question_version=q["version"], lang=lang, status="error",
                       queries=[], cost_usd=round(est, 6)))
        _charge(run, est)
        st["errors"].append(f"{q['key']}/{lang}: {err}")
        return "error"
    status = ans.status if ans.status in ANSWER_STATUSES else "error"
    text = getattr(ans, "answer_text", None) or ""
    model = getattr(ans, "model", None) or run.model
    searches = int(getattr(ans, "searches", 0) or 0)
    tin, tout = int(getattr(ans, "input_tokens", 0) or 0), int(getattr(ans, "output_tokens", 0) or 0)
    cost = float(P.estimate_usd(prices, run.provider, model, searches, tin, tout)) if (searches or tin or tout) else 0.0
    if getattr(ans, "cost_unknown", False):
        cost += est
    a = AiAnswer(run_id=run.id, question_key=q["key"], question_version=q["version"], lang=lang, status=status,
                 answer_lang=detect_lang(text) if text.strip() else None, answer_chars=len(text) if text else None,
                 queries=[str(x)[:500] for x in (getattr(ans, "queries", None) or [])][:20],
                 searches=searches, cost_usd=round(cost, 6))
    s.add(a)
    s.flush()
    searched = _sources(matcher, getattr(ans, "searched", None), "searched")
    cited = _sources(matcher, getattr(ans, "cited", None), "cited")
    for row in searched + cited:
        row.answer_id = a.id
        s.add(row)
    a.n_searched, a.n_cited = len(searched), len(cited)
    u = dict(run.usage or {})
    run.usage = {"input_tokens": int(u.get("input_tokens", 0)) + tin, "output_tokens": int(u.get("output_tokens", 0)) + tout,
                 "searches": int(u.get("searches", 0)) + searches}
    _charge(run, cost)
    if model:
        st["models"].setdefault(model, 0)
        st["models"][model] += 1
    loc = getattr(ans, "location_sent", None)
    if loc and loc not in st["locations"]:
        st["locations"].append(loc)
    if status in FAILED or getattr(ans, "error", None):
        st["errors"].append(f"{q['key']}/{lang}: {status}" + (f" ({_scrub(str(ans.error))[:200]})" if getattr(ans, "error", None) else ""))
    return status


def _finish(run: AiRun, st: dict, prices: dict, crash: str | None) -> None:
    n = st["n"]
    good = n["ok"] + n["no_search"] + n["refused"]
    failed = n["rate_limited"] + n["error"]
    if n["over_budget"]:
        run.status = "over_budget"
    elif crash or (failed and not good):
        run.status = "error" if not good else "partial"
    elif failed or st["stop"]:
        run.status = "partial"
    else:
        run.status = "ok"
    models = sorted(st["models"], key=lambda m: -st["models"][m])
    if models:
        run.model = models[0]
    block = prices.get(run.provider) or {}
    rates = {m["id"]: {k: m[k] for k in ("input_per_mtok", "output_per_mtok", "long_context") if k in m}
             for m in block.get("models") or [] if m.get("id") in (models or [run.model])}
    run.price_basis = {"as_of": str(prices.get("as_of") or ""), "search_per_1000_usd": block.get("search_per_1000_usd"),
                       "models": rates}
    cfg_settings = dict(run.settings or {})
    cfg_settings["location_sent"] = st["locations"][0] if len(st["locations"]) == 1 else (st["locations"] or None)
    if len(models) > 1:
        cfg_settings["models"] = models
    if st["stop"]:
        cfg_settings["stopped"] = {"reason": st["stop"][0], "n": st["stop"][1]}
    run.settings = cfg_settings
    errors = ([crash] if crash else []) + st["errors"]
    run.error = "\n".join(errors[:6])[:2000] or None
    run.finished_at = utcnow()


def _health(st: dict):
    """The source-health reading of one assistant's run (run_collector)."""
    def fn(_s):
        n = st["n"]
        detail = []
        if n["over_budget"]:
            detail.append(OVER_BUDGET)
        if st["stop"]:
            detail.append((STOPPED_REFUSED if st["stop"][0] == "refused" else STOPPED_TIME).format(n=st["stop"][1]))
        detail += st["errors"][:3]
        return RunResult(rows=n["ok"] + n["no_search"],
                         errors=n["rate_limited"] + n["error"] + (1 if (n["over_budget"] or st["stop"]) else 0),
                         detail="\n".join(detail)[:1000])
    return fn


def _awaiting(message: str):
    def fn(_s):
        raise AwaitingKey(message)
    return fn


# ---------------------------------------------------------------- the week
def run_week(s: Session, country: Country, providers=None, force: bool = False, dry_run: bool = False,
             cap: float | None = None, limit: int | None = None, today: date | None = None, lock=None) -> dict:
    """Asks the week's questions. `providers`: None (every enabled assistant), a key, a list of keys, or
    {key: provider object}. `force` runs again although this week has a run. `dry_run` makes no call and
    writes nothing: it returns the planned answers and the estimated cost. `cap` replaces the weekly cap
    (the pilot week's double run). `limit` asks only the first N answers of the plan. `lock` is the
    scheduler's job lock, taken for each short write."""
    from . import providers as P   # imported here: tests replace it with fakes
    cfg = load_config()
    prices = P.load_prices() or {}
    today = today or datetime.now(timezone.utc).date()
    week = week_start_of(today)
    cap_usd = float(cap if cap is not None else cfg.get("weekly_cap_usd", 1.0))
    qs = questions(country)
    active, disabled, skipped = _resolve(cfg, providers)
    skipped += [{"provider": k, "reason": "disabled"} for k in disabled]
    if not qs:
        skipped.append({"provider": None, "reason": "no_questions"})
    for key in list(active):
        why = _blocking(_week_runs(s, country.id, week, key), force)
        if why:
            skipped.append({"provider": key, "reason": why})
            del active[key]
    waiting = [k for k, p in active.items() if not p.available()]
    skipped += [{"provider": k, "reason": "awaiting_key"} for k in waiting]
    callers = {k: p for k, p in active.items() if k not in waiting}
    plan = [(q, lang, key) for q in qs for lang in LANGS for key in callers]
    if limit:
        plan = plan[:max(0, int(limit))]
    est = {k: _estimate(P, prices, k, cfg, callers[k]) for k in callers}
    spent = spent_this_week(s, week)
    if dry_run:
        fits, total = 0, spent
        for _q, _l, k in plan:
            if total + est[k] > cap_usd + 1e-9:
                break
            total += est[k]
            fits += 1
        # what an assistant still waiting for its key would add once the key is set (not in the plan)
        n_later = min(len(qs) * len(LANGS), int(limit)) if limit else len(qs) * len(LANGS)
        later = [{"provider": k, "answers": n_later,
                  "estimated_usd": round(_estimate(P, prices, k, cfg, active[k]) * n_later, 4)} for k in waiting]
        return {"week_start": week.isoformat(), "planned": [{"provider": k, "question_key": q["key"], "lang": l}
                                                            for q, l, k in plan],
                "estimated_usd": round(sum(est[k] for _q, _l, k in plan), 4), "fits_cap": fits,
                "cap_usd": cap_usd, "spent_this_week_usd": round(spent, 4), "skipped": skipped,
                "awaiting_key": later}
    if not _ACTIVE.acquire(blocking=False):
        return {"week_start": week.isoformat(), "busy": True, "runs": [], "skipped": skipped,
                "cap_usd": cap_usd, "spent_this_week_usd": round(spent, 4)}
    try:
        return _execute(s, country, P, cfg, prices, week, today, cap_usd, plan, callers, waiting, disabled,
                        skipped, est, force, lock)
    finally:
        _ACTIVE.release()


def _execute(s, country, P, cfg, prices, week, today, cap_usd, plan, callers, waiting, disabled, skipped, est,
             force, lock) -> dict:
    in_plan = [k for k in callers if any(k == key for _q, _l, key in plan)]
    with _writing(lock):
        for k in disabled:
            if not _blocking(_week_runs(s, country.id, week, k)):
                _new_run(s, country, week, k, "disabled", force=False, reuse=True, prices=prices, cfg=cfg)
        for k in waiting:
            _new_run(s, country, week, k, "awaiting_key", force=force, reuse=True, prices=prices, cfg=cfg)
        runs = {k: _new_run(s, country, week, k, "running", force=force, reuse=True, prices=prices, cfg=cfg)
                for k in in_plan}
        s.commit()
    state = {k: {"n": Counter(), "stop": None, "streak": 0, "first": None, "last": 0.0, "models": {},
                 "locations": [], "errors": []} for k in in_plan}
    matcher = Matcher(s)
    over = False
    crash = None
    try:
        for q, lang, key in plan:
            st = state[key]
            if st["stop"]:
                continue
            if not over:
                est[key] = _estimate(P, prices, key, cfg, callers[key])
            spent_now = 0.0 if over else spent_this_week(s, week)
            if over or spent_now + est[key] > cap_usd + 1e-9:
                over = True
                with _writing(lock):
                    s.add(AiAnswer(run_id=runs[key].id, question_key=q["key"], question_version=q["version"], lang=lang,
                                   status="over_budget", queries=[]))
                    s.commit()
                st["n"]["over_budget"] += 1
                continue
            if st["first"] is not None and time.monotonic() - st["first"] > MAX_MINUTES * 60:
                st["stop"] = ("time", MAX_MINUTES)
                continue
            wait = st["last"] + PACE_SECONDS - time.monotonic()
            if st["first"] is not None and wait > 0:
                time.sleep(wait)
            if st["first"] is None:
                st["first"] = time.monotonic()
            ans, err = None, None
            # what is left under the cap: the provider will not start a pause_turn continuation past it
            ask_cfg = {**_ask_cfg(cfg, prices, key), "answer_budget_usd": round(cap_usd - spent_now, 6)}
            try:
                ans = callers[key].ask(q[lang], lang, today=today, cfg=ask_cfg)
            except Exception as e:  # noqa: BLE001 - a provider failure is one answer's error, not the run's
                err = _scrub(f"{type(e).__name__}: {e}")
                log.warning("ai_audit %s %s/%s failed: %s", key, q["key"], lang, type(e).__name__)
            st["last"] = time.monotonic()
            with _writing(lock):
                status = _store_answer(s, matcher, P, prices, runs[key], q, lang, ans, err, st, est[key])
                s.commit()
            del ans   # the answer text goes with it
            st["n"][status] += 1
            st["streak"] = st["streak"] + 1 if status in ("refused", "rate_limited") else 0
            if st["streak"] >= STOP_AFTER:
                st["stop"] = ("refused", STOP_AFTER)
    except Exception as e:
        s.rollback()
        crash = _scrub(f"{type(e).__name__}: {e}")
        log.exception("ai_audit run failed")
        raise
    finally:
        with _writing(lock):
            for k, run in runs.items():
                _finish(run, state[k], prices, crash)
            s.commit()
            for k in in_plan:
                run_collector(s, f"ai_audit_{k}", _health(state[k]))
            for k in waiting:
                run_collector(s, f"ai_audit_{k}", _awaiting(AWAITING_KEY.format(key=KEY_NAMES.get(k, k.upper()))))
    return {"week_start": week.isoformat(), "cap_usd": cap_usd, "spent_this_week_usd": round(spent_this_week(s, week), 4),
            "runs": [{"run_id": r.id, "provider": k, "status": r.status, "answers": state[k]["n"]["ok"] + state[k]["n"]["no_search"],
                      "over_budget": state[k]["n"]["over_budget"], "cost_usd": round(r.cost_usd or 0, 4)}
                     for k, r in runs.items()],
            "skipped": skipped}


def run_all(provider: str | None = None, force: bool = False, dry_run: bool = False, limit: int | None = None,
            cap: float | None = None, lock=None) -> list[dict]:
    """run_week for every country with a question set (the schedule, the CLI and the Admin button)."""
    from ..db import SessionLocal
    out = []
    with SessionLocal() as s:
        for c in s.scalars(select(Country).order_by(Country.id)).all():
            if not questions(c):
                continue
            res = run_week(s, c, providers=provider, force=force, dry_run=dry_run, cap=cap, limit=limit, lock=lock)
            out.append({"country": c.iso2, **res})
            log.info("ai_audit %s: %s", c.iso2, {k: v for k, v in res.items() if k != "planned"})
    return out
