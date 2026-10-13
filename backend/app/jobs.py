"""Scheduled jobs. Each opens its own session; collectors are wrapped by run_collector
so failures are recorded, not raised. Jobs share one lock so SQLite sees one writer."""
import logging
import threading

from . import learning, network, scoring
from .collectors import COLLECTORS
from .collectors.base import run_collector
from .db import SessionLocal
from .ingest import apply_relevance_guard, infer_scopes
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
    with SessionLocal() as s:
        if weeks is None:
            from datetime import date
            from sqlalchemy import func, select
            from .models import Item
            first = s.scalar(select(func.min(Item.published_at)).where(Item.kind == "article"))
            weeks = min(210, max(12, ((date.today() - first.date()).days // 7) + 1)) if first else 12
        infer_scopes(s)
        for c in s.query(Country).all():
            apply_relevance_guard(s, c.id)
        n = scoring.compute_all(s, weeks=weeks)
        e = network.compute_all(s)
        lb = learning.build_labels(s)
        log.info("recompute: %s cells, %s edges, %s new labels", n, e, lb)
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
    collect("gnews")
    collect("gdelt")


@_locked
def backfill(weeks: int = 12):
    collect("gnews", weeks=weeks)
    collect("wikipedia", days=7 * (weeks + 16))
    collect("gdelt_timeline")
    collect("rss")


JOBS = {
    "rss": lambda: _locked(collect)("rss"),
    "galerts": lambda: _locked(collect)("galerts"),
    "gnews": lambda: _locked(collect)("gnews"),
    "gdelt": lambda: _locked(collect)("gdelt"),
    "gdelt_timeline": lambda: _locked(collect)("gdelt_timeline"),
    "wikipedia": lambda: _locked(collect)("wikipedia"),
    "recompute": recompute,
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
    sched.start()
    return sched
