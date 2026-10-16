from . import galerts, gdelt, gnews, gnews_social, keyed, official, rss, wikipedia

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
    "acled": (keyed.acled, "ACLED events"),
    "ucdp": (keyed.ucdp, "UCDP events"),
    "reliefweb": (keyed.reliefweb, "ReliefWeb reports"),
}
# Non-collector jobs shown in the source-health strip.
EXTRA_HEALTH = {
    "digest": "Weekly AI digest",
}
