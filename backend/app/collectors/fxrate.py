"""The dinar's exchange rates: the parallel ("black") market and the official rate.

Parallel: Al-Mashhad al-Libi (almashhadlibya.com) posts a closing figure for Tripoli's parallel market
every day ("في ختام السوق الموازي"), with the dollar in cash, the dollar by bank cheque, the euro and
more. Other outlets repost it. We read the site's own public WordPress feed for that category, a
handful of requests a day, as desert-watch (robots.txt allows it). On 15 Oct 2026 its close agreed
with two other outlets within 0.03 dinars.
Official: the Central Bank of Libya's rates page (cbl.gov.ly/currency-exchange-rates/), the average
of buy and sell. GET gives the latest day. Its own date filter (a form POST) gives history.

Parsing lives in app/fxparse.py (no network there). Each source keeps only (day, currency, value,
link): no author names, no comments. One Indicator row per key and day, replaced on each run."""
from datetime import date, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import fxparse
from ..models import Country, Indicator, utcnow
from .base import RunResult, http_client, polite_get, refused

MASHHAD_API = "https://almashhadlibya.com/wp-json/wp/v2/posts"
MASHHAD_CATEGORY = 8              # أسعار العملات
MASHHAD_SEARCH = "ختام السوق الموازي"
# the same posts, reposted with the same text by Libya Akhbar (tag اسعار الدولار), if Al-Mashhad's Cloudflare says no
MIRROR_API, MIRROR_TAG = "https://www.libyaakhbar.com/wp-json/wp/v2/posts", 98
CBL_URL = "https://cbl.gov.ly/currency-exchange-rates/"
FIELDS = "id,date,link,title,content"
# Indicator keys: (source currency code, market) -> key
KEYS = {("USD", "parallel"): "usd_lyd_parallel", ("USD_CHQ", "parallel"): "usd_lyd_parallel_cheque",
        ("EUR", "parallel"): "eur_lyd_parallel", ("USD", "official"): "usd_lyd_official", ("EUR", "official"): "eur_lyd_official"}


class Blocked(Exception):
    """A Cloudflare challenge or any answer that is not the JSON list we asked for."""


def _posts(client: httpx.Client, url: str, params: dict) -> tuple[list[dict], int]:
    r = polite_get(client, url, min_interval=3.0, params={**params, "_fields": FIELDS})
    if r.status_code == 400:   # a page past the end
        return [], 0
    if refused(r) or r.status_code in (401, 403) or "json" not in r.headers.get("content-type", ""):
        raise Blocked(f"{url} answered {r.status_code}")
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        raise Blocked(f"{url} answered {type(data).__name__}")
    return data, int(r.headers.get("X-WP-TotalPages", "1") or 1)


def recent_posts(client: httpx.Client, days: int = 3) -> tuple[list[dict], str]:
    """Every currency post of the last few days (one request), from Al-Mashhad or else its mirror."""
    after = (date.today() - timedelta(days=days)).isoformat() + "T00:00:00"
    try:
        return _posts(client, MASHHAD_API, {"categories": MASHHAD_CATEGORY, "after": after, "per_page": 50})[0], "almashhad"
    except Blocked:
        return _posts(client, MIRROR_API, {"tags": MIRROR_TAG, "after": after, "per_page": 50})[0], "libyaakhbar"


def close_history(client: httpx.Client, max_pages: int = 20) -> list[dict]:
    """All closing posts, newest first, page by page (about 13 pages of 100 since Nov 2023)."""
    posts, page, total = [], 1, 1
    while page <= min(total, max_pages):
        more, total = _posts(client, MASHHAD_API, {"categories": MASHHAD_CATEGORY, "search": MASHHAD_SEARCH,
                                                    "per_page": 100, "page": page, "orderby": "date", "order": "desc"})
        if not more:
            break
        posts += more
        page += 1
    return posts


def cbl_page(client: httpx.Client, start: date | None = None, end: date | None = None) -> str:
    """The rates table: the latest day, or every banking day in [start, end] through the page's own filter."""
    if start is None:
        r = polite_get(client, CBL_URL, min_interval=3.0)
    else:
        r = client.post(CBL_URL, data={"pub_date": f"{start.isoformat()} - {(end or date.today()).isoformat()}"}, timeout=180)
    r.raise_for_status()
    return r.text


def store(s: Session, country_id: int, rows: list[tuple], market: str, source: str, *, overwrite: bool = True) -> int:
    """Upsert (day, currency, value, url) rows as Indicator rows. Returns rows written. overwrite=False
    only fills days that have no value yet (an archive never replaces a daily source)."""
    n = 0
    for day, cur, value, url in rows:
        key = KEYS.get((cur, market))
        if not key:
            continue
        row = s.scalar(select(Indicator).where(Indicator.country_id == country_id, Indicator.key == key, Indicator.day == day))
        if row is not None and not overwrite and row.value is not None:
            continue
        if row is None:
            row = Indicator(country_id=country_id, key=key, day=day, source=source)
            s.add(row)
        row.value, row.source, row.extra, row.fetched_at = round(float(value), 4), source, {"url": url}, utcnow()
        n += 1
    s.commit()
    return n


def official_by_day(s: Session, country_id: int) -> dict:
    """{day: official USD rate}, for the parallel series' sanity check."""
    return dict(s.execute(select(Indicator.day, Indicator.value).where(
        Indicator.country_id == country_id, Indicator.key == "usd_lyd_official", Indicator.value.is_not(None))).all())


def run(s: Session, *, history: bool = False, cbl_since: date | None = None, client: httpx.Client | None = None) -> dict:
    """Official first (the parallel cleaning compares against it), then the parallel rate.
    history: every closing post since late 2023 instead of the last few days. cbl_since: the official
    history from that date, one year per request (the 3-year answer is 12 MB)."""
    c = s.scalar(select(Country).where(Country.iso2 == "LY"))
    if not c:
        return {"skipped": "no Libya"}
    own = client is None
    client = client or http_client(timeout=60)
    out = {"official": 0, "parallel": 0, "dropped": 0, "source": None, "errors": [], "warnings": []}
    try:
        try:
            if cbl_since:
                y = cbl_since
                while y <= date.today():
                    end = min(date(y.year, 12, 31), date.today())
                    out["official"] += store(s, c.id, fxparse.parse_cbl_html(cbl_page(client, y, end), CBL_URL), "official", "cbl")
                    y = date(y.year + 1, 1, 1)
            else:
                out["official"] = store(s, c.id, fxparse.parse_cbl_html(cbl_page(client), CBL_URL), "official", "cbl")
        except Exception as e:  # noqa: BLE001
            out["errors"].append(f"cbl: {e}"[:200])
        try:
            if history:
                posts, out["source"] = close_history(client), "almashhad"
                rows = fxparse.parse_almashhad_posts(posts, "close")
            else:
                posts, out["source"] = recent_posts(client)
                rows = fxparse.parse_almashhad_posts(posts, "best")
                newest = max((p for p in posts if fxparse.classify_almashhad(p["title"]["rendered"]) == "close"),
                             key=lambda p: p["date"], default=None)
                if newest and not any(r[1] == "USD" for r in fxparse.parse_almashhad_post(newest)[1]):
                    out["warnings"].append(f"newest closing post has no dollar figure we can read: {newest['link']}")
            kept, dropped = fxparse.clean_series(rows, official_by_day(s, c.id))
            out["parallel"] = store(s, c.id, kept, "parallel", out["source"])
            out["dropped"] = len(dropped)
        except Exception as e:  # noqa: BLE001
            out["errors"].append(f"parallel: {e}"[:200])
    finally:
        if own:
            client.close()
    return out


def collect(s: Session) -> RunResult:
    res = run(s)
    detail = f"official {res.get('official', 0)}, parallel {res.get('parallel', 0)} rows from {res.get('source')}" + (
        f", {res['dropped']} implausible dropped" if res.get("dropped") else "") + (
        ". " + " | ".join(res["errors"] + res["warnings"]) if res.get("errors") or res.get("warnings") else "")
    return RunResult(rows=res.get("official", 0) + res.get("parallel", 0), errors=len(res.get("errors", [])) + len(res.get("warnings", [])),
                     detail=detail[:900])


def import_archive(s: Session, path: str) -> dict:
    """Libya Observer's exchange-rate box over time, from Internet Archive snapshots (JSONL written by
    scripts/fx_archive.py: {snapshot, rates: [{market, currency, sell, updated}]}). Each box carries the
    date it was last updated, so many snapshots collapse to one value per update. Fills only days with
    no value from the daily sources."""
    import json
    from datetime import date as _date
    c = s.scalar(select(Country).where(Country.iso2 == "LY"))
    seen: dict[tuple, float] = {}
    for line in open(path, encoding="utf-8"):
        if not line.startswith("{"):
            continue
        rec = json.loads(line)
        for r in rec.get("rates") or []:
            if r.get("sell") and r.get("updated") and r["currency"] in ("USD", "EUR"):
                seen[(r["updated"], r["currency"], r["market"])] = r["sell"]
    url = "https://libyaobserver.ly/exchange-rates (Internet Archive)"
    out = {"updates": len(seen), "written": 0}
    for market in ("parallel", "official"):
        # wider than fxparse's bands: before the 2021 devaluation the official dollar was about 1.4 dinars
        rows = [(_date.fromisoformat(d), cur, v, url) for (d, cur, m), v in sorted(seen.items()) if m == market and 0.5 <= v <= 40]
        out["written"] += store(s, c.id, rows, market, "libyaobserver_archive", overwrite=False)
    return out
