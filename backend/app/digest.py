"""Weekly AI digest: one short brief per country per week, written from facts computed here.

The model only sees the facts dict (counts, flags, theme and district names; no headlines since 2026-10-17), never raw articles or user
data, and the facts are stored with the text so any claim can be checked. One call per week writes
the brief in English and then in Arabic (split at ARABIC_MARKER); without credentials the job
records "awaiting_key" and the rest of the app is unaffected."""
import json
import logging
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from . import settings
from .models import (BasisDeparture, CellWeek, Comment, Country, Digest, GapClaim, GapVote, Item, ItemRegion, ItemTheme,
                     Region, Theme, utcnow)
from .scoring import LENSES, counted_items, latest_complete_week, scored_articles, week_start

log = logging.getLogger("desert_watch.digest")

SYSTEM = """You write the weekly brief for Desert Watch, a tool that helps journalists find under-reported \
topics in {country}. Readers are journalists deciding what to cover next.

Rules:
- Use only the facts in the JSON you are given. Every number you mention must appear in it. Do not \
add context from your own knowledge, and do not speculate about causes.
- Never name any person. Institutions may be named when the JSON names them.
- "Coverage" means monitored coverage (news sites and search results the tool can see), not all \
reporting. Say "monitored" where it matters.
- Each gap in top_gaps carries a verdict. Only "short" is a gap: fewer articles than chance would \
explain. "possibly_short" is possibly fewer, not enough to be sure; "usual" is about as expected; \
"over" is more than expected; "unclear" could not be judged. Report a gap with its own numbers, \
verbatim: the articles against the expected count, the likely range ("likely 1.8 to 3.6 times \
fewer", from likely_times_fewer_low and likely_times_fewer_high) and the chance ("happens by chance \
about once in 50 such weeks", from chance_one_in; 1000 means once in 1000 or rarer; null means it \
could easily be chance). Call a gap "new" only when new_short is true; otherwise it was already \
short the week before. About 1 red gap in 10 is still chance, and the brief says so once.
- Prefer concrete, checkable statements ("14 articles, all in Arabic") over adjectives.
- Write in plain English. Use Markdown with exactly these headings, in this order, and keep the \
whole brief under 450 words:
  ## This week in brief
  ## Biggest gaps
  ## Gender
  ## Silent places
  ## What the team is doing
  ## Caveats
- If a section has nothing to report, write one sentence saying so.
- Then write a line containing only {marker} and, after it, the same brief in Arabic: the same facts, \
numbers and rules, in Modern Standard Arabic for Libyan journalists, with Western digits (0-9). Address \
no reader as male or female (use impersonal forms). Use exactly these headings, in this order:
  ## الأسبوع باختصار
  ## أكبر الفجوات
  ## النوع الاجتماعي
  ## أماكن صامتة
  ## ما يعمل عليه الفريق
  ## تنبيهات"""
ARABIC_MARKER = "===ARABIC==="


def split_brief(text: str) -> tuple[str, str | None]:
    """(English, Arabic) from the model's one answer; Arabic is None when the marker is missing."""
    if ARABIC_MARKER not in text:
        return text.strip(), None
    en, ar = text.split(ARABIC_MARKER, 1)
    return en.strip(), ar.strip() or None


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


# What the article counts are, so a new route into the data is never read as a rise in coverage.
COUNTS_LIMIT = ("articles and previous_window count stories from the outlets and routes monitored across the whole "
                "compared period (the counts the gaps use); articles_all and previous_window_all count every monitored "
                "source, so they rise whenever a feed or social route is added. A story found by two routes counts once. "
                "Recurring posts (daily rates, weather) are left out")
UNSCORED_LIMIT = ("this week has no scores, so articles and previous_window count every monitored source and rise "
                  "whenever a feed or social route is added")
# What a verdict is, for the facts: red (short) is a shortfall larger than chance would explain, judged
# with a false-discovery rate of 10% across the week's cells, so about 1 red gap in 10 is still chance.
VERDICT_LIMIT = ("a gap's verdict is short only when the shortfall is larger than chance would explain (false-discovery "
                 "rate 10% across the week, so about 1 short gap in 10 is still chance) and the shortfall is at least "
                 "{floor}x; possibly_short is fewer but not enough to be sure; usual is about as expected; over is more "
                 "than expected; unclear could not be judged. A gap is new only when new_short is true")
# Which lenses the gaps come from: only the ones the site offers (api.gaps.available_lenses). A lens the
# site has switched off has too few judged themes to compare, so its cells are not gaps here either.
LENSES_LIMIT = ("gaps are reported only on the lenses the site offers now ({lenses}); a lens with too few judged "
                "themes is left out, so a theme judged alone on a switched-off lens is not a gap")
# Outlets whose route stopped reaching us (scoring.record_departures): their articles left every compared
# week with them, so their silence shows as no gap. {n} outlets, {weeks} weeks.
DEPARTURES_LIMIT = ("{n} outlet{s} left the comparison in the last {weeks} weeks: they stopped reaching us, so their "
                    "articles were removed from every week compared and their silence does not show as a gap")


def build_facts(s: Session, country: Country, week: date) -> dict:
    themes = {t.id: t for t in s.scalars(select(Theme).where(Theme.active.is_(True)))}
    regions = {r.id: r for r in s.scalars(select(Region).where(Region.country_id == country.id))}
    national = next(r for r in regions.values() if r.level == "national")
    win_end = datetime.combine(week + timedelta(days=7), datetime.min.time())
    win_start = win_end - timedelta(weeks=settings.WINDOW_WEEKS)
    prev_start = win_start - timedelta(weeks=settings.WINDOW_WEEKS)

    # coverage per theme: the scored counts (stories from comparable source|outlet pairs, the ones the
    # gaps use) from the week's national cells, beside the all-source counts, and the previous window
    # on the same pairs. Both windows then count the same outlets, so a new feed or social route does
    # not read as a rise. A week that was never scored falls back to all-source counts and says so.
    nat_cells = s.scalars(select(CellWeek).where(CellWeek.country_id == country.id, CellWeek.week_start == week,
                                                 CellWeek.region_id == national.id)).all()
    by_theme: dict[int, CellWeek] = {}
    for cell in nat_cells:   # prefer a lens that counts the whole week (a daily lens cuts coverage at its last need day)
        cur = by_theme.get(cell.theme_id)
        if cur is None or (LENSES[cur.lens].get("daily") and not LENSES[cell.lens].get("daily")):
            by_theme[cell.theme_id] = cell
    scored = bool(by_theme)

    def counts(start, end):
        rows = s.execute(select(ItemTheme.theme_id, Item.lang, func.count(Item.id))
                         .join(Item, Item.id == ItemTheme.item_id)
                         .where(*counted_items(country.id), Item.kind == "article", ItemTheme.active.is_(True),
                                Item.published_at >= start, Item.published_at < end)
                         .group_by(ItemTheme.theme_id, Item.lang)).all()
        out = defaultdict(Counter)
        for tid, lang, n in rows:
            out[tid][lang or "und"] += n
        return out

    now, prev = (counts(win_start, win_end), counts(prev_start, win_start)) if not scored else ({}, {})
    coverage = []
    for tid, t in themes.items():
        cell = by_theme.get(tid)
        if cell is not None:
            b = cell.breakdown or {}
            langs = b.get("scored_lang") or {}
            coverage.append({"theme": t.name_en, "group": t.group or "general", "articles": scored_articles(cell),
                             "articles_all": int(cell.coverage), "arabic": langs.get("ar", 0), "english": langs.get("en", 0),
                             "previous_window": b.get("prev_scored_coverage"), "previous_window_all": b.get("prev_coverage")})
        else:
            c, p = now.get(tid, Counter()), prev.get(tid, Counter())
            total = sum(c.values())
            coverage.append({"theme": t.name_en, "group": t.group or "general", "articles": total, "articles_all": total,
                             "arabic": c.get("ar", 0), "english": c.get("en", 0),
                             "previous_window": sum(p.values()), "previous_window_all": sum(p.values())})

    # scored gaps for every lens the site offers now (api.gaps.available_lenses: a lens with too few
    # judged themes is switched off, and one judged theme is not a lens), with the calibrated verdict
    # and its evidence (scoring.judge): the short ones lead, then the rest by gap
    from .api.gaps import available_lenses
    offered = available_lenses(s, country.id)
    gaps = []
    for lens in (k for k in LENSES if k in offered):
        for cell in s.scalars(select(CellWeek).where(CellWeek.country_id == country.id, CellWeek.week_start == week,
                                                     CellWeek.lens == lens, CellWeek.insufficient.is_(False),
                                                     CellWeek.gap.is_not(None))):
            b = cell.breakdown or {}
            gaps.append({"theme": themes[cell.theme_id].name_en if cell.theme_id in themes else "?",
                         "region": regions[cell.region_id].name_en, "lens": lens, "gap": round(cell.gap, 2),
                         "times_less_coverage_than_expected": round(2.718281828 ** cell.gap, 1),
                         "articles": scored_articles(cell), "articles_all": int(cell.coverage),
                         "expected": round(b["expected_4w"], 1) if b.get("expected_4w") is not None else None,
                         "need": round(cell.need), "flags": cell.flags,
                         "verdict": cell.verdict, "new_short": bool(b.get("new_short")),
                         "likely_times_fewer_low": b.get("ratio_lo"), "likely_times_fewer_high": b.get("ratio_hi"),
                         "chance_one_in": b.get("chance")})
    gaps.sort(key=lambda g: (g["verdict"] != "short", -g["gap"]))

    # districts: articles naming each one in the window (all themes, and gender only)
    gender_ids = {t.id for t in themes.values() if t.group == "gender"}
    rows = s.execute(select(ItemRegion.region_id, ItemTheme.theme_id, func.count(func.distinct(Item.id)))
                     .join(Item, Item.id == ItemRegion.item_id)
                     .join(ItemTheme, and_(ItemTheme.item_id == Item.id, ItemTheme.active.is_(True)))
                     .where(*counted_items(country.id), Item.kind == "article",
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

    # team activity (counts only; no names)
    since = datetime.combine(week, datetime.min.time())
    votes = Counter(v for (v,) in s.execute(select(GapVote.vote).where(GapVote.created_at >= since)))
    claims = Counter(c for (c,) in s.execute(select(GapClaim.status).where(GapClaim.updated_at >= since)))
    comments = s.scalar(select(func.count(Comment.id)).where(Comment.created_at >= since, Comment.deleted.is_(False)))
    # outlets whose route left the comparable basis lately (nightly list; the health card shows the pairs)
    departed = s.scalar(select(func.count(func.distinct(BasisDeparture.outlet_id)))
                        .where(BasisDeparture.country_id == country.id)) or 0

    return {
        "country": country.name_en, "week_starting": week.isoformat(),
        "window": f"{win_start.date().isoformat()} to {(win_end - timedelta(days=1)).date().isoformat()}",
        "coverage_by_theme": coverage, "top_gaps": gaps[:8],
        "lenses_with_data": sorted({g["lens"] for g in gaps}),
        "lenses_offered": sorted(offered),
        "districts_with_no_monitored_articles": silent, "districts_total": len(districts),
        "gender_articles_naming_a_district": gender_named,
        "flags_this_week": dict(flags),
        "team_activity_this_week": {"gap_votes": dict(votes), "claims": dict(claims), "comments": comments or 0},
        "known_limits": ["monitored coverage only (Facebook only as the sample of posts Google indexes, no Telegram)",
                         COUNTS_LIMIT if scored else UNSCORED_LIMIT,
                         LENSES_LIMIT.format(lenses=", ".join(sorted(offered)) or "none"),
                         *([VERDICT_LIMIT.format(floor=settings.MIN_SHORTFALL)] if any(g["verdict"] for g in gaps) else []),
                         "event and humanitarian need data are pending source keys" if not
                         {"events", "humanitarian"} & {g["lens"] for g in gaps} else "",
                         "most articles name no district",
                         *([SEARCH_LIMIT] if "search" in {g["lens"] for g in gaps} else []),
                         *([DEPARTURES_LIMIT.format(n=departed, s="" if departed == 1 else "s", weeks=settings.DEPARTURE_WEEKS)]
                           if departed else [])],
    }


LAST_TRY = 3  # Thursday: from then on the digest covers last week even if its reader data is still short


def digest_week(s: Session, country_id: int, today: date | None = None) -> date:
    """The week the digest covers: the one that ended last Sunday, once its scores are complete.
    Wikipedia gives us page views a day or two late, so early in the week that week's audience cells
    can still be coming in. Until Thursday the digest then falls back to the latest complete week (whose
    digest usually exists already, so nothing new is written) and the next morning's run tries again."""
    today = today or date.today()
    last = week_start(today) - timedelta(weeks=1)
    if today.weekday() >= LAST_TRY:
        return last
    return latest_complete_week(s, country_id, upto=last) or last


def generate(s: Session, country: Country, week: date | None = None, force: bool = False,
             today: date | None = None) -> Digest:
    week = week or digest_week(s, country.id, today)
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
            system=SYSTEM.format(country=country.name_en, marker=ARABIC_MARKER),
            messages=[{"role": "user", "content": "Facts for this week's brief (JSON):\n\n"
                       + json.dumps(facts, ensure_ascii=False, sort_keys=True)}],
        )
    except Exception as e:  # noqa: BLE001 - recorded, never raised into the scheduler
        d.status, d.error, d.content_md, d.content_md_ar = "error", f"{type(e).__name__}: {e}"[:1000], None, None
        s.commit()
        log.warning("digest failed: %s", d.error)
        return d
    d.usage = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
    if resp.stop_reason == "refusal":
        d.status, d.content_md, d.content_md_ar = "refused", None, None
        d.error = f"Model declined ({getattr(resp.stop_details, 'category', None)})"
    else:
        d.status, d.error = "ok", None
        d.content_md, d.content_md_ar = split_brief("\n".join(b.text for b in resp.content if b.type == "text"))
        if resp.stop_reason == "max_tokens":
            if d.content_md_ar:
                d.content_md_ar += "\n\n*(توقف الموجز عند حد الطول.)*"
            else:
                d.content_md += "\n\n*(Brief was cut off at the length limit.)*"
    s.commit()
    return d


def generate_all(s: Session, **kw) -> list[Digest]:
    return [generate(s, c, **kw) for c in s.scalars(select(Country))]
