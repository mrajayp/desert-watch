"""The AI answers audit (ai_audit/): what AI assistants search and cite when asked about Libya.

Who sees what: admins see everything. Everyone else sees the summary only once config/ai_audit.yaml
says visible_to: team, and then only outlet- and domain-level counts. The assistant's own search queries,
full links and result titles can carry private names, so they stay on the /api/admin routes.
Counts are per assistant and never added across assistants (each API means something different by a
search result and by a citation)."""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import median

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import auth
from ..ai_audit import runner as audit
from ..db import get_db
from ..dedupe import outlet_families
from ..i18n import tr
from ..models import AiAnswer, AiRun, AiSource, Country, Item, Outlet, User, utcnow
from ..textnorm import detect_lang
from .common import country_or_404, outlet_categories

router = APIRouter(prefix="/api")

SCOPES = ("libyan", "diaspora", "international")
TOP_OUTLETS = 15
NEVER_CITED_MAX = 60
RUNS_MAX = 60
# Hosted blogs and pages: a subdomain there is usually one person's own site, so the summary (which the
# team may see) names only the platform for one that is not in the register. The admin's list of
# unknown domains keeps the full host.
HOSTED = ("blogspot.com", "wordpress.com", "substack.com", "tumblr.com", "wixsite.com", "weebly.com", "github.io",
          "medium.com", "livejournal.com", "telegra.ph")


def can_see(u: User, cfg: dict | None = None) -> bool:
    """Admins always; the whole team once config visible_to is 'team'."""
    cfg = audit.load_config() if cfg is None else cfg
    return u.role == "admin" or cfg.get("visible_to") == "team"


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _spread(values: list[int]) -> dict:
    if not values:
        return {"median": None, "min": None, "max": None}
    return {"median": median(values), "min": min(values), "max": max(values)}


def _lang3(code: str | None) -> str:
    return code if code in ("ar", "en") else "other"


def _scope(oid: int | None, family: int | None, cats: dict) -> str:
    """An outlet's scope, else its family's (a website's social account), else unknown_scope."""
    if oid is None:
        return "unregistered"
    for o in (oid, family):
        v = ((cats.get(o) or {}).get("scope") or {}).get("value") if o is not None else None
        if v in SCOPES:
            return v
    return "unknown_scope"


def _public_domain(domain: str) -> str:
    d = (domain or "").lower()
    return next((h for h in HOSTED if d.endswith("." + h)), domain)


def _status(s: Session, country_id: int, key: str, cfg: dict) -> str:
    if key not in audit.enabled_keys(cfg):
        return "disabled"
    r = s.scalar(select(AiRun).where(AiRun.country_id == country_id, AiRun.provider == key)
                 .order_by(AiRun.id.desc()).limit(1))
    return r.status if r else "never_run"


def ai_cited_4w(s: Session, u: User, outlet_id: int) -> int | None:
    """Citations of an outlet (and, for a website, of its own social accounts) in the last 4 weeks,
    every assistant; None when the user may not see audit results (GET /api/outlets/{id})."""
    if not can_see(u):
        return None
    start = audit.week_start_of(_today()) - timedelta(weeks=3)
    return int(s.scalar(select(func.count(AiSource.id)).join(AiAnswer, AiAnswer.id == AiSource.answer_id)
                        .join(AiRun, AiRun.id == AiAnswer.run_id)
                        .where(AiSource.role == "cited", AiAnswer.status.in_(audit.COUNTED), AiRun.week_start >= start,
                               or_(AiSource.outlet_id == outlet_id, AiSource.family_id == outlet_id))) or 0)


# ---------------------------------------------------------------- summary (Outlets page card)
@router.get("/ai-audit/summary")
def ai_summary(weeks: int = 4, provider: str = "all", lang: str = "all", country: str = "LY",
               s: Session = Depends(get_db), u: User = Depends(auth.current_user)):
    cfg = audit.load_config()
    if not can_see(u, cfg):
        return {"visible": False}
    if weeks not in (4, 12):
        raise HTTPException(400, tr("Weeks must be 4 or 12."))
    keys = audit.known_keys(cfg)
    if provider != "all" and provider not in keys:
        raise HTTPException(400, tr("Unknown provider"))
    if lang not in ("all", "ar", "en"):
        raise HTTPException(400, tr("Unknown language"))
    c = country_or_404(s, country)
    this_week = audit.week_start_of(_today())
    start, end = this_week - timedelta(weeks=weeks - 1), this_week + timedelta(days=6)
    chosen = keys if provider == "all" else [provider]

    in_window = [AiRun.country_id == c.id, AiRun.week_start >= start, AiRun.week_start <= this_week,
                 AiRun.provider.in_(chosen)] + ([AiAnswer.lang == lang] if lang != "all" else [])
    by_status = Counter()
    for prov, st, n in s.execute(select(AiRun.provider, AiAnswer.status, func.count(AiAnswer.id))
                                 .join(AiRun, AiRun.id == AiAnswer.run_id).where(*in_window)
                                 .group_by(AiRun.provider, AiAnswer.status)):
        by_status[(prov, st)] = n
    included = select(AiAnswer.id).join(AiRun, AiRun.id == AiAnswer.run_id).where(
        *in_window, AiAnswer.status.in_(audit.COUNTED))
    answers = {a.id: (a, prov) for a, prov in s.execute(
        select(AiAnswer, AiRun.provider).join(AiRun, AiRun.id == AiAnswer.run_id)
        .where(*in_window, AiAnswer.status.in_(audit.COUNTED)))}
    sources = s.scalars(select(AiSource).where(AiSource.answer_id.in_(included))).all()
    fams = outlet_families(s)
    fam = lambda oid: fams.get(oid, (oid,))[0] if oid is not None else None  # noqa: E731
    cats = outlet_categories(s)

    providers = []
    for key in chosen:
        ans = [a for a, p in answers.values() if p == key]
        if not ans and key not in audit.enabled_keys(cfg):
            continue
        mine = [x for x in sources if answers[x.answer_id][1] == key]
        cited_scope = Counter({k: 0 for k in (*SCOPES, "unknown_scope", "unregistered")})
        cited_lang = Counter({"ar": 0, "en": 0, "other": 0})
        for x in mine:
            if x.role == "cited":
                cited_scope[_scope(x.outlet_id, fam(x.outlet_id), cats)] += 1
                cited_lang[_lang3(x.lang)] += 1
        query_lang = Counter({"ar": 0, "en": 0, "other": 0})
        for a in ans:
            for qtext in a.queries or []:
                query_lang[_lang3(detect_lang(qtext))] += 1
        providers.append({
            "key": key, "label": tr(audit.LABELS.get(key, key)), "answers": len(ans),
            "no_search": sum(a.status == "no_search" for a in ans),
            "refused": by_status[(key, "refused")], "failed": sum(by_status[(key, x)] for x in audit.FAILED),
            "over_budget": by_status[(key, "over_budget")],
            "searched_per_answer": _spread([a.n_searched for a in ans]),
            "cited_per_answer": _spread([a.n_cited for a in ans]),
            "cited_scope": dict(cited_scope), "cited_lang": dict(cited_lang), "query_lang": dict(query_lang)})

    # monitored coverage in the same weeks, for comparison (a different unit: articles, not citations)
    coverage = Counter({k: 0 for k in (*SCOPES, "unknown_scope")})
    t0 = datetime.combine(start, datetime.min.time())
    t1 = datetime.combine(end + timedelta(days=1), datetime.min.time())
    for oid, n in s.execute(select(Item.outlet_id, func.count(Item.id)).where(
            Item.country_id == c.id, Item.kind == "article", Item.relevant.is_(True), Item.duplicate_of.is_(None),
            Item.published_at >= t0, Item.published_at < t1).group_by(Item.outlet_id)):
        sc = _scope(oid, fam(oid), cats)
        coverage["unknown_scope" if sc == "unregistered" else sc] += n

    # outlets (a website and its own social accounts together) and unregistered domains
    groups: dict = defaultdict(lambda: {"cited": 0, "searched": 0, "by_provider": Counter({k: 0 for k in chosen})})
    for x in sources:
        g = groups[("o", fam(x.outlet_id)) if x.outlet_id is not None else ("d", _public_domain(x.domain))]
        g[x.role] += 1
        if x.role == "cited":
            g["by_provider"][answers[x.answer_id][1]] += 1
    heads = {k[1] for k in groups if k[0] == "o"}
    names = {o.id: o for o in s.scalars(select(Outlet).where(Outlet.id.in_(heads)))} if heads else {}
    top = []
    for (kind, ident), g in groups.items():
        if not g["cited"]:
            continue
        o = names.get(ident) if kind == "o" else None
        top.append({"outlet_id": ident if kind == "o" else None, "name": o.name if o else ident if kind == "d" else str(ident),
                    "domain": o.domain if o else (ident if kind == "d" else None),
                    "scope": _scope(ident, ident, cats) if kind == "o" else "unregistered",
                    "cited": g["cited"], "searched": g["searched"], "by_provider": dict(g["by_provider"])})
    top.sort(key=lambda r: (-r["cited"], -r["searched"], str(r["name"]).lower()))

    # Libyan register outlets with counted articles in the last 12 weeks that no included answer cited
    since12 = utcnow() - timedelta(weeks=12)
    articles = Counter()
    for oid, n in s.execute(select(Item.outlet_id, func.count(Item.id)).where(
            Item.country_id == c.id, Item.kind == "article", Item.relevant.is_(True), Item.duplicate_of.is_(None),
            Item.published_at >= since12, Item.outlet_id.is_not(None)).group_by(Item.outlet_id)):
        articles[fam(oid)] += n
    cited_heads = {fam(x.outlet_id) for x in sources if x.outlet_id is not None and x.role == "cited"}
    seen_heads = {fam(x.outlet_id) for x in sources if x.outlet_id is not None and x.role == "searched"}
    libyan = [h for h, n in articles.items() if n and h not in cited_heads and _scope(h, h, cats) == "libyan"]
    outlets = {o.id: o for o in s.scalars(select(Outlet).where(Outlet.id.in_(libyan), Outlet.active.is_(True)))} if libyan else {}
    # social: a register page or account with no website on record (the card may label or set these apart)
    never = sorted(({"outlet_id": h, "name": outlets[h].name, "domain": outlets[h].domain, "articles_12w": articles[h],
                     "appeared_in_results": h in seen_heads, "social": fams.get(h, (h, False))[1]}
                    for h in libyan if h in outlets),
                   key=lambda r: (-r["articles_12w"], r["name"].lower()))[:NEVER_CITED_MAX]

    return {"visible": True, "weeks": weeks, "window": {"from": start.isoformat(), "to": end.isoformat()},
            "status": {k: _status(s, c.id, k, cfg) for k in keys}, "providers": providers,
            "coverage_scope": dict(coverage), "top_outlets": top[:TOP_OUTLETS], "never_cited": never,
            "n_answers": len(answers)}


# ---------------------------------------------------------------- admin
def _run_note(r: AiRun) -> str | None:
    """The run's note in the interface language: our own notes are rebuilt from the status; a provider's
    error text is kept as it came."""
    if r.status == "awaiting_key":
        return tr(audit.AWAITING_KEY, key=audit.KEY_NAMES.get(r.provider, r.provider.upper() + "_API_KEY"))
    if r.status == "disabled":
        return tr(audit.DISABLED)
    notes = [tr(audit.OVER_BUDGET)] if r.status == "over_budget" else []
    stopped = (r.settings or {}).get("stopped")
    if stopped:
        notes.append(tr(audit.STOPPED_REFUSED if stopped.get("reason") == "refused" else audit.STOPPED_TIME,
                        n=stopped.get("n")))
    if r.error:
        notes.append(r.error)
    return "\n".join(notes) or None


def _iso(d) -> str | None:
    return d.isoformat() if d else None


@router.get("/admin/ai-audit/runs")
def ai_runs(country: str = "LY", s: Session = Depends(get_db), _: User = Depends(auth.require_admin)):
    cfg = audit.load_config()
    c = country_or_404(s, country)
    today = _today()
    week = audit.week_start_of(today)
    ytd = float(s.scalar(select(func.coalesce(func.sum(AiRun.cost_usd), 0.0)).where(
        AiRun.week_start >= date(today.year, 1, 1))) or 0.0)
    rows = s.scalars(select(AiRun).where(AiRun.country_id == c.id).order_by(AiRun.id.desc()).limit(RUNS_MAX)).all()
    counts: dict = defaultdict(Counter)
    if rows:
        for rid, st, n in s.execute(select(AiAnswer.run_id, AiAnswer.status, func.count(AiAnswer.id))
                                    .where(AiAnswer.run_id.in_([r.id for r in rows]))
                                    .group_by(AiAnswer.run_id, AiAnswer.status)):
            counts[rid][st] = n
    return {"cap_usd": float(cfg.get("weekly_cap_usd", 1.0)), "week_start": week.isoformat(),
            "week_cost_usd": round(audit.spent_this_week(s, week), 4), "ytd_cost_usd": round(ytd, 4),
            "runs": [{"id": r.id, "week_start": r.week_start.isoformat(), "provider": r.provider,
                      "label": tr(audit.LABELS.get(r.provider, r.provider)), "model": r.model, "tool": r.tool,
                      "status": r.status, "answers": sum(counts[r.id][x] for x in audit.COUNTED),
                      "asked": sum(n for st, n in counts[r.id].items() if st != "over_budget"),
                      "over_budget": counts[r.id]["over_budget"], "cost_usd": round(r.cost_usd or 0, 4),
                      "usage": r.usage or {}, "price_basis": r.price_basis or {}, "settings": r.settings or {},
                      "error": _run_note(r), "started_at": _iso(r.started_at), "finished_at": _iso(r.finished_at),
                      "forced": bool(r.forced)} for r in rows]}


def _source_json(x: AiSource, names: dict, cited: bool) -> dict:
    out = {"url": x.url, "title": x.title, "domain": x.domain, "outlet_id": x.outlet_id,
           "outlet_name": names.get(x.outlet_id), "match": x.match, "lang": x.lang, "rank": x.rank, "date": x.date}
    if cited:
        out["citations"] = x.citations
    return out


@router.get("/admin/ai-audit/answers")
def ai_answers(run_id: int, s: Session = Depends(get_db), _: User = Depends(auth.require_admin)):
    run = s.get(AiRun, run_id)
    if not run:
        raise HTTPException(404, tr("Unknown run"))
    qs = {q["key"]: q for q in audit.questions(s.get(Country, run.country_id))}
    rows = s.scalars(select(AiAnswer).where(AiAnswer.run_id == run.id).order_by(AiAnswer.id)).all()
    srcs = defaultdict(list)
    for x in s.scalars(select(AiSource).where(AiSource.answer_id.in_(select(AiAnswer.id).where(AiAnswer.run_id == run.id)))
                       .order_by(AiSource.role, AiSource.rank, AiSource.id)):
        srcs[x.answer_id].append(x)
    ids = {x.outlet_id for v in srcs.values() for x in v if x.outlet_id}
    names = dict(s.execute(select(Outlet.id, Outlet.name).where(Outlet.id.in_(ids))).all()) if ids else {}
    out = []
    for a in rows:
        q = qs.get(a.question_key) or {}
        out.append({"id": a.id, "question_key": a.question_key, "question": q.get(a.lang) or a.question_key,
                    "question_version": a.question_version,
                    "question_changed": bool(q) and q.get("version") != a.question_version,
                    "lang": a.lang, "status": a.status, "answer_lang": a.answer_lang, "answer_chars": a.answer_chars,
                    "queries": a.queries or [], "n_searched": a.n_searched, "n_cited": a.n_cited, "searches": a.searches,
                    "cost_usd": round(a.cost_usd or 0, 6),
                    "searched": [_source_json(x, names, False) for x in srcs[a.id] if x.role == "searched"],
                    "cited": [_source_json(x, names, True) for x in srcs[a.id] if x.role == "cited"]})
    return out


@router.get("/admin/ai-audit/unknown-domains")
def ai_unknown_domains(weeks: int = 12, country: str = "LY", s: Session = Depends(get_db),
                       _: User = Depends(auth.require_admin)):
    """Domains no register outlet matched (social platforms and open-posting sites are left out: their
    accounts are not kept). ly marks a .ly domain, a likely Libyan outlet to add."""
    c = country_or_404(s, country)
    start = audit.week_start_of(_today()) - timedelta(weeks=max(1, min(weeks, 104)) - 1)
    agg: dict = defaultdict(lambda: {"cited": 0, "searched": 0})
    for dom, role, n in s.execute(select(AiSource.domain, AiSource.role, func.count(AiSource.id))
                                  .join(AiAnswer, AiAnswer.id == AiSource.answer_id).join(AiRun, AiRun.id == AiAnswer.run_id)
                                  .where(AiSource.outlet_id.is_(None), AiSource.match == "unknown", AiRun.country_id == c.id,
                                         AiRun.week_start >= start)
                                  .group_by(AiSource.domain, AiSource.role)):
        agg[dom][role] += n
    out = [{"domain": d, "cited": v["cited"], "searched": v["searched"], "ly": d.endswith(".ly")} for d, v in agg.items()]
    return sorted(out, key=lambda r: (-r["cited"], -r["searched"], r["domain"]))


class RunIn(BaseModel):
    provider: str | None = None
    force: bool = False
    dry_run: bool = True      # the safe default: a plan and an estimate, no call


@router.post("/admin/ai-audit/run")
def ai_run(body: RunIn, bg: BackgroundTasks, country: str = "LY", s: Session = Depends(get_db),
           _: User = Depends(auth.require_admin)):
    cfg = audit.load_config()
    if body.provider is not None and body.provider not in audit.known_keys(cfg):
        raise HTTPException(400, tr("Unknown provider"))
    c = country_or_404(s, country)
    if body.dry_run:
        return audit.run_week(s, c, providers=body.provider, force=body.force, dry_run=True)
    if audit.is_busy():
        raise HTTPException(409, tr("The AI answers audit is already running."))
    from ..jobs import ai_audit
    bg.add_task(ai_audit, provider=body.provider, force=body.force)
    return {"started": True}
