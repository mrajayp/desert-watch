"""Scheduled jobs. Each opens its own session; collectors are wrapped by run_collector
so failures are recorded, not raised. Jobs share one lock so SQLite sees one writer."""
import logging
import threading

from . import dedupe, learning, network, scoring
from .collectors import COLLECTORS
from .collectors.base import run_collector
from .db import SessionLocal
from .ingest import apply_relevance_guard, infer_bases, infer_scopes
from .models import Country

log = logging.getLogger("desert_watch.jobs")
_LOCK = threading.Lock()

# Learned models only switch on above these label counts (plan: sparse-data safeguard).
THRESHOLDS = {"theme_classifier_new_labels": 50, "gap_ranker_votes": 150}


def _locked(fn):
    def wrapper(*a, **kw):
        with _LOCK:
            return fn(*a, **kw)
    wrapper.__name__ = fn.__name__
    return wrapper


def collect(key: str, **kw):
    fn, _ = COLLECTORS[key]
    with SessionLocal() as s:
        run = run_collector(s, key, lambda sess: fn(sess, **kw))
        log.info("collector %s -> %s (%s rows)", key, run.status, run.rows)
        return run.status


@_locked
def recompute(weeks: int | None = None):
    """weeks=None scores every week since the first collected article (capped at ~4 years)."""
    full = weeks is None
    with SessionLocal() as s:
        if weeks is None:
            from datetime import date
            from sqlalchemy import func, select
            from .models import Item
            first = s.scalar(select(func.min(Item.published_at)).where(Item.kind == "article"))
            weeks = min(210, max(12, ((date.today() - first.date()).days // 7) + 1)) if first else 12
        infer_scopes(s)
        infer_bases(s)
        for c in s.query(Country).all():
            apply_relevance_guard(s, c.id)
        # one story counted once: recent weeks on the hourly run, everything on the full run
        from datetime import datetime, timedelta
        since = None if full else datetime.now() - timedelta(weeks=weeks + 5)
        dups = dedupe.mark_duplicates(s, since)
        n = scoring.compute_all(s, weeks=weeks)
        from .gtrends import flag_missing_weeks
        flag_missing_weeks(s)  # search lens: no score when a week of the window lacks search data
        e = network.compute_all(s, weeks=weeks)
        lb = learning.build_labels(s)
        log.info("recompute: %s new duplicates, %s cells, %s edges, %s new labels", dups, n, e, lb)
        return n


def model_job(source_key: str, *args: str) -> dict | None:
    """Run a theme-model command (app/ml) in a child process, so the memory scikit-learn takes goes
    back to the system when it ends. Skipped quietly while no model is live. Logged in source_run."""
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path
    from .ml.registry import active
    from .models import SourceRun, utcnow
    with SessionLocal() as s:
        if active(s) is None:
            return None
        run = SourceRun(source_key=source_key, started_at=utcnow(), status="running")
        s.add(run)
        s.commit()
        out = {}
        try:
            # one BLAS thread and one fitting thread: the job shares a 512 MB machine with the web process
            env = {**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
                   "DW_NJOBS": "1"}
            p = subprocess.run([sys.executable, "-m", "app.cli", *args], cwd=Path(__file__).resolve().parents[1],
                               capture_output=True, text=True, encoding="utf-8", timeout=3600, env=env)
            try:
                out = json.loads((p.stdout.strip().splitlines() or ["{}"])[-1])
            except ValueError:
                out = {}
            run.status = "ok" if p.returncode == 0 else "error"
            run.rows = int(out.get("changed") or 0)
            run.error = (p.stderr or p.stdout)[-1500:] if p.returncode else None  # the outcome is in the registry note
        except subprocess.TimeoutExpired:
            run.status, run.error = "error", "timed out after an hour"
        except Exception as e:  # never leave the run at "running"
            run.status, run.error = "error", repr(e)[:1500]
        run.ok = run.status == "ok"
        run.finished_at = utcnow()
        s.commit()
        log.info("%s %s -> %s (%s changes)", source_key, " ".join(args), run.status, run.rows)
        return out


@_locked
def nightly():
    with SessionLocal() as s:
        learning.purge_old_events(s)
    for key in ("wikipedia", "acled", "ucdp", "reliefweb"):
        collect(key)
    collect("gnews_social")   # yesterday and the day before, one fixed day each (Google indexes late)
    _resolve_links()
    # retrain the label-trained part of the theme model; a promoted version re-scores everything
    res = model_job("theme_model_train", "train-small-model")
    if res and res.get("promoted"):
        model_job("theme_model", "classify-items", "--all")


# ---------------------------------------------------------------- engagement (see engagement.py)
def _resolve_links(days: int = 14, limit: int = 400):
    from . import resolve
    with SessionLocal() as s:
        return run_collector(s, "resolve", lambda sess: resolve.collect(sess, days=days, limit=limit)).status


@_locked
def resolve_links(days: int = 14, limit: int = 400):
    return _resolve_links(days, limit)


@_locked
def reach_snapshot(limit: int | None = None):
    from . import reach
    with SessionLocal() as s:
        return run_collector(s, "reach", lambda sess: reach.collect(sess, limit=limit)).status


CATCH_UP = 5000  # older articles the live model has not scored, picked up per hourly run (newest first)
CLASSIFY_HOURLY = ("classify-items", "--days", "3", "--catch-up", str(CATCH_UP))


def classify_due() -> bool:
    """Whether the hourly scoring has work: a counted article created since the last successful scoring
    run, or one the live version never scored (it became relevant later). Plain SQL in this process,
    so a quiet hour starts no scikit-learn child."""
    from sqlalchemy import func, select
    from .ml.registry import active, unscored
    from .models import Item, SourceRun
    with SessionLocal() as s:
        live = active(s)
        if live is None:
            return False
        last = s.scalar(select(func.max(SourceRun.started_at)).where(SourceRun.source_key == "theme_model",
                                                                      SourceRun.status == "ok"))
        counted = (Item.kind == "article", Item.relevant.is_(True), Item.duplicate_of.is_(None))
        if last is None or s.scalar(select(Item.id).where(*counted, Item.created_at >= last).limit(1)) is not None:
            return True
        return s.scalar(select(Item.id).where(*counted, unscored(live.version)).limit(1)) is not None


@_locked
def hourly():
    collect("rss")
    collect("youtube")
    collect("galerts")
    if classify_due():  # before the recompute at :45
        model_job("theme_model", *CLASSIFY_HOURLY)
    else:
        log.info("theme_model: nothing new to score this hour")


@_locked
def six_hourly():
    collect("official")
    collect("gnews")
    collect("gdelt")
    collect("fb_url")   # Facebook readings at ~48 h and ~7 days (awaiting key until the Meta app exists)
    collect("wikireading")   # Wikimedia publishes each day's file around 02:30-03:00 UTC the next day


@_locked
def backfill(weeks: int = 12):
    collect("gnews", weeks=weeks)
    collect("wikipedia", days=7 * (weeks + 16))
    collect("gdelt_timeline")
    collect("rss")


@_locked
def weekly_digest(force: bool = False):
    from . import digest
    from .collectors.base import AwaitingKey  # noqa: F401
    from .models import SourceRun, utcnow
    with SessionLocal() as s:
        run = SourceRun(source_key="digest", started_at=utcnow(), status="running")
        s.add(run)
        s.commit()
        if not digest.has_credentials():
            run.status, run.error = "awaiting_key", "Set the ANTHROPIC_API_KEY secret to enable the weekly digest."
        else:
            ds = digest.generate_all(s, force=force)
            bad = [d for d in ds if d.status != "ok"]
            run.status = "ok" if not bad else "error"
            run.rows = len(ds) - len(bad)
            run.error = "; ".join(d.error or d.status for d in bad)[:1000] or None
        run.finished_at = utcnow()
        s.commit()
        return run.status


JOBS = {
    "rss": lambda: _locked(collect)("rss"),
    "youtube": lambda: _locked(collect)("youtube"),
    "galerts": lambda: _locked(collect)("galerts"),
    "gnews": lambda: _locked(collect)("gnews"),
    "gnews_social": lambda: _locked(collect)("gnews_social"),
    "official": lambda: _locked(collect)("official"),
    "gdelt": lambda: _locked(collect)("gdelt"),
    "gdelt_timeline": lambda: _locked(collect)("gdelt_timeline"),
    "wikipedia": lambda: _locked(collect)("wikipedia"),
    "recompute": recompute,
    "digest": lambda: weekly_digest(force=True),
    "backfill": backfill,
    "resolve_links": resolve_links,
    "fb_url": lambda: _locked(collect)("fb_url"),
    "reach": reach_snapshot,
    "classify": lambda: _locked(model_job)("theme_model", *CLASSIFY_HOURLY),
    "classify_all": lambda: _locked(model_job)("theme_model", "classify-items", "--all"),
}


def start_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler
    sched = BackgroundScheduler(timezone="UTC", job_defaults={"coalesce": True, "max_instances": 1})
    sched.add_job(hourly, "cron", minute=7)
    sched.add_job(six_hourly, "cron", hour="*/6", minute=17)
    sched.add_job(nightly, "cron", hour=2, minute=5)
    sched.add_job(recompute, "cron", minute=45, kwargs={"weeks": 12})   # recent weeks hourly
    sched.add_job(recompute, "cron", hour=3, minute=30)                   # full history nightly
    # the digest waits for Sunday's page views (a day or two late): later runs write it once they are in
    sched.add_job(weekly_digest, "cron", day_of_week="tue-thu", hour=6, minute=0)
    sched.add_job(weekly_digest, "cron", day_of_week="mon", hour=6, minute=0)  # after Sunday's data
    sched.add_job(reach_snapshot, "cron", day=1, hour=4, minute=40)            # outlet web rank, monthly
    sched.start()
    return sched
