"""The AI answers audit from the apps people actually use: the journalist panel and supervised browser sessions.

Three origins, never counted together (the summary takes one at a time):
- api: the automatic weekly run through the developers' APIs (ai_audit/runner.py);
- panel: a journalist asks one of the week's questions in the app on their own phone (ChatGPT app, Gemini,
  Google's AI Overview or AI Mode, Meta AI ...) and logs the source links the answer showed, or that it
  showed none;
- browser: an admin signs in to a chatbot in a browser, Claude asks the questions while the admin watches,
  and only the source links are logged, through the same path (asked from London, admins only).

What is kept for an entry: the question, the language, the app, where it was asked from (Libya, elsewhere,
or London for a browser session) and the links, matched read-only to the outlet register by the audit's own
matcher (stored as role 'cited': the apps show the links an answer used). Never the answer text. An unlisted
social account is kept as its platform only. Full links stay on the admin routes. Who logged an entry is
kept only so that person can delete it, and is set to NULL when their account is deleted. Nobody else is
shown who logged what: the admin drill-down says "A team member".

Entries hang off one ai_run per (country, week, app, origin), made with the week's first entry: model null,
cost 0, so they never count against the weekly cap. Nothing here writes Item, ItemTheme or CellWeek."""
import re
import threading
from collections import Counter
from datetime import date, datetime, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from .. import auth
from ..ai_audit import runner as audit
from ..ai_audit.matcher import Matcher, clean_url
from ..db import get_db
from ..i18n import N_, tr
from ..models import AiAnswer, AiRun, AiSource, Country, User, utcnow
from .common import country_or_404

router = APIRouter(prefix="/api")

ORIGINS = ("api", "panel", "browser")
LOGGED = ("panel", "browser")              # the origins people log by hand
LOGGED_STATUSES = ("ok", "no_sources")     # an entry with links, or one whose answer showed no sources
ASKED_IN = ("LY", "other", "London")       # London: a supervised browser session (the owner is in London)
BROWSER_ASKED_IN = "London"
# The consumer apps, in the order the form lists them. The frontend shows these labels (translated here).
APPS = {
    "chatgpt_app": N_("ChatGPT app"),
    "gemini_app": N_("Gemini"),
    "google_ai": N_("Google AI Overview or AI Mode"),
    "meta_ai": N_("Meta AI (WhatsApp, Facebook, Instagram)"),
    "copilot_app": N_("Copilot"),
    "perplexity_app": N_("Perplexity app"),
    "claude_app": N_("Claude app"),
    "grok_app": N_("Grok"),
    "deepseek_app": N_("DeepSeek"),
    "other_app": N_("Other"),
}
WEEKLY_LIMIT = 40     # entries per person per week, both logged origins together
MAX_LINKS = 30        # links per entry, after duplicates are dropped
MAX_TEXT = 40000      # characters of pasted text
TEAM_MEMBER = N_("A team member")

# Links are taken from the pasted text only when they start with http:// or https://. Bidi and zero-width
# marks (common when copying from a right-to-left app) are removed first; a comma, semicolon or bar right
# before the next link separates two links pasted without a space.
_MARKS = re.compile("[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
_GLUED = re.compile(r"[,\u060c;|](?=https?://)", re.IGNORECASE)
_URL = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
_TRAIL = ".,;:!?\u060c\u061b\u061f'\"\u201d\u2019>\u00bb\u2026*_"
_CLOSERS = {")": "(", "]": "[", "}": "{"}

_RUN_LOCK = threading.Lock()   # one get-or-create of a week's run at a time (two first entries at once)


class EntryError(Exception):
    """A refused entry: the HTTP status and the message, already in the request's language."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def origin_clause(origin: str):
    """The WHERE clause for one origin's runs. Rows from before the column existed are developer-API runs."""
    if origin == "api":
        return or_(AiRun.origin == "api", AiRun.origin.is_(None))
    return AiRun.origin == origin


def app_label(key: str) -> str:
    return tr(APPS[key]) if key in APPS else key


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _trim(u: str) -> str:
    """Punctuation after a link is not part of it. A closing bracket stays when the link opened one
    (Wikipedia: .../Libya_(disambiguation))."""
    while u:
        c = u[-1]
        if c in _CLOSERS:
            if u.count(_CLOSERS[c]) >= u.count(c):
                break
        elif c not in _TRAIL:
            break
        u = u[:-1]
    return u


def extract_urls(text: str | list | None) -> list[str]:
    """The http(s) links in pasted text, in order, each once (compared after the matcher's clean-up:
    redirect and AMP wrappers and tracking parameters removed)."""
    if isinstance(text, (list, tuple)):
        text = "\n".join(str(x) for x in text)
    text = _GLUED.sub(" ", _MARKS.sub("", text or ""))
    out, seen = [], set()
    for m in _URL.finditer(text):
        u = _trim(m.group(0))
        try:
            p = urlsplit(u)
            host = p.hostname or ""
        except ValueError:
            continue
        if p.scheme.lower() not in ("http", "https") or "." not in host or host.startswith(".") or host.endswith("."):
            continue
        key = clean_url(u)
        if key in seen:
            continue
        seen.add(key)
        out.append(u)
    return out


def week_questions(country: Country) -> list[dict]:
    return audit.questions(country)


def used_this_week(s: Session, user_id: int, week: date) -> int:
    return int(s.scalar(select(func.count(AiAnswer.id)).join(AiRun, AiRun.id == AiAnswer.run_id).where(
        AiAnswer.logged_by == user_id, AiAnswer.origin.in_(LOGGED), AiRun.week_start == week)) or 0)


def _week_run(s: Session, country: Country, week: date, app: str, origin: str) -> AiRun:
    run = s.scalar(select(AiRun).where(AiRun.country_id == country.id, AiRun.week_start == week, AiRun.provider == app,
                                       AiRun.origin == origin).order_by(AiRun.id).limit(1))
    if run is None:
        run = AiRun(country_id=country.id, provider=app, origin=origin, week_start=week, model=None, tool=None,
                    status="ok", settings={}, usage={}, cost_usd=0.0, price_basis={}, forced=False)
        s.add(run)
        s.flush()
    run.finished_at = utcnow()   # the latest entry
    return run


def validate_entry(country: Country, *, origin: str, question_key: str, lang: str, app: str, asked_in: str | None,
                   no_sources: bool, links, is_admin: bool) -> tuple[dict, str, list[str]]:
    """(the question, asked_in as stored, the links to keep) or EntryError. Writes nothing."""
    if origin not in LOGGED:
        raise EntryError(400, tr("Unknown origin"))
    if origin == "browser" and not is_admin:
        raise EntryError(403, tr("Only admins can log a browser session."))
    q = next((x for x in week_questions(country) if x["key"] == question_key), None)
    if q is None:
        raise EntryError(400, tr("Unknown question"))
    if lang not in audit.LANGS:
        raise EntryError(400, tr("Unknown language"))
    if app not in APPS:
        raise EntryError(400, tr("Unknown app"))
    if origin == "browser":
        asked_in = BROWSER_ASKED_IN
    elif asked_in not in ("LY", "other"):
        raise EntryError(400, tr("Say where the question was asked from: Libya or elsewhere."))
    text_len = sum(len(str(x)) for x in links) if isinstance(links, (list, tuple)) else len(links or "")
    if text_len > MAX_TEXT:
        raise EntryError(400, tr("Too much text. Paste the links only."))
    urls = [] if no_sources else extract_urls(links)
    if not no_sources and not urls:
        raise EntryError(400, tr("Paste at least one link that starts with http:// or https://, or mark the answer as showing no sources."))
    if len(urls) > MAX_LINKS:
        raise EntryError(400, tr("At most {n} links per entry.", n=MAX_LINKS))
    return q, asked_in, urls


def log_entry(s: Session, country: Country, *, user_id: int | None, is_admin: bool, origin: str, question_key: str,
              lang: str, app: str, asked_in: str | None, no_sources: bool, links, check_limit: bool = True,
              matcher: Matcher | None = None, today: date | None = None) -> dict:
    """Stores one entry and its links (commits). The API and the CLI import both come through here."""
    q, asked_in, urls = validate_entry(country, origin=origin, question_key=question_key, lang=lang, app=app,
                                       asked_in=asked_in, no_sources=no_sources, links=links, is_admin=is_admin)
    week = audit.week_start_of(today or _today())
    matcher = matcher or Matcher(s)
    matches = [m for m in (matcher.match(u) for u in urls) if m is not None]
    with _RUN_LOCK:
        if check_limit and user_id is not None and used_this_week(s, user_id, week) >= WEEKLY_LIMIT:
            raise EntryError(429, tr("The weekly limit of {n} entries is reached. It resets on Monday.", n=WEEKLY_LIMIT))
        run = _week_run(s, country, week, app, origin)
        a = AiAnswer(run_id=run.id, question_key=q["key"], question_version=q["version"], lang=lang,
                     status="no_sources" if no_sources else "ok", answer_lang=None, answer_chars=None, queries=[],
                     n_searched=0, n_cited=len(matches), searches=0, cost_usd=0.0, origin=origin, logged_by=user_id,
                     asked_in=asked_in)
        s.add(a)
        s.flush()
        for rank, m in enumerate(matches, start=1):
            # no title (the apps give none here) and no citation-span count (citations 0): only the link
            s.add(AiSource(answer_id=a.id, role="cited", rank=rank, url=m.url[:2000], domain=m.domain[:200],
                           outlet_id=m.outlet_id, family_id=m.family_id, match=m.match, title=None, lang=m.lang,
                           date=None, citations=0))
        s.commit()
    matched = sum(1 for m in matches if m.outlet_id is not None)
    return {"id": a.id, "links": len(matches), "matched": matched, "unknown": len(matches) - matched}


def _counts(s: Session, answer_ids: list[int]) -> dict[int, tuple[int, int]]:
    """answer id -> (links, links matched to a register outlet)."""
    out: dict[int, list[int]] = {}
    if answer_ids:
        for aid, oid, n in s.execute(select(AiSource.answer_id, AiSource.outlet_id.is_not(None), func.count(AiSource.id))
                                     .where(AiSource.answer_id.in_(answer_ids))
                                     .group_by(AiSource.answer_id, AiSource.outlet_id.is_not(None))):
            row = out.setdefault(aid, [0, 0])
            row[0] += n
            if oid:
                row[1] += n
    return {k: (v[0], v[1]) for k, v in out.items()}


# ---------------------------------------------------------------- routes
@router.get("/ai-panel/week")
def panel_week(country: str = "LY", s: Session = Depends(get_db), u: User = Depends(auth.current_user)):
    """The week's questions in both languages, the apps, and the signed-in person's own entries this week."""
    c = country_or_404(s, country)
    week = audit.week_start_of(_today())
    rows = s.execute(select(AiAnswer, AiRun.provider).join(AiRun, AiRun.id == AiAnswer.run_id).where(
        AiAnswer.logged_by == u.id, AiAnswer.origin.in_(LOGGED), AiRun.week_start == week, AiRun.country_id == c.id)
        .order_by(AiAnswer.id.desc())).all()
    counts = _counts(s, [a.id for a, _p in rows])
    mine = []
    for a, app in rows:
        n, matched = counts.get(a.id, (0, 0))
        mine.append({"id": a.id, "question_key": a.question_key, "lang": a.lang, "app": app, "app_label": app_label(app),
                     "asked_in": a.asked_in, "no_sources": a.status == "no_sources", "links": n, "matched": matched,
                     "unknown": n - matched, "created_at": a.created_at.isoformat() if a.created_at else None,
                     "origin": a.origin})
    return {"week_start": week.isoformat(),
            "questions": [{"key": q["key"], "theme": q.get("theme"), "en": q["en"], "ar": q["ar"]} for q in week_questions(c)],
            "apps": [{"key": k, "label": tr(v)} for k, v in APPS.items()],
            "mine": mine, "limit": WEEKLY_LIMIT, "used": used_this_week(s, u.id, week), "max_links": MAX_LINKS,
            "can_log": u.role != "viewer", "can_log_browser": u.role == "admin"}


class EntryIn(BaseModel):
    question_key: str
    lang: str
    app: str
    asked_in: str | None = None      # LY | other (a browser session is always London)
    no_sources: bool = False
    links: str | list[str] = ""      # free text: every http(s) link in it is kept
    origin: str = "panel"            # panel | browser (admins only)


@router.post("/ai-panel/entries")
def panel_log(body: EntryIn, country: str = "LY", s: Session = Depends(get_db), u: User = Depends(auth.require_contributor)):
    c = country_or_404(s, country)
    try:
        return log_entry(s, c, user_id=u.id, is_admin=u.role == "admin", origin=body.origin,
                         question_key=body.question_key, lang=body.lang, app=body.app, asked_in=body.asked_in,
                         no_sources=body.no_sources, links=body.links)
    except EntryError as e:
        s.rollback()
        raise HTTPException(e.status, e.message)


@router.delete("/ai-panel/entries/{entry_id}")
def panel_delete(entry_id: int, s: Session = Depends(get_db), u: User = Depends(auth.current_user)):
    """The person who logged the entry, or an admin. A developer-API answer is not an entry and is not
    deleted here."""
    a = s.get(AiAnswer, entry_id)
    if a is None or a.origin not in LOGGED:
        raise HTTPException(404, tr("Unknown entry"))
    if u.role != "admin" and (a.logged_by is None or a.logged_by != u.id):
        raise HTTPException(403, tr("Only the person who logged this entry, or an admin, can delete it."))
    run_id = a.run_id
    with _RUN_LOCK:   # an entry logged at the same moment must not land on a run deleted here
        s.execute(delete(AiSource).where(AiSource.answer_id == a.id))   # links first (no ORM relationship orders it)
        s.delete(a)
        s.flush()
        run = s.get(AiRun, run_id)
        if run is not None and run.origin in LOGGED and not s.scalar(
                select(func.count(AiAnswer.id)).where(AiAnswer.run_id == run_id)):
            s.delete(run)   # the week's last entry for that app: the empty run goes too
        s.commit()
    return {"ok": True}


# ---------------------------------------------------------------- CLI import (python -m app.cli ai-panel-import)
def import_entries(s: Session, items, *, origin: str = "browser", country: str = "LY", by: str | None = None,
                   dry_run: bool = False, today: date | None = None) -> dict:
    """The admin path for a supervised browser session: a JSON list of {question_key, lang, app, links,
    no_sources} (links: text or a list; a panel import also needs asked_in LY | other). Everything is checked
    before anything is written, and one bad entry stores none. `by` is an account email, kept as logged_by
    (so that person can delete the entries); without it the entries have no author. --dry-run matches the
    links and writes nothing."""
    c = s.scalar(select(Country).where(Country.iso2 == (country or "").upper()))
    if c is None:
        return {"stored": 0, "errors": [f"unknown country {country}"]}
    if not isinstance(items, list) or not all(isinstance(x, dict) for x in items):
        return {"stored": 0, "errors": ["the file must hold a JSON list of objects"]}
    user_id = None
    if by:
        u = s.scalar(select(User).where(User.email == by.strip().lower()))
        if u is None or not u.active:
            return {"stored": 0, "errors": [f"no active account {by}"]}
        user_id = u.id
    errors, checked = [], []
    for i, x in enumerate(items):
        try:
            checked.append(validate_entry(c, origin=origin, question_key=str(x.get("question_key") or ""),
                                          lang=str(x.get("lang") or ""), app=str(x.get("app") or ""),
                                          asked_in=x.get("asked_in"), no_sources=bool(x.get("no_sources")),
                                          links=x.get("links") or "", is_admin=True))
        except EntryError as e:
            errors.append(f"entry {i + 1}: {e.message}")
    if errors:
        return {"stored": 0, "errors": errors}
    matcher = Matcher(s)
    if dry_run:
        found = [m for _q, _a, urls in checked for m in (matcher.match(u) for u in urls) if m is not None]
        matched = sum(1 for m in found if m.outlet_id is not None)
        return {"stored": 0, "dry_run": True, "entries": len(checked), "links": len(found), "matched": matched,
                "unknown": len(found) - matched, "errors": []}
    totals = Counter()
    for x in items:
        res = log_entry(s, c, user_id=user_id, is_admin=True, origin=origin, question_key=str(x["question_key"]),
                        lang=str(x["lang"]), app=str(x["app"]), asked_in=x.get("asked_in"),
                        no_sources=bool(x.get("no_sources")), links=x.get("links") or "", check_limit=False,
                        matcher=matcher, today=today)
        totals.update({k: res[k] for k in ("links", "matched", "unknown")})
    return {"stored": len(items), "origin": origin, **{k: totals[k] for k in ("links", "matched", "unknown")},
            "errors": []}


# ---------------------------------------------------------------- account (api/account.py)
def entries_for_export(s: Session, user_id: int) -> list[dict]:
    """A person's own entries for their data export: question, language, app, where it was asked from,
    and the links as stored (an unlisted social account is stored as its platform only)."""
    rows = s.execute(select(AiAnswer, AiRun).join(AiRun, AiRun.id == AiAnswer.run_id)
                     .where(AiAnswer.logged_by == user_id, AiAnswer.origin.in_(LOGGED)).order_by(AiAnswer.id)).all()
    links: dict[int, list[str]] = {}
    if rows:
        for aid, url in s.execute(select(AiSource.answer_id, AiSource.url).where(
                AiSource.answer_id.in_([a.id for a, _r in rows])).order_by(AiSource.answer_id, AiSource.rank, AiSource.id)):
            links.setdefault(aid, []).append(url)
    qs: dict[int, dict] = {}
    out = []
    for a, run in rows:
        if run.country_id not in qs:
            c = s.get(Country, run.country_id)
            qs[run.country_id] = {q["key"]: q for q in week_questions(c)} if c else {}
        q = qs[run.country_id].get(a.question_key) or {}
        out.append({"id": a.id, "week_start": run.week_start.isoformat(), "origin": a.origin,
                    "question_key": a.question_key, "question": q.get(a.lang) or a.question_key, "lang": a.lang,
                    "app": run.provider, "asked_in": a.asked_in, "no_sources": a.status == "no_sources",
                    "links": links.get(a.id, []), "created_at": a.created_at})
    return out


def forget_author(s: Session, user_id: int) -> int:
    """Account deletion: the entries stay (the team's evidence), without the person."""
    n = 0
    for a in s.scalars(select(AiAnswer).where(AiAnswer.logged_by == user_id)):
        a.logged_by = None
        n += 1
    return n
