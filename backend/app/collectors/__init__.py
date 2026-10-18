from . import fb_engagement, fxrate, galerts, gdelt, gnews, gnews_social, keyed, official, rss, wikipedia, wikireading
from ..i18n import N_

# key -> (callable, human description). Order = scheduler order.
COLLECTORS = {
    "rss": (rss.collect, N_("Outlet RSS feeds")),
    "youtube": (rss.collect_youtube, N_("YouTube channel feeds")),
    "galerts": (galerts.collect, N_("Google Alerts feeds")),
    "official": (official.collect, N_("Official statements + ReliefWeb reports")),
    "gnews": (gnews.collect, N_("Google News search (Arabic + English)")),
    "gnews_social": (gnews_social.collect, N_("Social media posts indexed by Google News")),
    "gdelt": (gdelt.collect, N_("GDELT article lists")),
    "gdelt_timeline": (gdelt.collect_timeline, N_("GDELT coverage history")),
    "wikipedia": (wikipedia.collect, N_("Wikipedia pageviews")),
    "wikireading": (wikireading.collect, N_("Wikipedia pages read in Libya (Wikimedia, privacy-protected)")),
    "fxrate": (fxrate.collect, N_("Dinar exchange rates (parallel market and central bank)")),
    "acled": (keyed.acled, N_("ACLED events")),
    "ucdp": (keyed.ucdp, N_("UCDP events")),
    "reliefweb": (keyed.reliefweb, N_("ReliefWeb reports")),
    "fb_url": (fb_engagement.collect, N_("Facebook link engagement")),
}
# Non-collector jobs shown in the source-health strip.
EXTRA_HEALTH = {
    "digest": N_("Weekly AI digest"),
    "gtrends": N_("Google searches (weekly import)"),
    "resolve": N_("Outlet links for Google News items"),
    # the weekly AI answers audit, one line per assistant (ai_audit/runner.py)
    "ai_audit_anthropic": N_("AI answers audit: Claude"),
    "ai_audit_openai": N_("AI answers audit: ChatGPT"),
    "ai_audit_perplexity": N_("AI answers audit: Perplexity"),
    # the nightly off-site copy of the database (backup.py), 01:15 UTC
    "backup": N_("Nightly database backup (off-site)"),
}
# Hours before a source counts as stale (48 unless listed). Search data is imported by hand each week;
# the AI answers audit runs once a week (Monday 04:20 UTC), so it is stale after 8 days; the backup
# runs nightly, so a missed night shows after 30 hours.
STALE_HOURS = {"gtrends": 10 * 24, "ai_audit_anthropic": 8 * 24, "ai_audit_openai": 8 * 24,
               "ai_audit_perplexity": 8 * 24, "backup": 30}
