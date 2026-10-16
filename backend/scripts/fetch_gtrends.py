"""Fetch Google Trends search interest for Libya on a local machine, for `python -m app.cli import-search`.

Never run this from the Fly server. It calls the unofficial trends.google.com widget endpoints
(homepage cookie -> /trends/api/explore -> /trends/api/widgetdata/multiline), which Google tags as
scraper traffic. It is polite on purpose: at least 10 s between requests, one 60 s back-off on a
429, and a full stop at the second 429. Run it about once a week.

    cd backend
    .venv/Scripts/python.exe scripts/fetch_gtrends.py ../data/imports/gtrends.jsonl            # 5 years weekly + 269 days daily
    .venv/Scripts/python.exe scripts/fetch_gtrends.py out.jsonl --no-weekly --daily 120         # the weekly refresh
    .venv/Scripts/python.exe scripts/fetch_gtrends.py out.jsonl --basket services=الكهرباء+المياه --anchor مطعم --no-daily

Word lists, anchor and request groups come from `gtrends` in config/countries/<country>.yaml;
--basket/--anchor override them for trying out new lists. Rows are appended to the output
(JSONL, one row per list per Monday week, see app/gtrends.py). The output stays out of git.
Request budget: --max-requests (default 40) counts every request, the homepage included."""
import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import settings  # noqa: E402
from app.gtrends import (DAILY_MAX_DAYS, MAX_SLOTS, build_rows, check_baskets, config, groups,  # noqa: E402
                         parse_points, slot)

HOME = "https://trends.google.com/trends/"
API = "https://trends.google.com/trends/api"
MIN_GAP = 10.0
BACKOFF = 60


class Stop(Exception):
    pass


class Client:
    def __init__(self, *, gap: float = MIN_GAP, max_requests: int = 40, raw_dir: Path | None = None,
                 hl: str = "en-US", tz: str = "-120", transport=None, sleep=time.sleep):
        self.gap, self.max, self.raw_dir, self.hl, self.tz = max(gap, MIN_GAP), max_requests, raw_dir, hl, tz
        self.sleep, self.n, self.n429, self.last = sleep, 0, 0, 0.0
        self.http = httpx.Client(headers={"User-Agent": settings.USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
                                 timeout=30, follow_redirects=True, transport=transport)

    def get(self, name: str, url: str, params: dict | None = None) -> str:
        while True:
            if self.n >= self.max:
                raise Stop(f"request budget used up ({self.max})")
            wait = self.last + self.gap - time.monotonic()
            if self.last and wait > 0:
                self.sleep(wait)
            self.n += 1
            r = self.http.get(url, params=params)
            self.last = time.monotonic()
            print(f"[{self.n:02d}] {name}: HTTP {r.status_code} {len(r.content)}B", flush=True)
            if self.raw_dir:
                self.raw_dir.mkdir(parents=True, exist_ok=True)
                (self.raw_dir / f"{self.n:02d}_{name}.txt").write_text(f"{r.request.url}\nHTTP {r.status_code}\n\n{r.text}",
                                                                       encoding="utf-8")
            if r.status_code == 429:
                self.n429 += 1
                if self.n429 >= 2:
                    raise Stop("second 429: stopping")
                print(f"   429: waiting {BACKOFF} s", flush=True)
                self.sleep(BACKOFF)
                continue
            if r.status_code != 200:
                raise Stop(f"{name}: HTTP {r.status_code}")
            return r.text

    @staticmethod
    def body(text: str) -> dict:
        return json.loads(text[text.index("{"):])  # strips Google's )]}' prefix

    def home(self, geo: str):
        self.get("home", HOME, {"geo": geo, "hl": self.hl})

    def timeseries(self, name: str, items: list[str], time_: str, geo: str) -> tuple[str, list[dict]]:
        req = {"comparisonItem": [{"keyword": k, "geo": geo, "time": time_} for k in items], "category": 0, "property": ""}
        ex = self.body(self.get(f"explore_{name}", f"{API}/explore",
                                {"hl": self.hl, "tz": self.tz, "req": json.dumps(req, ensure_ascii=False)}))
        w = next(w for w in ex["widgets"] if w["id"] == "TIMESERIES")
        data = self.body(self.get(f"multiline_{name}", f"{API}/widgetdata/multiline",
                                  {"hl": self.hl, "tz": self.tz, "req": json.dumps(w["request"], ensure_ascii=False),
                                   "token": w["token"]}))
        return w["request"].get("resolution", ""), data["default"]["timelineData"]


def plan(g: dict, *, weekly: bool, daily: int | None, today: date) -> list[dict]:
    jobs = []
    windows = []
    if weekly:
        windows.append(("week", "today 5-y"))
    if daily:
        days = min(daily, DAILY_MAX_DAYS)
        windows.append(("day", f"{(today - timedelta(days=days - 1)).isoformat()} {today.isoformat()}"))
    for res, time_ in windows:
        for grp in groups(g):
            jobs.append({"resolution": res, "time": time_,
                         "slots": [(sl, g["baskets"][sl]) for sl in grp[:MAX_SLOTS - 1]]})
    return jobs


def summarize(rows: list[dict]):
    by = {}
    for r in rows:
        by.setdefault((r["request_id"], r["theme_slug"]), []).append(r)
    for (rid, slug), rs in by.items():
        n = len(rs)
        nod = sum(not r["has_data"] for r in rs)
        mean = sum(r["value_raw"] for r in rs) / n
        anc = [r["anchor_raw"] for r in rs]
        am = sum(anc) / n
        cv = (sum((x - am) ** 2 for x in anc) / n) ** 0.5 / am if am else float("nan")
        ratio = sum(r["value_raw"] for r in rs) / sum(anc) if sum(anc) else float("nan")
        print(f"   {rid} {slug}: {n} weeks, no data {nod} ({nod / n:.0%}), mean {mean:.1f}, anchor mean {am:.1f} "
              f"(CV {cv:.2f}, min {min(anc)}), list/anchor {ratio:.2f}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path)
    ap.add_argument("--config", type=Path, default=settings.CONFIG_DIR / "countries" / "libya.yaml")
    ap.add_argument("--no-weekly", action="store_true", help="skip the 5-year weekly series")
    ap.add_argument("--daily", type=int, default=DAILY_MAX_DAYS, help="recent daily window in days (<= 269)")
    ap.add_argument("--no-daily", action="store_true")
    ap.add_argument("--only", help="comma-separated theme slugs")
    ap.add_argument("--basket", action="append", default=[], help="slug=term1+term2 (replaces the config lists)")
    ap.add_argument("--anchor")
    ap.add_argument("--max-requests", type=int, default=40)
    ap.add_argument("--gap", type=float, default=MIN_GAP)
    ap.add_argument("--raw-dir", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = yaml.safe_load(a.config.read_text(encoding="utf-8"))
    g = dict(config(cfg) or {"geo": cfg.get("iso2", "LY"), "baskets": {}})
    if a.basket:
        g["baskets"] = {k: [t.strip() for t in v.split("+")] for k, v in (b.split("=", 1) for b in a.basket)}
        g["groups"] = [list(g["baskets"])[i:i + MAX_SLOTS - 1] for i in range(0, len(g["baskets"]), MAX_SLOTS - 1)]
    else:
        themes = yaml.safe_load((a.config.parent.parent / "themes.yaml").read_text(encoding="utf-8"))["themes"]
        problems = check_baskets(g, {t["slug"]: t.get("ar_terms", []) for t in themes})
        if problems:
            sys.exit("config problems:\n  " + "\n  ".join(problems))
    if a.anchor:
        g["anchor"] = a.anchor
    if a.only:
        keep = set(a.only.split(","))
        g["baskets"] = {k: v for k, v in g["baskets"].items() if k in keep}
    if not g.get("anchor") or not g["baskets"]:
        sys.exit("no anchor or no word lists")
    geo = g.get("geo", "LY")
    today = datetime.now(timezone.utc).date()
    jobs = plan(g, weekly=not a.no_weekly, daily=None if a.no_daily else a.daily, today=today)
    need = 1 + 2 * len(jobs)
    print(f"{len(jobs)} requests of up to {MAX_SLOTS} items ({need} HTTP calls, budget {a.max_requests}), anchor {g['anchor']}")
    for j in jobs:
        print(f"   {j['resolution']} {j['time']}: {' | '.join(slot(t) for _, t in j['slots'])} | {g['anchor']}")
    if a.dry_run:
        return 0
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    c = Client(gap=a.gap, max_requests=a.max_requests, raw_dir=a.raw_dir)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        c.home(geo)
        for k, j in enumerate(jobs, 1):
            items = [slot(t) for _, t in j["slots"]] + [g["anchor"]]
            res, timeline = c.timeseries(f"{j['resolution']}{k}", items, j["time"], geo)
            if res.lower() != j["resolution"]:
                print(f"   expected {j['resolution']} data, got {res}: skipped")
                continue
            rows = build_rows(parse_points(timeline), j["slots"], g["anchor"], resolution=j["resolution"],
                              request_id=f"{stamp}-{k:02d}", fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                              geo=geo)
            with a.out.open("a", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            total += len(rows)
            summarize(rows)
    except Stop as e:
        print(f"stopped: {e}")
    print(f"{total} rows -> {a.out} ({c.n} requests, {c.n429} x 429)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
