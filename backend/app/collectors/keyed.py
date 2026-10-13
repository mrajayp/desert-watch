"""Need-lens collectors that need credentials (ACLED, UCDP, ReliefWeb). Until the
key is configured each one records an "awaiting_key" run, so the dashboard shows
exactly what is missing. Implementations land in Phase 3 once keys are issued
(see plan: ACLED via OAuth/myACLED aggregated weekly admin1 data; UCDP token;
ReliefWeb pre-approved appname)."""
from sqlalchemy.orm import Session

from .. import settings
from .base import AwaitingKey, RunResult


def acled(s: Session) -> RunResult:
    if not (settings.ACLED_EMAIL and settings.ACLED_PASSWORD):
        raise AwaitingKey("Set ACLED_EMAIL / ACLED_PASSWORD (myACLED account, OAuth).")
    raise NotImplementedError("ACLED collector: Phase 3")


def ucdp(s: Session) -> RunResult:
    if not settings.UCDP_TOKEN:
        raise AwaitingKey("Set UCDP_TOKEN (request by email; 3-5 working days).")
    raise NotImplementedError("UCDP collector: Phase 3")


def reliefweb(s: Session) -> RunResult:
    if not settings.RELIEFWEB_APPNAME:
        raise AwaitingKey("Set RELIEFWEB_APPNAME (pre-approved appname, required since Nov 2025).")
    raise NotImplementedError("ReliefWeb collector: Phase 3")
