from . import galerts, gdelt, gnews, keyed, official, rss, wikipedia

# key -> (callable, human description). Order = scheduler order.
COLLECTORS = {
    "rss": (rss.collect, "Outlet RSS feeds"),
    "galerts": (galerts.collect, "Google Alerts feeds"),
    "official": (official.collect, "Official statements + ReliefWeb reports"),
    "gnews": (gnews.collect, "Google News search (Arabic + English)"),
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
    "resolve": "Outlet links for Google News items",
}
