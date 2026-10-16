"""Weekly AI digest: one short brief per country per week, written from facts computed here.

The model only sees the facts dict (counts, flags, a few headlines), never raw articles or user
data, and the facts are stored with the text so any claim can be checked. One call per week;
without credentials the job records "awaiting_key" and the rest of the app is unaffected."""
import json
import logging
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from . import settings
from .models import (CellWeek, Comment, Country, Digest, GapClaim, GapVote, Item, ItemRegion, ItemTheme, Region,
                     Theme, utcnow)
from .scoring import LENSES, week_start

log = logging.getLogger("desert_watch.digest")

SYSTEM = """You write the weekly brief for Desert Watch, a tool that helps journalists find under-reported \
topics in {country}. Readers are journalists deciding what to cover next.

Rules:
- Use only the facts in the JSON you are given. Every number you mention must appear in it. Do not \
add context from your own knowledge, and do not speculate about causes.
- Never name private individuals, victims or survivors, even if a headline does. Public officials \
and institutions may be named when a headline names them.
- "Coverage" means monitored coverage (news sites and search results the tool can see), not all \
reporting. Say "monitored" where it matters.
- Prefer concrete, checkable statements ("14 articles, all in Arabic") over adjectives.
- Write in plain English. Use Markdown with exactly these headings, in this order, and keep the \
whole brief under 450 words:
  ## This week in brief
  ## Biggest gaps
  ## Gender
  ## Silent places
  ## What the team is doing
  ## Caveats
- If a section has nothing to report, write one sentence saying so."""


def _client():
    import anthropic
    return anthropic.Anthropic()


def has_credentials() -> bool:
    import os
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


# Gaps on the search lens (Google Trends) read differently from the others: the model must see why.
SEARCH_LIMIT = ("search lens: need is a Google Trends index of searches from Libya for the theme's own words, "
                "per 100 searches for an everyday word. The word list sets its size, so compare a theme only "
                "with its own past. A search gap means searches rose and monitored coverage did not keep up. "
                "It does not show that nobody reported the subject")


def build_facts(s: Session, country: Country, week: date) -> dict:
    themes = {t.id: t for t in s.scalars(select(Theme).where(Theme.active.is_(True)))}
    regions = {r.id: r for r in s.scalars(select(Region).where(Region.country_id == country.id))}
    national = next(r for r in regions.values() if r.level == "national")
    win_end = datetime.combine(week + timedelta(days=7), datetime.min.time())
    win_start = win_end - timedelta(weeks=settings.WINDOW_WEEKS)
    prev_start = win_start - timedelta(weeks=settings.WINDOW_WEEKS)

    def counts(start, end):
        rows = s.execute(select(ItemTheme.theme_id, Item.lang, func.count(Item.id))
                         .join(Item, Item.id == ItemTheme.item_id)
                         .where(Item.country_id == country.id, Item.kind == "article", Item.relevant.is_(True), Item.duplicate_of.is_(None),
                                ItemTheme.active.is_(True), Item.published_at >= start, Item.published_at < end)
                         .group_by(ItemTheme.theme_id, Item.lang)).all()
        out = defaultdict(Counter)
        for tid, lang, n in rows:
            out[tid][lang or "und"] += n
        return out

    now, prev = counts(win_start, win_end), counts(prev_start, win_start)
    coverage = []
    for tid, t in themes.items():
        c, p = now.get(tid, Counter()), prev.get(tid, Counter())
        total = sum(c.values())
        coverage.append({"theme": t.name_en, "group": t.group or "general", "articles": total,
                         "arabic": c.get("ar", 0), "english": c.get("en", 0),
                         "previous_window": sum(p.values())})

    # scored gaps for every lens that has data this week
    gaps = []
    for lens in LENSES:
        for cell in s.scalars(select(CellWeek).where(CellWeek.country_id == country.id, CellWeek.week_start == week,
                                                     CellWeek.lens == lens, CellWeek.insufficient.is_(False),
                                                     CellWeek.gap.is_not(None))):
            gaps.append({"theme": themes[cell.theme_id].name_en if cell.theme_id in themes else "?",
                         "region": regions[cell.region_id].name_en, "lens": lens, "gap": round(cell.gap, 2),
                         "times_less_coverage_than_expected": round(2.718281828 ** cell.gap, 1),
                         "articles": int(cell.coverage), "need": round(cell.need), "flags": cell.flags})
    gaps.sort(key=lambda g: -g["gap"])

    # districts: articles naming each one in the window (all themes, and gender only)
    gender_ids = {t.id for t in themes.values() if t.group == "gender"}
    rows = s.execute(select(ItemRegion.region_id, ItemTheme.theme_id, func.count(func.distinct(Item.id)))
                     .join(Item, Item.id == ItemRegion.item_id)
                     .join(ItemTheme, and_(ItemTheme.item_id == Item.id, ItemTheme.active.is_(True)))
                     .where(Item.country_id == country.id, Item.kind == "article", Item.relevant.is_(True), Item.duplicate_of.is_(None),
                            ItemRegion.active.is_(True), Item.published_at >= win_start, Item.published_at < win_end)
                     .group_by(ItemRegion.region_id, ItemTheme.theme_id)).all()
    by_district, gender_by_district = Counter(), Counter()
    for rid, tid, n in rows:
        by_district[rid] += n
        if tid in gender_ids:
            gender_by_district[rid] += n
    districts = [r for r in regions.values() if r.level == "district"]
    silent = sorted(r.name_en for r in districts if by_district.get(r.id, 0) == 0)
    gender_named = sorted(((regions[r].name_en, n) for r, n in gender_by_district.items()
                           if regions.get(r) and regions[r].level == "district"), key=lambda x: -x[1])

    # flags on national cells this week (outside-only, little Arabic, coverage drop...)
    flags = Counter()
    for cell in s.scalars(select(CellWeek).where(CellWeek.country_id == country.id, CellWeek.week_start == week,
                                                 CellWeek.region_id == national.id)):
        for f in cell.flags or []:
            if f != "mostly_unplaced":
                flags[f"{themes[cell.theme_id].name_en}: {f}"] += 1

    # a few recent headlines for gender themes (for colour, not names)
    headlines = []
    for tid in gender_ids:
        for title, lang in s.execute(select(Item.title, Item.lang).join(ItemTheme, ItemTheme.item_id == Item.id)
                                     .where(ItemTheme.theme_id == tid, ItemTheme.active.is_(True),
                                            Item.relevant.is_(True), Item.duplicate_of.is_(None), Item.kind == "article",
                                            Item.published_at >= win_start, Item.published_at < win_end)
                                     .order_by(Item.published_at.desc()).limit(3)):
            headlines.append({"theme": themes[tid].name_en, "lang": lang, "title": (title or "")[:160]})

    # team activity (counts only; no names)
    since = datetime.combine(week, datetime.min.time())
    votes = Counter(v for (v,) in s.execute(select(GapVote.vote).where(GapVote.created_at >= since)))
    claims = Counter(c for (c,) in s.execute(select(GapClaim.status).where(GapClaim.updated_at >= since)))
    comments = s.scalar(select(func.count(Comment.id)).where(Comment.created_at >= since, Comment.deleted.is_(False)))

    return {
        "country": country.name_en, "week_starting": week.isoformat(),
        "window": f"{win_start.date().isoformat()} to {(win_end - timedelta(days=1)).date().isoformat()}",
        "coverage_by_theme": coverage, "top_gaps": gaps[:8],
        "lenses_with_data": sorted({g["lens"] for g in gaps}),
        "districts_with_no_monitored_articles": silent, "districts_total": len(districts),
        "gender_articles_naming_a_district": gender_named,
        "flags_this_week": dict(flags), "recent_gender_headlines": headlines[:12],
        "team_activity_this_week": {"gap_votes": dict(votes), "claims": dict(claims), "comments": comments or 0},
        "known_limits": ["monitored coverage only (Facebook only as the sample of posts Google indexes, no Telegram)",
                         "event and humanitarian need data are pending source keys" if not
                         {"events", "humanitarian"} & {g["lens"] for g in gaps} else "",
                         "most articles name no district",
                         *([SEARCH_LIMIT] if "search" in {g["lens"] for g in gaps} else [])],
    }


def generate(s: Session, country: Country, week: date | None = None, force: bool = False) -> Digest:
    week = week or week_start(date.today() - timedelta(days=7))  # last complete week
    existing = s.scalar(select(Digest).where(Digest.country_id == country.id, Digest.week_start == week))
    if existing and existing.status == "ok" and not force:
        return existing
    facts = build_facts(s, country, week)
    d = existing or Digest(country_id=country.id, week_start=week, model=settings.DIGEST_MODEL, status="error")
    d.facts, d.model, d.created_at = facts, settings.DIGEST_MODEL, utcnow()
    if not existing:
        s.add(d)
    try:
        resp = _client().messages.create(
            model=settings.DIGEST_MODEL,
            max_tokens=4000,
            system=SYSTEM.format(country=country.name_en),
            messages=[{"role": "user", "content": "Facts for this week's brief (JSON):\n\n"
                       + json.dumps(facts, ensure_ascii=False, sort_keys=True)}],
        )
    except Exception as e:  # noqa: BLE001 - recorded, never raised into the scheduler
        d.status, d.error, d.content_md = "error", f"{type(e).__name__}: {e}"[:1000], None
        s.commit()
        log.warning("digest failed: %s", d.error)
        return d
    d.usage = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
    if resp.stop_reason == "refusal":
        d.status, d.content_md = "refused", None
        d.error = f"Model declined ({getattr(resp.stop_details, 'category', None)})"
    else:
        d.status, d.error = "ok", None
        d.content_md = "\n".join(b.text for b in resp.content if b.type == "text").strip()
        if resp.stop_reason == "max_tokens":
            d.content_md += "\n\n*(Brief was cut off at the length limit.)*"
    s.commit()
    return d


def generate_all(s: Session, **kw) -> list[Digest]:
    return [generate(s, c, **kw) for c in s.scalars(select(Country))]
