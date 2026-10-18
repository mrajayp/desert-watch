"""Need-lens collectors that need credentials (ACLED, UCDP, ReliefWeb). Until the
key is configured each one records an "awaiting_key" run, so the dashboard shows
exactly what is missing. The collectors themselves are not written yet: once a key is
set they record a "not_built" run (NotBuilt), so the health strip says so instead of
showing a traceback. The designs are in the plan (ACLED via OAuth/myACLED aggregated
weekly admin1 data; UCDP GED candidate; ReliefWeb v2 with a pre-approved appname)."""
from sqlalchemy.orm import Session

from .. import settings
from ..i18n import N_
from .base import AwaitingKey, NotBuilt, RunResult

NOT_BUILT = N_("Key set; collector not written yet.")


def acled(s: Session) -> RunResult:
    if not (settings.ACLED_EMAIL and settings.ACLED_PASSWORD):
        raise AwaitingKey("Set ACLED_EMAIL / ACLED_PASSWORD (myACLED account, OAuth).")
    raise NotBuilt(NOT_BUILT)


def ucdp(s: Session) -> RunResult:
    if not settings.UCDP_TOKEN:
        raise AwaitingKey("Set UCDP_TOKEN. Request it by email. It takes 3 to 5 working days.")
    raise NotBuilt(NOT_BUILT)


def reliefweb(s: Session) -> RunResult:
    if not settings.RELIEFWEB_APPNAME:
        raise AwaitingKey("Set RELIEFWEB_APPNAME (pre-approved appname, required since Nov 2025).")
    raise NotBuilt(NOT_BUILT)
