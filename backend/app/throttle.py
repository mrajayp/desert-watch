"""Sign-in throttle, in memory (one process, one machine).

Per email: after EMAIL_FAILURES wrong passwords in WINDOW the next attempt is held back, first for
FIRST_HOLD seconds, doubling with every further failure up to MAX_HOLD, and the API answers 429 with
Retry-After. The count clears on a successful sign-in. Per address: a soft cap, IP_FAILURES in WINDOW
for a short fixed hold. Soft because Libyan mobile networks put many readers behind one address, so
the per-email hold carries the protection and the address cap only slows a spray across emails.

Addresses are never kept as they are: ip_key() hashes them with a salt that is new on every process
start and changes daily, which is also what the sign-up limiter keys on."""
import hashlib
import math
import secrets
import threading
import time
from datetime import date

WINDOW = 15 * 60
EMAIL_FAILURES = 5
FIRST_HOLD = 60
MAX_HOLD = 15 * 60
IP_FAILURES = 50
IP_HOLD = 60
MAX_KEYS = 10_000

_SALT = secrets.token_hex(16)


def ip_key(ip: str | None, day: date | None = None) -> str:
    """A daily-salted hash of an address: the same within a day, unrelated across days or restarts."""
    return hashlib.sha256(f"{_SALT}:{(day or date.today()).isoformat()}:{ip or '?'}".encode()).hexdigest()[:24]


class Throttle:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._fails: dict[str, list[float]] = {}
        self._hold: dict[str, float] = {}     # key -> monotonic time the hold ends
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        hits = [t for t in self._fails.get(key, []) if now - t < WINDOW]
        if hits:
            self._fails[key] = hits
        else:
            self._fails.pop(key, None)
        return hits

    def check(self, email: str, ip: str | None = None) -> int:
        """Seconds to wait before this email or address may try again, 0 when it may try now."""
        now = self._clock()
        with self._lock:
            waits = [self._hold.get(k, 0.0) - now for k in (email.strip().lower(), ip_key(ip)) if k in self._hold]
            for k in [k for k, until in self._hold.items() if until <= now]:
                del self._hold[k]
        return max(0, math.ceil(max(waits))) if waits else 0

    def failed(self, email: str, ip: str | None = None) -> int:
        """Record a failure. Returns the hold now placed on the email, in seconds (0 for none yet)."""
        now = self._clock()
        key, ipk = email.strip().lower(), ip_key(ip)
        with self._lock:
            self._trim()
            hits = self._recent(key, now) + [now]
            self._fails[key] = hits
            hold = 0
            if len(hits) >= EMAIL_FAILURES:
                hold = min(MAX_HOLD, FIRST_HOLD * 2 ** (len(hits) - EMAIL_FAILURES))
                self._hold[key] = now + hold
            ip_hits = self._recent(ipk, now) + [now]
            self._fails[ipk] = ip_hits
            if len(ip_hits) >= IP_FAILURES:
                self._hold[ipk] = max(self._hold.get(ipk, 0.0), now + IP_HOLD)
            return hold

    def succeeded(self, email: str) -> None:
        key = email.strip().lower()
        with self._lock:
            self._fails.pop(key, None)
            self._hold.pop(key, None)

    def _trim(self) -> None:
        """Keep the tables bounded: drop the oldest entries past MAX_KEYS (a spray of made-up emails)."""
        if len(self._fails) > MAX_KEYS:
            for k in list(self._fails)[: len(self._fails) - MAX_KEYS]:
                self._fails.pop(k, None)
                self._hold.pop(k, None)

    def reset(self) -> None:
        with self._lock:
            self._fails.clear()
            self._hold.clear()


LOGIN = Throttle()
