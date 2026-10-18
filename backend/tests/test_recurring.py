"""Recurring posts (daily rates, weather, prayer times) are not stories: recurring.py marks them and
every count skips them (scoring.counted_items)."""
from datetime import date, datetime, timedelta

from sqlalchemy import select

from app.dedupe import mark_duplicates
from app.ingest import load_rules, store_article
from app.models import CellWeek, Item, Outlet
from app.recurring import RECUR_MIN, mark_recurring, recurrence_key
from app.scoring import compute, week_start
from tests.conftest import ids, login
from tests.test_scoring import _pageviews

AR_DAYS = ("الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت")
EN_DAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")


def test_recurrence_key_drops_digits_and_weekday_names():
    a = recurrence_key("أسعار صرف الدينار في ليبيا اليوم الخميس 8 أكتوبر 2026")
    b = recurrence_key("أسعار صرف الدينار في ليبيا اليوم الجمعة 9 أكتوبر 2026")
    assert a == b and "8" not in a and "الخميس" not in a and a.startswith("اسعار صرف")
    assert recurrence_key("Libya exchange rates on Monday 12 October") == recurrence_key("Libya exchange rates on Tuesday 13 October")
    assert recurrence_key("#ليبيا | الطقس اليوم في ليبيا") == recurrence_key("الطقس اليوم في ليبيا")   # a feed's hashtag label
    assert recurrence_key("Dinar falls after 10 days of protests") != recurrence_key("Dinar falls after a week of protests")
    assert recurrence_key("12 3") == "" and recurrence_key(None) == ""


def _fx_title(d: int) -> str:
    return f"أسعار صرف الدينار في ليبيا اليوم {AR_DAYS[d % 7]} {d + 1} أكتوبر"


def test_mark_recurring_flags_daily_posts_per_outlet_family_and_clears_them_again(db):
    cid = db.scalar(select(Outlet.country_id).limit(1))
    rules = load_rules(db, cid)
    now = datetime(2026, 10, 12, 12)
    # a daily exchange-rate post at one outlet for 5 days, also found by Google News on one of them
    for d in range(5):
        store_article(db, cid, rules, url=f"https://ex.ly/fx/{d}", title=_fx_title(d), published_at=now - timedelta(days=d),
                      source_key="rss")
    store_article(db, cid, rules, url="https://news.google.com/rss/articles/fx0", outlet_domain="ex.ly", title=_fx_title(0),
                  published_at=now + timedelta(hours=1), source_key="gnews")
    # the same post twice at another outlet: below the threshold
    for d in range(2):
        store_article(db, cid, rules, url=f"https://other.ly/fx/{d}", title=_fx_title(d), published_at=now - timedelta(days=d),
                      source_key="rss")
    # a story whose headline carries a number is not recurring
    store_article(db, cid, rules, url="https://ex.ly/s/1", title="Libya: 3 hospitals in Sabha close for lack of medicines",
                  published_at=now, source_key="rss")
    # a weather post split between the outlet's site (once) and its Facebook page (twice): one family, three times
    page, _ = store_article(db, cid, rules, url="https://www.facebook.com/expage/posts/1", title="الطقس في ليبيا اليوم الاثنين 12 أكتوبر",
                            published_at=now, source_key="gnews_social")
    db.get(Outlet, page.outlet_id).external = {"parent": "ex.ly"}
    store_article(db, cid, rules, url="https://www.facebook.com/expage/posts/2", title="الطقس في ليبيا اليوم الأحد 11 أكتوبر",
                  published_at=now - timedelta(days=1), source_key="gnews_social")
    store_article(db, cid, rules, url="https://ex.ly/weather/10", title="الطقس في ليبيا اليوم السبت 10 أكتوبر",
                  published_at=now - timedelta(days=2), source_key="rss")
    db.commit()
    assert mark_duplicates(db) == 1
    res = mark_recurring(db, now=now)
    assert res["headlines"] == 2 and res["marked"] == 9 and res["cleared"] == 0    # 5 + the Google copy, 3 weather posts
    db.expire_all()
    flagged = {it.url for it in db.scalars(select(Item).where(Item.kind == "article")) if (it.extra or {}).get("recurring")}
    assert all(u.startswith(("https://ex.ly/fx/", "https://ex.ly/weather", "https://www.facebook.com/expage/")) or "fx0" in u
               for u in flagged) and len(flagged) == 9
    assert not any("other.ly" in u or "/s/1" in u for u in flagged)
    assert mark_recurring(db, now=now) == {**res, "marked": 0, "cleared": 0}               # idempotent
    # the verdict follows the headline's own dates, not the day the job runs: a month on, the newest
    # posts still sit in a 30-day span with three repeats, so nothing is cleared
    later = mark_recurring(db, now=now + timedelta(days=29))
    assert later["marked"] == 0 and later["cleared"] == 0 and later["articles"] == 8      # judged: published since 29 days ago
    # three of the five rate posts are deleted: the two that are left, and the Google copy, no longer recur
    for d in (2, 3, 4):
        db.delete(db.scalar(select(Item).where(Item.url == f"https://ex.ly/fx/{d}")))
    db.commit()
    again = mark_recurring(db, now=now)
    assert again["marked"] == 0 and again["cleared"] == 3 and again["headlines"] == 1
    db.expire_all()
    still = {it.url for it in db.scalars(select(Item).where(Item.kind == "article")) if (it.extra or {}).get("recurring")}
    assert still == {"https://ex.ly/weather/10", "https://www.facebook.com/expage/posts/1", "https://www.facebook.com/expage/posts/2"}
    # history in one pass: `since` judges everything from that day on
    assert mark_recurring(db, now=now + timedelta(days=200), since=now - timedelta(days=10))["articles"] == 9
    assert RECUR_MIN == 3


def test_recurring_posts_are_skipped_by_scores_bars_and_lists(client, users, db):
    themes, regions = ids(db)
    cid = db.scalar(select(Outlet.country_id).limit(1))
    rules = load_rules(db, cid)
    today = date(2026, 10, 12)
    vary = ("worsen", "ease", "persist", "return", "spread", "continue", "deepen")   # a new headline each week
    for w in range(24):
        day = datetime.combine(week_start(today) - timedelta(weeks=w), datetime.min.time()) + timedelta(hours=9)
        _pageviews(db, cid, themes["health"], day.date(), 2000)
        store_article(db, cid, rules, url=f"https://old.ly/h/{w}", title=f"Hospital shortages in Sabha {vary[w % 7]}",
                      published_at=day, source_key="rss")
    # a daily "hospital bulletin" post for the last 10 days: health words, a place, a weekday and a date
    for d in range(10):
        when = datetime.combine(today + timedelta(days=6 - d), datetime.min.time()) + timedelta(hours=8)
        store_article(db, cid, rules, url=f"https://old.ly/bulletin/{d}",
                      title=f"Sabha hospital daily bulletin {EN_DAYS[when.weekday() % 7]} {when.day} October",
                      published_at=when, source_key="rss")
    db.commit()
    now = today + timedelta(days=7)
    assert mark_recurring(db, now=datetime.combine(now, datetime.min.time()))["marked"] == 10
    compute(db, cid, weeks=3, today=now)
    cell = db.scalar(select(CellWeek).where(CellWeek.theme_id == themes["health"], CellWeek.region_id == regions["national"],
                                            CellWeek.lens == "audience", CellWeek.week_start == week_start(today)))
    assert cell.coverage == 4 and cell.breakdown["articles_4w"] == 4 and abs(cell.gap) < 0.2
    login(client, "admin@example.org", "admin-password-1")
    rows = client.get("/api/cells/trends", params={"lens": "audience"}).json()["themes"][str(themes["health"])]["rows"]
    last = next(x for x in rows if x["week"] == week_start(today).isoformat())
    assert last["articles"] == 1 and last["articles_all"] == 1
    wk = week_start(today)
    listed = client.get("/api/items", params={"theme_id": themes["health"], "start": wk.isoformat(),
                                               "end": (wk + timedelta(days=6)).isoformat()}).json()
    assert listed["total"] == 1 and "bulletin" not in listed["items"][0]["url"]
    assert client.get("/api/contribute").json()["to_assess"] == [] or all(
        "bulletin" not in x["url"] for x in client.get("/api/contribute").json()["to_assess"])
