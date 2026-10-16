"""Google Trends search lens: row building, the local fetcher's politeness, config checks."""
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
import yaml

from app import settings
from app.gtrends import (DAILY_MAX_DAYS, anchor_refs, build_rows, check_baskets, config, groups, parse_points,
                         slot)
from scripts.fetch_gtrends import Client, Stop, plan


def _ts(d: date) -> str:
    return str(int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp()))


def _point(d, values, has=None, partial=False):
    p = {"time": _ts(d), "value": values, "hasData": has or [True] * len(values)}
    if partial:
        p["isPartial"] = True
    return p


def test_weekly_rows_move_sunday_weeks_to_monday_and_mark_the_last_two_provisional():
    sun = date(2026, 9, 6)  # a Sunday
    tl = [_point(sun + timedelta(weeks=i), [10 + i, 20]) for i in range(5)]
    tl[1]["hasData"] = [False, True]          # list below Google's threshold
    tl[2]["hasData"] = [True, False]          # anchor below threshold: no ratio either
    tl.append(_point(sun + timedelta(weeks=5), [99, 20], partial=True))
    rows = build_rows(parse_points(tl), [("services", ["الكهرباء", "المياه"])], "مطعم", resolution="week",
                      request_id="r1", fetched_at="2026-10-16T06:00:00+00:00")
    assert [r["week"] for r in rows] == [(sun + timedelta(weeks=i, days=1)).isoformat() for i in range(5)]
    assert all(date.fromisoformat(r["week"]).weekday() == 0 for r in rows)
    assert [r["has_data"] for r in rows] == [True, False, False, True, True]
    assert [r["provisional"] for r in rows] == [False, False, False, True, True]
    assert rows[0]["value_raw"] == 10 and rows[0]["anchor_raw"] == 20 and rows[0]["basket"] == ["الكهرباء", "المياه"]
    assert {"theme_slug", "basket", "anchor", "week", "value_raw", "anchor_raw", "has_data", "fetched_at",
            "request_id"} <= set(rows[0])


def test_daily_rows_sum_whole_monday_weeks_only():
    start = date(2026, 9, 2)  # a Wednesday: the first, incomplete week is dropped
    days = [start + timedelta(days=i) for i in range(5 + 14 + 3)]
    tl = [_point(d, [2, 4]) for d in days]
    first_full = date(2026, 9, 7)
    tl[days.index(first_full + timedelta(days=1))]["hasData"] = [False, True]   # one day without data: still counts
    second = first_full + timedelta(weeks=1)
    for k in (0, 1):
        tl[days.index(second + timedelta(days=k))]["hasData"] = [False, True]  # two days: the week lacks data
    tl[-1]["isPartial"] = True
    rows = build_rows(parse_points(tl), [("economy", ["الدينار"])], "مطعم", resolution="day", request_id="r",
                      fetched_at="t")
    assert [r["week"] for r in rows] == [first_full.isoformat(), second.isoformat()]
    assert rows[0]["value_raw"] == 14 and rows[0]["anchor_raw"] == 28
    assert rows[0]["has_data"] and rows[0]["nodata_days"] == 1
    assert not rows[1]["has_data"] and rows[1]["nodata_days"] == 2


def test_anchor_ref_ignores_a_one_week_spike():
    weeks = [(date(2026, 1, 5) + timedelta(weeks=i)).isoformat() for i in range(20)]
    rows = [{"week": w, "anchor_raw": 30 if i == 10 else 10} for i, w in enumerate(weeks)]
    refs = anchor_refs(rows)
    assert refs[weeks[10]] == 10
    rows[3]["anchor_raw"] = 0  # anchor without data is left out of the median
    assert anchor_refs(rows)[weeks[3]] == 10


def test_slots_and_groups():
    assert slot([" الكهرباء", "المياه "]) == "الكهرباء + المياه"
    g = {"baskets": {"a": [1], "b": [1], "c": [1], "d": [1], "e": [1], "f": [1]}, "groups": [["b", "zz"], ["a"]]}
    assert groups(g) == [["b"], ["a"], ["c", "d", "e", "f"]]


def test_real_config_lists_use_only_their_themes_words():
    country = yaml.safe_load((settings.CONFIG_DIR / "countries" / "libya.yaml").read_text(encoding="utf-8"))
    themes = yaml.safe_load((settings.CONFIG_DIR / "themes.yaml").read_text(encoding="utf-8"))["themes"]
    g = config(country)
    words = {t["slug"]: t.get("ar_terms", []) for t in themes}
    assert g and check_baskets(g, words) == []
    assert all(w in g["glosses"] for terms in g["baskets"].values() for w in terms + [g["anchor"]])
    assert all(len(grp) <= 4 for grp in groups(g))  # plus the anchor: five items per request at most
    bad = {**g, "baskets": {"health": ["علاج"], "nope": ["x"]}}
    assert len(check_baskets(bad, words)) == 2


def test_plan_daily_window_never_exceeds_269_days():
    g = {"anchor": "مطعم", "baskets": {"economy": ["الدينار"], "governance": ["مجلس النواب"]},
         "groups": [["economy"], ["governance"]]}
    jobs = plan(g, weekly=True, daily=400, today=date(2026, 10, 16))
    assert [j["resolution"] for j in jobs] == ["week", "week", "day", "day"]
    a, b = jobs[2]["time"].split()
    assert (date.fromisoformat(b) - date.fromisoformat(a)).days + 1 == DAILY_MAX_DAYS


def _client(responses, **kw):
    calls, sleeps = [], []
    it = iter(responses)

    def handler(request):
        calls.append(str(request.url))
        return next(it)
    c = Client(transport=httpx.MockTransport(handler), sleep=sleeps.append, **kw)
    return c, calls, sleeps


def test_client_backs_off_once_then_stops_at_the_second_429():
    ok = httpx.Response(200, text="ok")
    c, calls, sleeps = _client([httpx.Response(429), ok, httpx.Response(429)], gap=1)
    assert c.gap == 10  # never closer than 10 s
    assert c.get("a", "https://trends.google.com/x") == "ok"
    assert 60 in sleeps and len(calls) == 2
    with pytest.raises(Stop):
        c.get("b", "https://trends.google.com/y")
    assert c.n429 == 2 and len(calls) == 3


def test_client_respects_the_request_budget_and_strips_googles_prefix():
    body = ")]}',\n{\"default\": {\"timelineData\": []}}"
    c, calls, _ = _client([httpx.Response(200, text=body)] * 3, max_requests=2)
    assert Client.body(c.get("a", "https://trends.google.com/x")) == {"default": {"timelineData": []}}
    c.get("b", "https://trends.google.com/x")
    with pytest.raises(Stop):
        c.get("c", "https://trends.google.com/x")
    assert len(calls) == 2
    assert c.http.headers["User-Agent"] == settings.USER_AGENT
