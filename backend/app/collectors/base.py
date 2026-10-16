"""Collector runner: every run is recorded in source_run so the dashboard can show
freshness and errors, and a failure in one collector never stops the others."""
import logging
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import httpx
from sqlalchemy.orm import Session

from .. import settings
from ..models import SourceRun, utcnow

log = logging.getLogger("desert_watch.collectors")


class AwaitingKey(Exception):
    """Raised when a collector's credential is not configured yet."""


@dataclass
class RunResult:
    rows: int = 0
    errors: int = 0
    detail: str = ""


def http_client(timeout: float = 30) -> httpx.Client:
    return httpx.Client(timeout=timeout, follow_redirects=True,
                        headers={"User-Agent": settings.USER_AGENT})


def polite_get(client: httpx.Client, url: str, *, params=None, min_interval: float = 1.0,
               retries: int = 2, backoff: float | None = None, state: dict = {}, headers=None) -> httpx.Response:
    """GET with a per-host minimum interval and exponential backoff on 429/5xx: waits
    backoff (default min_interval) x 2, x 4, ... or longer if the server's Retry-After asks (max 120 s)."""
    host = httpx.URL(url).host
    for attempt in range(retries + 1):
        wait = state.get(host, 0) + min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        r = client.get(url, params=params, headers=headers)
        state[host] = time.monotonic()
        if r.status_code == 429 or r.status_code >= 500 or "Please limit requests" in r.text[:200]:
            if attempt < retries:
                asked = r.headers.get("retry-after", "")
                time.sleep(max(min(float(asked), 120.0) if asked.isdigit() else 0.0,
                               (backoff or min_interval) * (2 ** (attempt + 1))))
            continue
        return r
    return r


STOP_AFTER = 3  # refused requests in a row (after their retries) end a collector run


def refused(r: httpx.Response) -> bool:
    """The server said no (rate limit or overload) instead of answering. A run that keeps asking only
    holds the job lock longer, so collectors stop after STOP_AFTER of these in a row."""
    return r.status_code == 429 or r.status_code >= 500 or "Please limit requests" in r.text[:200]


def to_naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def run_collector(s: Session, source_key: str, fn: Callable[[Session], RunResult]) -> SourceRun:
    run = SourceRun(source_key=source_key, started_at=utcnow(), status="running")
    s.add(run)
    s.commit()
    try:
        res = fn(s)
        run.rows = res.rows
        run.ok = res.errors == 0
        run.status = "ok" if res.errors == 0 else ("partial" if res.rows else "error")
        run.error = res.detail or None
        s.commit()
    except AwaitingKey as e:
        s.rollback()
        run.status, run.error = "awaiting_key", str(e)
    except Exception as e:  # noqa: BLE001 - record and carry on
        s.rollback()
        log.exception("collector %s failed", source_key)
        run.status, run.error = "error", f"{e}\n{traceback.format_exc()[-1500:]}"
    run.finished_at = utcnow()
    s.add(run)
    s.commit()
    return run
