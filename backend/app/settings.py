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
# Facebook link engagement: a Meta developer app's id and secret (app token = "<id>|<secret>").
FB_APP_ID = os.environ.get("DW_FB_APP_ID")
FB_APP_SECRET = os.environ.get("DW_FB_APP_SECRET")
FB_DAILY_URLS = int(os.environ.get("DW_FB_DAILY_URLS", "400"))   # URL lookups in any 24 hours
# Weekly digest model: Haiku per the approved plan (one short call per week). Override to e.g.
# claude-opus-5-5 for a richer brief.
DIGEST_MODEL = os.environ.get("DW_DIGEST_MODEL", "claude-haiku-5-5")

# Scoring
WINDOW_WEEKS = 4            # rolling window per cell
MIN_NEED_UNITS = {          # below this a cell is "insufficient evidence"
    "audience": 500,        # pageviews in window
    "events": 3,
    "humanitarian": 2,
    "journalist": 1,
}
SHRINK_STRENGTH = {"audience": 2000, "events": 10, "humanitarian": 5, "journalist": 2}
# Search lens (Google Trends, anchor units). A cell is insufficient when any week of its window
# lacks data (gtrends.flag_missing_weeks), not below a need level. Shrink ~ a quarter of the
# smallest list's 4-week need (governance, ~57 in 2025-26). Coverage counts there are in the
# hundreds, so it barely moves the gap (checked 20 / 50 / 100 on the 2026-10-16 snapshot).
MIN_NEED_UNITS["search"] = 1
SHRINK_STRENGTH["search"] = 20
RAW_EVENT_RETENTION_DAYS = 365
# Gap score: gap = ln((E + A) / (C + A)), E = expected articles (reference x need), C = articles counted.
PRIOR_ARTICLES = 5          # A: the prior, in articles, for every lens (MIN_NEED_UNITS/SHRINK_STRENGTH no longer decide)
MIN_EXPECTED_ARTICLES = 3   # a cell is judged only when E reaches this
GAP_RED_FROM = 0.4          # about 1.5 times fewer articles than expected
PAGEVIEW_SPIKE_CAP = 5      # a title's day counts at most this many times its trailing 28-day median
