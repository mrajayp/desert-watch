from . import fb_engagement, fxrate, galerts, gdelt, gnews, gnews_social, keyed, official, rss, wikipedia, wikireading

# key -> (callable, human description). Order = scheduler order.
COLLECTORS = {
    "rss": (rss.collect, "Outlet RSS feeds"),
    "youtube": (rss.collect_youtube, "YouTube channel feeds"),
    "galerts": (galerts.collect, "Google Alerts feeds"),
    "official": (official.collect, "Official statements + ReliefWeb reports"),
    "gnews": (gnews.collect, "Google News search (Arabic + English)"),
    "gnews_social": (gnews_social.collect, "Social media posts indexed by Google News"),
    "gdelt": (gdelt.collect, "GDELT article lists"),
    "gdelt_timeline": (gdelt.collect_timeline, "GDELT coverage history"),
    "wikipedia": (wikipedia.collect, "Wikipedia pageviews"),
    "wikireading": (wikireading.collect, "Wikipedia pages read in Libya (Wikimedia, privacy-protected)"),
    "fxrate": (fxrate.collect, "Dinar exchange rates (parallel market and central bank)"),
    "acled": (keyed.acled, "ACLED events"),
    "ucdp": (keyed.ucdp, "UCDP events"),
    "reliefweb": (keyed.reliefweb, "ReliefWeb reports"),
    "fb_url": (fb_engagement.collect, "Facebook link engagement"),
}
# Non-collector jobs shown in the source-health strip.
EXTRA_HEALTH = {
    "digest": "Weekly AI digest",
    "gtrends": "Google searches (weekly import)",
    "resolve": "Outlet links for Google News items",
}
# Hours before a source counts as stale (48 unless listed). Search data is imported by hand each week.
STALE_HOURS = {"gtrends": 10 * 24}
