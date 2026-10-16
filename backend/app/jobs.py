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
        e = network.compute_all(s, weeks=weeks)
        lb = learning.build_labels(s)
        log.info("recompute: %s new duplicates, %s cells, %s edges, %s new labels", dups, n, e, lb)
        return n


@_locked
def nightly():
    with SessionLocal() as s:
        learning.purge_old_events(s)
    for key in ("wikipedia", "acled", "ucdp", "reliefweb"):
        collect(key)


@_locked
def hourly():
    collect("rss")
    collect("galerts")


@_locked
def six_hourly():
    collect("official")
    collect("gnews")
    collect("gdelt")


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
    "galerts": lambda: _locked(collect)("galerts"),
    "gnews": lambda: _locked(collect)("gnews"),
    "official": lambda: _locked(collect)("official"),
    "gdelt": lambda: _locked(collect)("gdelt"),
    "gdelt_timeline": lambda: _locked(collect)("gdelt_timeline"),
    "wikipedia": lambda: _locked(collect)("wikipedia"),
    "recompute": recompute,
    "digest": lambda: weekly_digest(force=True),
    "backfill": backfill,
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
    sched.start()
    return sched
