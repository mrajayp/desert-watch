"""Runtime settings, read from environment variables."""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = Path(os.environ.get("DW_CONFIG_DIR", REPO_ROOT / "config"))
DATA_DIR = Path(os.environ.get("DW_DATA_DIR", REPO_ROOT / "data"))
DATABASE_URL = os.environ.get("DW_DATABASE_URL", f"sqlite:///{(DATA_DIR / 'desert_watch.db').as_posix()}")
FRONTEND_DIST = Path(os.environ.get("DW_FRONTEND_DIST", REPO_ROOT / "frontend" / "dist"))

# Wikimedia asks for a contact URL in the User-Agent (meta.wikimedia.org/wiki/User-Agent_policy)
USER_AGENT = os.environ.get("DW_USER_AGENT",
                            "desert-watch/0.2 (https://desert-watch.fly.dev; information-desert research tool)")
COOKIE_SECURE = os.environ.get("DW_COOKIE_SECURE", "0") == "1"
SCHEDULER_ENABLED = os.environ.get("DW_SCHEDULER", "0") == "1"

# Keys: every collector that needs one is skipped (and reported as "awaiting key")
# until the key is set.
ACLED_EMAIL = os.environ.get("ACLED_EMAIL")
ACLED_PASSWORD = os.environ.get("ACLED_PASSWORD")
UCDP_TOKEN = os.environ.get("UCDP_TOKEN")
RELIEFWEB_APPNAME = os.environ.get("RELIEFWEB_APPNAME")
# Search lens providers (both optional; the default route is a local fetch + import-search).
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
GOOGLE_TRENDS_API_KEY = os.environ.get("GOOGLE_TRENDS_API_KEY")  # official API: closed alpha
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
# Off-site backups (backup.py): an S3-compatible bucket. Fly's Tigris integration (`fly storage create`)
# sets exactly these names as secrets; until they exist the nightly backup records "awaiting_key".
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_ENDPOINT_URL_S3 = os.environ.get("AWS_ENDPOINT_URL_S3")
AWS_REGION = os.environ.get("AWS_REGION", "auto")
BUCKET_NAME = os.environ.get("BUCKET_NAME")
BACKUP_PREFIX = os.environ.get("DW_BACKUP_PREFIX", "backups/")
BACKUP_KEEP = {"daily": 7, "weekly": 4, "monthly": 3}   # retention after a successful upload
# Facebook link engagement: a Meta developer app's id and secret (app token = "<id>|<secret>").
FB_APP_ID = os.environ.get("DW_FB_APP_ID")
FB_APP_SECRET = os.environ.get("DW_FB_APP_SECRET")
FB_DAILY_URLS = int(os.environ.get("DW_FB_DAILY_URLS", "400"))   # URL lookups in any 24 hours
# Weekly digest model: Haiku per the approved plan (one short call per week). Override to e.g.
# claude-opus-5-5 for a richer brief.
DIGEST_MODEL = os.environ.get("DW_DIGEST_MODEL", "claude-haiku-5-5")

# Scoring
WINDOW_WEEKS = 4            # rolling window per cell
# Pooled lenses only (scoring.need_floor): below this need in a window a cell is not judged
# (reason too_little_need). The own-history lenses have no need floor: the audience lens relies on
# the prior and MIN_EXPECTED_ARTICLES, and the search lens on every week of its window having data
# (gtrends.flag_missing_weeks).
MIN_NEED_UNITS = {
    "events": 3,
    "humanitarian": 2,
    "journalist": 1,
}
RAW_EVENT_RETENTION_DAYS = 365
# Gap score: gap = ln((E + A) / (C + A)), E = expected articles (reference x need), C = articles counted.
PRIOR_ARTICLES = 5          # A: the prior, in articles, for every lens (replaces the old per-lens shrink strengths)
MIN_EXPECTED_ARTICLES = 3   # a cell is judged only when E reaches this
GAP_RED_FROM = 0.4          # about 1.5 times fewer articles than expected
PAGEVIEW_SPIKE_CAP = 5      # a title's day counts at most this many times its trailing 28-day median
