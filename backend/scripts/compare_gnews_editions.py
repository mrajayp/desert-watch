"""Compare Google News editions for the Arabic theme searches (plan C-R2.4). Run from a PC, never
from the server.

Google News has no Libya edition, so the collector asks the Egypt-Arabic edition (config gnews.editions).
This script asks the same theme-and-week searches of several Arabic editions and of hl=ar&gl=LY, and
counts what each returns: items, how many come from outlets the register labels Libyan (the local
database, opened read-only), how many from outlets the register has no scope for, and how much of it
the Egypt edition already returned (overlap by headline). It writes a Markdown report; the owner
decides from the numbers whether a second edition is worth doubling the Arabic requests.

    cd backend
    .venv/Scripts/python.exe scripts/compare_gnews_editions.py --db ../data/desert_watch.db \
        --out ../docs/research/gnews_editions_2026-10-19.md

Budget: --max-requests (default 60) at --interval seconds (default 2) with the desert-watch user agent,
one request at a time, nothing retried; two refusals (429/5xx) in a row end the run. The plan fits the
budget: the Egypt edition and the LY request on all four weeks (12 each), the other six editions on the
first two weeks (6 each), 3 themes x 4 fixed past weeks. The weeks are old enough for Google's index to
have settled (more than 3 weeks)."""
import argparse
import json
import re
import sqlite3
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import feedparser
import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import settings  # noqa: E402
from app.collectors.gnews import ENDPOINT, build_query  # noqa: E402
from app.ingest import domain_of  # noqa: E402

THEMES = ("security", "economy", "migration")
WEEKS = (date(2026, 9, 7), date(2026, 9, 14), date(2026, 9, 21), date(2026, 9, 28))   # Mondays, 7-day windows
# (name, hl, gl, ceid). EG is what the collector uses; LY is the request Google answers with a redirect.
EDITIONS = (("EG:ar", "ar", "EG", "EG:ar"), ("LY:ar", "ar", "LY", "LY:ar"), ("SA:ar", "ar", "SA", "SA:ar"),
            ("AE:ar", "ar", "AE", "AE:ar"), ("LB:ar", "ar", "LB", "LB:ar"), ("MA:ar", "ar", "MA", "MA:ar"),
            ("TN:ar", "ar", "TN", "TN:ar"), ("DZ:ar", "ar", "DZ", "DZ:ar"))
FULL = {"EG:ar", "LY:ar"}       # all four weeks; the others get the first two
REFUSALS_STOP = 2


def register(db: Path) -> tuple[dict[str, str], dict[str, str]]:
    """domain -> active scope, and domain -> outlet name, from a database opened read-only."""
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        scope = dict(con.execute("""select o.domain, c.value from outlet o join outlet_category c on c.outlet_id = o.id
                                    where c.dimension = 'scope' and c.status = 'active' and c.valid_to is null"""))
        names = dict(con.execute("select domain, name from outlet"))
    finally:
        con.close()
    return scope, names


def theme_terms() -> dict[str, list[str]]:
    data = yaml.safe_load((settings.CONFIG_DIR / "themes.yaml").read_text(encoding="utf-8"))
    return {t["slug"]: t.get("ar_terms", []) for t in data["themes"] if t["slug"] in THEMES}


def country_term() -> str:
    cfg = yaml.safe_load((settings.CONFIG_DIR / "countries" / "libya.yaml").read_text(encoding="utf-8"))
    return cfg["gnews"]["country_term_ar"]


def headline(e, name: str | None) -> str:
    t = e.get("title", "")
    if name and t.endswith(" - " + name):
        t = t[: -len(name) - 3]
    return re.sub(r"\s+", " ", t).strip().lower()


def plan() -> list[tuple[str, str, date]]:
    out = []
    for name, *_ in EDITIONS:
        for theme in THEMES:
            for wk in (WEEKS if name in FULL else WEEKS[:2]):
                out.append((name, theme, wk))
    return out


def scope_of(domain: str | None, scope: dict[str, str]) -> str:
    if not domain:
        return "unknown"
    if domain in scope:
        return scope[domain]
    parts = domain.split(".")
    if len(parts) > 2 and ".".join(parts[-2:]) in scope:
        return scope[".".join(parts[-2:])]
    return "unlabelled"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=str(settings.DATA_DIR / "desert_watch.db"))
    ap.add_argument("--out", default=str(settings.REPO_ROOT / "docs" / "research" / f"gnews_editions_{date.today().isoformat()}.md"))
    ap.add_argument("--max-requests", type=int, default=60)
    ap.add_argument("--interval", type=float, default=2.0)
    a = ap.parse_args(argv)
    scope, names = register(Path(a.db))
    terms = theme_terms()
    cterm = country_term()
    eds = {name: (hl, gl, ceid) for name, hl, gl, ceid in EDITIONS}
    results: dict[tuple, dict] = {}
    refusals = made = 0
    started = datetime.now(timezone.utc)
    with httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": settings.USER_AGENT}) as client:
        for name, theme, wk in plan():
            if made >= a.max_requests or refusals >= REFUSALS_STOP:
                break
            hl, gl, ceid = eds[name]
            chunk = terms[theme][:7]
            q = build_query(cterm, chunk, wk, wk + timedelta(days=7))
            if made:
                time.sleep(a.interval)
            made += 1
            try:
                r = client.get(ENDPOINT, params={"q": q, "hl": hl, "gl": gl, "ceid": ceid})
            except httpx.HTTPError as e:
                results[(name, theme, wk)] = {"error": type(e).__name__, "items": 0, "entries": []}
                print(f"{name} {theme} {wk}: {type(e).__name__}", flush=True)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                refusals += 1
                results[(name, theme, wk)] = {"error": f"HTTP {r.status_code}", "items": 0, "entries": []}
                print(f"{name} {theme} {wk}: HTTP {r.status_code}", flush=True)
                continue
            refusals = 0
            entries = feedparser.parse(r.content).entries if r.status_code == 200 else []
            rows = []
            for e in entries:
                src = e.get("source") or {}
                src_url = src.get("href") or src.get("url")
                dom = domain_of(src_url) if src_url else None
                rows.append({"title": headline(e, src.get("title")), "domain": dom, "scope": scope_of(dom, scope)})
            results[(name, theme, wk)] = {"status": r.status_code, "final_url": str(r.url), "items": len(rows), "entries": rows,
                                          "query": q}
            print(f"{name} {theme} {wk}: {len(rows)} items, final ceid {dict(r.url.params).get('ceid')}", flush=True)
    report = render(results, names, started, made, a)
    Path(a.out).write_text(report, encoding="utf-8", newline="\n")
    print(f"wrote {a.out}")
    return 0


def render(results: dict, names: dict, started: datetime, made: int, a) -> str:
    eg = {(t, w): r for (n, t, w), r in results.items() if n == "EG:ar"}
    lines = [f"# Google News editions for the Arabic searches ({started.date().isoformat()})", "",
             f"Run from a PC on {started.strftime('%Y-%m-%d %H:%M')} UTC against a read-only copy of the register "
             f"(`{Path(a.db).name}`): {made} requests at {a.interval:.0f} s spacing, {len(THEMES)} themes "
             f"({', '.join(THEMES)}), the weeks of {', '.join(w.isoformat() for w in WEEKS)}. The Egypt edition (what the "
             f"collector asks) and the LY request were asked for all four weeks, the other editions for the first two, so "
             f"every comparison below is paired: an edition is set against the Egypt edition on the same theme and week.",
             "", "Libyan share: items whose source outlet the register labels Libyan. Unlabelled: the register has no "
             "scope for the outlet. Overlap: the share of an edition's headlines the Egypt edition returned too for the "
             "same theme and week. New: headlines the Egypt edition did not return.", ""]
    # the LY request: where did it land
    ly = [r for (n, _t, _w), r in results.items() if n == "LY:ar" and r.get("final_url")]
    if ly:
        ceids = Counter(dict(httpx.URL(r["final_url"]).params).get("ceid") for r in ly)
        lines += [f"The hl=ar&gl=LY request ended at ceid {', '.join(f'{k} ({v})' for k, v in ceids.items())} "
                  f"after redirects: Google has no Libya edition and answers with another one.", ""]
    lines += ["## Per edition (paired with the Egypt edition on the same theme and week)", "",
              "| edition | requests | items | items per query | Libyan share | international | unlabelled | overlap with EG | new vs EG |",
              "|---|---|---|---|---|---|---|---|---|"]
    per_edition = {}
    for name, *_ in EDITIONS:
        rs = [((t, w), r) for (n, t, w), r in results.items() if n == name]
        if not rs:
            continue
        items = sum(r["items"] for _, r in rs)
        sc = Counter(e["scope"] for _, r in rs for e in r["entries"])
        overlap = new = both = 0
        for (t, w), r in rs:
            base = {e["title"] for e in eg.get((t, w), {}).get("entries", [])}
            mine = {e["title"] for e in r["entries"]}
            if not base or name == "EG:ar":
                continue
            both += len(mine)
            overlap += len(mine & base)
            new += len(mine - base)
        pct = lambda k: f"{100 * sc[k] / items:.0f}%" if items else "-"  # noqa: E731
        ov = f"{100 * overlap / both:.0f}%" if both else "-"
        nw = str(new) if both else "-"
        per_edition[name] = {"items": items, "libyan": sc["libyan"], "new": new, "both": both}
        lines.append(f"| {name} | {len(rs)} | {items} | {items / len(rs):.0f} | {pct('libyan')} | {pct('international')} | "
                     f"{pct('unlabelled')} | {ov} | {nw} |")
    lines += ["", "## Per theme and week", "", "| edition | theme | week | items | Libyan | unlabelled | overlap with EG |",
              "|---|---|---|---|---|---|---|"]
    for (n, t, w), r in results.items():
        if r.get("error"):
            lines.append(f"| {n} | {t} | {w.isoformat()} | {r['error']} | | | |")
            continue
        sc = Counter(e["scope"] for e in r["entries"])
        base = {e["title"] for e in eg.get((t, w), {}).get("entries", [])}
        mine = {e["title"] for e in r["entries"]}
        ov = f"{100 * len(mine & base) / len(mine):.0f}%" if mine and base and n != "EG:ar" else "-"
        lines.append(f"| {n} | {t} | {w.isoformat()} | {r['items']} | {sc['libyan']} | {sc['unlabelled']} | {ov} |")
    # the outlets an edition adds that the Egypt edition never returned (Libyan ones first)
    lines += ["", "## Outlets an edition returned that the Egypt edition did not (same theme and week)", ""]
    eg_domains = {e["domain"] for r in eg.values() for e in r.get("entries", [])}
    for name, *_ in EDITIONS:
        if name == "EG:ar":
            continue
        extra = Counter()
        for (n, t, w), r in results.items():
            if n != name:
                continue
            for e in r["entries"]:
                if e["domain"] and e["domain"] not in eg_domains:
                    extra[(e["domain"], e["scope"])] += 1
        if extra:
            top = ", ".join(f"{d} ({s}, {k})" for (d, s), k in extra.most_common(10))
            lines.append(f"- {name}: {top}")
        else:
            lines.append(f"- {name}: none")
    lines += ["", "## Reading the numbers", "",
              "- A second Arabic edition pays off only when it adds Libyan-outlet items the Egypt edition misses "
              "(the `new vs EG` column, read with the Libyan share), not when it returns the same headlines again.",
              "- Items from unlabelled outlets are not evidence either way until the register programme labels them "
              "(`python -m app.cli label-scopes`).",
              "- Adding an edition doubles the Arabic requests of every six-hourly run and of the Sunday re-query; the "
              "collector then stores each story once (ingest.store_article, by URL key).",
              "", "## What changed in the code", "",
              "- `gnews.editions` in config/countries/libya.yaml is now a list (one Arabic entry, EG:ar, and one "
              "English, GB:en); the theme searches run every entry of a language. Nothing changes until the owner adds "
              "an edition here.",
              "- The social-post search reads its editions from `gnews.social_editions` instead of a constant in "
              "collectors/gnews_social.py.",
              "", "## Decision", "", "Owner to decide from the table above (plan Q33). No edition was added.", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
