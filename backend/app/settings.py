"""Runtime settings, read from environment variables."""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = Path(os.environ.get("DW_CONFIG_DIR", REPO_ROOT / "config"))
DATA_DIR = Path(os.environ.get("DW_DATA_DIR", REPO_ROOT / "data"))
DATABASE_URL = os.environ.get("DW_DATABASE_URL", f"sqlite:///{(DATA_DIR / 'desert_watch.db').as_posix()}")
FRONTEND_DIST = Path(os.environ.get("DW_FRONTEND_DIST", REPO_ROOT / "frontend" / "dist"))

USER_AGENT = os.environ.get("DW_USER_AGENT", "desert-watch/0.1 (information-desert research tool)")
COOKIE_SECURE = os.environ.get("DW_COOKIE_SECURE", "0") == "1"
SCHEDULER_ENABLED = os.environ.get("DW_SCHEDULER", "0") == "1"

# Keys: every collector that needs one is skipped (and reported as "awaiting key")
# until the key is set.
ACLED_EMAIL = os.environ.get("ACLED_EMAIL")
ACLED_PASSWORD = os.environ.get("ACLED_PASSWORD")
UCDP_TOKEN = os.environ.get("UCDP_TOKEN")
RELIEFWEB_APPNAME = os.environ.get("RELIEFWEB_APPNAME")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
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
RAW_EVENT_RETENTION_DAYS = 365
