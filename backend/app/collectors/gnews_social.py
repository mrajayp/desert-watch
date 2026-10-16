"""Google News RSS restricted to one public social account (`site:facebook.com/<page>`): the posts
Google has indexed, without a key. Google keeps a sample that favours recent posts and changes with
the window size, so we ask for ONE fixed 1-day window per account and day, a day or two late (Google
indexes late), and never use it to fill in history. Trend comparisons leave each account out until
it has been collected across the whole span (the stable source+outlet rule in scoring.py).

Accounts: Facebook pages and X, Instagram and TikTok accounts that are on the 2023-24 Facebook register
as media/official pages or carry a type/scope label. Personal accounts that Google Alerts happened
to pick up have neither and are never queried. Numeric page ids and groups are skipped (site: cannot
match an id, and groups are people). YouTube channels have their own feed (rss.py). No Telegram.

Attribution: the query names the account, so every result is filed on that account's outlet."""
import calendar
import re
from collections import Counter
from datetime import date, datetime, timedelta

import feedparser
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ingest import SOCIAL, labelled_outlets, load_rules, register_kind, store_article
from ..models import Outlet
from ..textnorm import detect_lang
from .base import RunResult, http_client, polite_get
from .gnews import ENDPOINT

PLATFORMS = ("facebook.com/", "x.com/", "instagram.com/", "tiktok.com/@")
# Google News has no Libya edition: gl=LY / ceid=LY:ar answers 302 to the Egypt-Arabic edition
# (checked 2026-10-16), so we ask for that edition by name.
EDITION = {"hl": "ar", "gl": "EG", "ceid": "EG:ar"}
# At most 100 results per query. A page with 100 in one day is cut short by Google, and nothing
# smaller than a day can be asked for (libyaakhbar hits it most days).
CAP = 100
MIN_INTERVAL = 2.0     # seconds between requests
STOP_AFTER = 3         # consecutive 429/5xx answers end the run
DAYS_BACK = (1, 2)     # yesterday and the day before
MAX_QUERIES = 400

_SUFFIX = re.compile(r"\s*[-|•/]\s*(Facebook|X|Twitter|Instagram|TikTok)\s*$", re.I)
_SEP = re.compile(r"\.\s\.(?:\s|$)")          # "<page name>. . <post text>"
_ON = re.compile(r"^.{1,80}? on (X|Twitter|Instagram|TikTok):\s*", re.I)
_PROFILE = re.compile(r"Instagram photos and videos|\(@[\w.]+\)\s*$", re.I)


def _bare(t: str) -> str:
    return t.strip().rstrip(".…").strip()


def post_text(title: str, names: set[str] | None = None) -> str | None:
    """Google's title for a post is "<page name>. . <post text> - Facebook", "<post text> - Facebook"
    or "<name> on X: <text>". Returns the post text, or None when only the page name (often cut
    short) is left. `names` gathers page names seen so far, to spot a bare page name later."""
    names = names if names is not None else set()
    t = _SUFFIX.sub("", (title or "").strip()).strip()
    parts = _SEP.split(t, 1)
    if len(parts) == 2:
        names.add(_bare(parts[0]))
        t = parts[1]
    elif any(n.startswith(_bare(t)) or _bare(t) == n for n in names if n):
        return None
    t = _ON.sub("", t).strip().strip('"“”').strip()
    if _PROFILE.search(t):
        return None
    return t if len(t) >= 25 and t.count(" ") >= 3 else None


def accounts(s: Session) -> list[Outlet]:
    labelled = labelled_outlets(s)
    out = []
    for o in s.scalars(select(Outlet).where(Outlet.active.is_(True))):
        if not o.domain.lower().startswith(PLATFORMS):
            continue
        handle = o.domain.split("/", 1)[1]
        if handle.isdigit() or "/" in handle:   # numeric ids, groups/<name>
            continue
        if o.id in labelled or register_kind(o):
            out.append(o)
    # busiest register pages first, so a run that stops early drops the quiet ones
    out.sort(key=lambda o: (-((((o.external or {}).get("social_media_scrape") or {}).get("posts")) or 0), o.id))
    return out


def window_query(account: str, day: date) -> str:
    return f"site:{account} after:{day.isoformat()} before:{(day + timedelta(days=1)).isoformat()}"


def collect(s: Session, *, days: int | None = None, today: date | None = None,
            max_queries: int = MAX_QUERIES) -> RunResult:
    """One 1-day window per account for each of the last `days` days (default: yesterday and the
    day before). Results already stored by another route are only moved off a whole-platform outlet."""
    res = RunResult()
    today = today or date.today()
    windows = [today - timedelta(days=d) for d in (range(1, days + 1) if days else DAYS_BACK)]
    stats = Counter()
    failures = 0
    rules_by_country: dict = {}
    platform_ids = set(s.scalars(select(Outlet.id).where(Outlet.domain.in_(list(SOCIAL)))))
    with http_client() as client:
        for o in accounts(s):
            if failures >= STOP_AFTER or stats["queries"] >= max_queries:
                break
            rules = rules_by_country.setdefault(o.country_id, load_rules(s, o.country_id))
            names = set((o.external or {}).get("page_names") or [])
            known = set(names)
            stats["accounts"] += 1
            for day in windows:
                if failures >= STOP_AFTER or stats["queries"] >= max_queries:
                    break
                try:
                    r = polite_get(client, ENDPOINT, params={"q": window_query(o.domain, day), **EDITION},
                                   min_interval=MIN_INTERVAL, retries=0)
                except Exception as e:  # noqa: BLE001
                    res.errors += 1
                    failures += 1
                    res.detail += f"{o.domain}: {e}; "
                    continue
                stats["queries"] += 1
                if r.status_code == 429 or r.status_code >= 500:
                    res.errors += 1
                    failures += 1
                    continue
                failures = 0
                if r.status_code != 200:
                    res.errors += 1
                    res.detail += f"{o.domain}: HTTP {r.status_code}; "
                    continue
                entries = feedparser.parse(r.content).entries
                stats["results"] += len(entries)
                stats["capped"] += len(entries) >= CAP
                # a title repeated within one answer is the page's own name, not a post
                seen = Counter(_bare(_SUFFIX.sub("", e.get("title", ""))) for e in entries)
                names |= {t for t, n in seen.items() if n > 1 and not _SEP.search(t)}
                for e in sorted(entries, key=lambda e: not _SEP.search(e.get("title", ""))):  # learn names first
                    when = e.get("published_parsed")
                    text = post_text(e.get("title", ""), names)
                    if not when or not text or not e.get("link"):
                        stats["no_text"] += 1
                        continue
                    item, created = store_article(
                        s, o.country_id, rules, url=e.link, title=text,
                        published_at=datetime.utcfromtimestamp(calendar.timegm(when)), source_key="gnews_social",
                        lang=detect_lang(text), outlet_domain=o.domain, outlet_name=o.name, require_theme=True,
                        outlet_cache={o.domain: o}, extra={"window": day.isoformat()})
                    res.rows += created
                    if item is None:
                        stats["no_theme"] += 1
                    elif not created and item.outlet_id in platform_ids:
                        item.outlet_id = o.id   # Google News filed it under the whole platform
                        stats["refiled"] += 1
            if names != known:
                o.external = {**(o.external or {}), "page_names": sorted(names)[:8]}
            s.commit()
    if failures >= STOP_AFTER:
        res.detail += f"stopped after {STOP_AFTER} refusals in a row; "
    if stats["queries"] >= max_queries:
        res.detail += f"stopped at {max_queries} queries; "
    res.detail = (res.detail + str(dict(stats)))[:1000]
    return res
