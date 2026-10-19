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
    # the Sunday re-query of Google News for the weeks aged 2 to 4 weeks (gnews.settle), 05:00 UTC
    "gnews_settle": N_("Google News searched again for the weeks aged 2 to 4 weeks (Sundays)"),
    # the monthly web-rank snapshot of the outlets (reach.py), the 1st at 04:40 UTC
    "reach": N_("Outlet web rank (Tranco, monthly)"),
    # the nightly search for outlet feeds (collectors/feeds.py), 50 outlets a night after the social posts
    "discover_feeds": N_("Feed discovery (50 outlets a night)"),
}
# How often each source is scheduled to run, in hours (jobs.start_scheduler). None = run by hand with
# no cadence (gdelt_timeline, the backfills): such a source is never stale, the strip says "manual,
# last run ...". The weekly search import (gtrends) is also by hand, but it has a cadence: the search
# lens silently loses its data when a week is missed, so it keeps its 10-day stale rule below. The API
# sends the schedule as expected_hours so the interface can say "runs every N hours" beside the last run.
SCHEDULE_HOURS = {
    "rss": 1, "youtube": 1, "galerts": 1,                                   # hourly, :07
    "official": 6, "gnews": 6, "gdelt": 6, "fb_url": 6, "wikireading": 6, "fxrate": 6,   # six-hourly, :17
    "gnews_social": 24, "wikipedia": 24, "acled": 24, "ucdp": 24, "reliefweb": 24,       # nightly, 02:05
    "resolve": 24, "discover_feeds": 24, "backup": 24,
    "digest": 7 * 24, "ai_audit_anthropic": 7 * 24, "ai_audit_openai": 7 * 24, "ai_audit_perplexity": 7 * 24,
    "gnews_settle": 7 * 24, "gtrends": 7 * 24,
    "reach": 30 * 24,
    "gdelt_timeline": None, "backfill": None, "rss_backfill": None,
}
# Sources run by hand: never stale (no cadence), or stale only by their own rule (gtrends).
MANUAL = frozenset({"gdelt_timeline", "backfill", "rss_backfill", "gtrends"})
# Hours before a source counts as stale: twice its schedule, except where a job is allowed to run late
# (the weekly digest waits for Sunday's page views and may write on Thursday: 8 days; the monthly web
# rank: 35 days; the nightly backup must not miss a night: 30 hours), the weekly audit and re-query
# (8 days) and the weekly search import (10 days: a missed week). A source not scheduled at all is
# stale after 48 hours; one run by hand with no cadence is never stale (stale_hours()).
STALE_HOURS = {"gtrends": 10 * 24, "ai_audit_anthropic": 8 * 24, "ai_audit_openai": 8 * 24,
               "ai_audit_perplexity": 8 * 24, "backup": 30, "gnews_settle": 8 * 24, "digest": 8 * 24,
               "reach": 35 * 24}


def stale_hours(key: str) -> int | None:
    """Hours after the last good run before `key` is stale: STALE_HOURS, else twice SCHEDULE_HOURS, else
    48. None for a source run by hand with no cadence (SCHEDULE_HOURS None): it is never stale."""
    if key in STALE_HOURS:
        return STALE_HOURS[key]
    if key in SCHEDULE_HOURS and SCHEDULE_HOURS[key] is None:
        return None
    sched = SCHEDULE_HOURS.get(key)
    return 2 * sched if sched else 48
