"""Scheduled jobs. Each opens its own session; collectors are wrapped by run_collector
so failures are recorded, not raised. Jobs share one lock so SQLite sees one writer: the job lock
(joblock.py) covers this process's threads, the CLI commands in other processes and the children the
scheduler starts, so a deploy's data steps and the scheduler's jobs take turns."""
import logging

from . import dedupe, joblock, learning, network, scoring
from .collectors import COLLECTORS
from .collectors.base import run_collector
from .db import SessionLocal
from .ingest import apply_relevance_guard, infer_bases, infer_scopes
from .models import Country

log = logging.getLogger("desert_watch.jobs")
STATE = {"scheduler": None}   # the running BackgroundScheduler, for the health endpoints

# Learned models only switch on above these label counts (plan: sparse-data safeguard).
THRESHOLDS = {"theme_classifier_new_labels": 50, "gap_ranker_votes": 150}


def _locked(fn):
    def wrapper(*a, **kw):
        with joblock.held(note=lambda m: log.info("%s: %s", fn.__name__, m), job=fn.__name__):
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


def child_job(source_key: str, *args: str, timeout: int = 3600) -> dict:
    """Run a CLI command in a child process, so the memory it takes (scikit-learn for the theme model,
    the recompute's rows) goes back to the system when it ends. Logged in source_run under source_key;
    the child's last stdout line is read as JSON and its "changed" count stored as rows. A child
    started under the job lock inherits it (HELD_ENV) instead of waiting for its parent."""
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path
    from .models import SourceRun, utcnow
    with SessionLocal() as s:
        run = SourceRun(source_key=source_key, started_at=utcnow(), status="running")
        s.add(run)
        s.commit()
        out = {}
        try:
            # one BLAS thread and one fitting thread: the job shares a 512 MB machine with the web process
            env = {**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
                   "DW_NJOBS": "1"}
            if joblock.is_held():  # the child's command must not wait for the lock its parent holds
                env[joblock.HELD_ENV] = "1"
            p = subprocess.run([sys.executable, "-m", "app.cli", *args], cwd=Path(__file__).resolve().parents[1],
                               capture_output=True, text=True, encoding="utf-8", timeout=timeout, env=env)
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


def model_job(source_key: str, *args: str) -> dict | None:
    """A theme-model command (app/ml) as a child (child_job). Skipped quietly while no model is live."""
    from .ml.registry import active
    with SessionLocal() as s:
        if active(s) is None:
            return None
    return child_job(source_key, *args)


@_locked
def recompute_child(weeks: int | None = None) -> dict:
    """The scheduled recomputes (12 weeks at :45, everything at 03:30) as a child process under this
    job's lock, so the ~250 MB a recompute takes goes back to the system when it ends. Logged in
    source_run as "recompute". The in-process recompute() stays for the CLI and the tests."""
    args = ("recompute", "--weeks", str(weeks)) if weeks else ("recompute",)
    return child_job("recompute", *args)


@_locked
def nightly():
    with SessionLocal() as s:
        learning.purge_old_events(s)
        learning.purge_account_leftovers(s)
    for key in ("wikipedia", "acled", "ucdp", "reliefweb"):
        collect(key)
    collect("gnews_social")   # yesterday and the day before, one fixed day each (Google indexes late)
    _resolve_links()
    _mark_recurring()
    # retrain the label-trained part of the theme model; a promoted version re-scores everything
    res = model_job("theme_model_train", "train-small-model")
    if res and res.get("promoted"):
        model_job("theme_model", "classify-items", "--all")
    _checkpoint_wal()


def _mark_recurring() -> int | None:
    """Recurring headlines (daily rates, weather, prayer times) are marked so the scores skip them
    (recurring.py, the accuracy work). Nothing happens until that module exists."""
    try:
        from .recurring import mark_recurring
    except ImportError:
        return None
    with SessionLocal() as s:
        st = mark_recurring(s)   # {"headlines", "marked", "cleared", "articles", "days", "since"}
        log.info("recurring: %s articles marked, %s cleared, %s recurring headlines in %s days",
                 st["marked"], st["cleared"], st["headlines"], st["days"])
        return st["marked"]


def _checkpoint_wal() -> None:
    """Fold the write-ahead log back into the database file and truncate it. The nightly jobs and the
    children leave a WAL of hundreds of MB behind otherwise, which the backup and the disk pay for."""
    from sqlalchemy import text
    from .db import engine
    if not str(engine.url).startswith("sqlite"):
        return
    try:
        with engine.connect() as con:
            busy, log_pages, moved = con.execute(text("PRAGMA wal_checkpoint(TRUNCATE)")).one()
        log.info("wal_checkpoint(TRUNCATE): busy=%s pages=%s moved=%s", busy, log_pages, moved)
    except Exception as e:  # noqa: BLE001 - housekeeping never fails the night
        log.warning("wal_checkpoint failed: %r", e)


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


def six_hourly():
    """The lock is taken per collector, not for the whole job: the run can take 45 minutes, and the :45
    recompute and a hand-run command only wait for the collector that is in progress."""
    each = _locked(collect)
    each("official")
    each("gnews")
    each("gdelt")
    each("fb_url")   # Facebook readings at ~48 h and ~7 days (awaiting key until the Meta app exists)
    each("wikireading")   # Wikimedia publishes each day's file around 02:30-03:00 UTC the next day
    each("fxrate")        # the parallel close is posted after midnight, the official rate late morning


def backup():
    """The nightly off-site backup (backup.py). Recorded as "backup" in the health strip; awaiting_key
    until the bucket's credentials exist. The copy is taken under the job lock, the upload outside it."""
    from . import backup as backup_mod
    with SessionLocal() as s:
        return run_collector(s, "backup", lambda sess: backup_mod.run(sess)).status


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


def ai_audit(provider: str | None = None, force: bool = False):
    """The weekly AI answers audit (ai_audit/runner.py). Not wrapped in _locked: the assistant calls take
    minutes, and holding the lock through them would hold up the hourly collectors. Each answer's short
    write takes the job lock instead (polling up to runner.WRITE_WAIT_SECONDS). Kept out of JOBS: a
    manual run goes through the Admin card, which shows the cost first (POST /api/admin/ai-audit/run)."""
    from .ai_audit.runner import run_all
    return run_all(provider=provider, force=force, lock=joblock.JobLock("ai_audit"))


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
    "recompute": recompute_child,
    "digest": lambda: weekly_digest(force=True),
    "backfill": backfill,
    "resolve_links": resolve_links,
    "fb_url": lambda: _locked(collect)("fb_url"),
    "reach": reach_snapshot,
    "backup": backup,
    "classify": lambda: _locked(model_job)("theme_model", *CLASSIFY_HOURLY),
    "classify_all": lambda: _locked(model_job)("theme_model", "classify-items", "--all"),
}


def start_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler
    sched = BackgroundScheduler(timezone="UTC", job_defaults={"coalesce": True, "max_instances": 1})
    sched.add_job(hourly, "cron", minute=7)
    sched.add_job(six_hourly, "cron", hour="*/6", minute=17)
    sched.add_job(backup, "cron", hour=1, minute=15)                            # off-site copy, before the night's writes
    sched.add_job(nightly, "cron", hour=2, minute=5)
    sched.add_job(recompute_child, "cron", minute=45, kwargs={"weeks": 12})   # recent weeks hourly, as a child
    sched.add_job(recompute_child, "cron", hour=3, minute=30)                   # full history nightly, as a child
    # the digest waits for Sunday's page views (a day or two late): later runs write it once they are in
    sched.add_job(weekly_digest, "cron", day_of_week="tue-thu", hour=6, minute=0)
    sched.add_job(weekly_digest, "cron", day_of_week="mon", hour=6, minute=0)  # after Sunday's data
    sched.add_job(reach_snapshot, "cron", day=1, hour=4, minute=40)            # outlet web rank, monthly
    # after the nightly full recompute (03:30) and before the Monday digest (06:00)
    sched.add_job(ai_audit, "cron", day_of_week="mon", hour=4, minute=20)
    sched.start()
    STATE["scheduler"] = sched
    return sched
