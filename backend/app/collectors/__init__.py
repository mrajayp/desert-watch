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
}
# Hours before a source counts as stale (48 unless listed). Search data is imported by hand each week.
STALE_HOURS = {"gtrends": 10 * 24}
