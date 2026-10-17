from datetime import date

import httpx
from sqlalchemy import select

from app.collectors import wikireading
from app.models import Country, Indicator, WikiReading
from tests.conftest import login

D1, D2 = date(2026, 6, 7), date(2026, 6, 8)


def _tsv(rows):
    return "\n".join("\t".join(str(x) for x in r) for r in rows) + "\n"


DAY1 = _tsv([
    ("Libya", "LY", "en.wikipedia", 15580374, "Main_Page", "Q5296", 3078),             # not about Libya: dropped
    ("Libya", "LY", "ar.wikipedia", 10077606, "منصة_حجز_العملة_الأجنبية_للأفراد", "Q138658223", 4466),  # indicator
    ("Libya", "LY", "ar.wikipedia", 37451, "مصرف_ليبيا_المركزي", "Q58234", 390),      # indicator + names Libya
    ("Libya", "LY", "ar.wikipedia", 1001, "درنة", "Q1", 1654),                        # a Libyan place
    ("Libya", "LY", "ar.wikipedia", 1002, "عبد_الغني_الككلي", "Q2", 1892),            # a listed public figure
    ("Libya", "LY", "ar.wikipedia", 1003, "سكس_ليبي", "", 300),                       # blocked even though it names Libya
    ("Libya", "LY", "ar.wikipedia", 1004, "كأس_العالم_2026", "Q3", 140),               # football: dropped
    ("Tunisia", "TN", "ar.wikipedia", 1005, "درنة", "Q1", 500),                       # another country: ignored
])
DAY1_RENAMED = DAY1.replace("منصة_حجز_العملة_الأجنبية_للأفراد", "منصة_حجز_العملة_الأجنبية")


def _client(pages):
    def handler(request):
        day = request.url.path.rsplit("/", 1)[-1].removesuffix(".tsv")
        body = pages.get(day)
        return httpx.Response(200, text=body) if body is not None else httpx.Response(404, text="not found")
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_keeps_libya_pages_and_page_indicators_only(db):
    c = db.scalar(select(Country))
    with _client({D1.isoformat(): DAY1}) as cl:
        res = wikireading.run(db, D1, D2, client=cl)
    assert res["stored"] == 1 and res["not_yet"] == D2.isoformat()       # day 2 not published: stops there
    titles = {r.page_title for r in db.scalars(select(WikiReading).where(WikiReading.day == D1))}
    assert titles == {"منصة_حجز_العملة_الأجنبية_للأفراد", "مصرف_ليبيا_المركزي", "درنة", "عبد_الغني_الككلي"}
    ind = {i.key: i.value for i in db.scalars(select(Indicator).where(Indicator.country_id == c.id, Indicator.day == D1))}
    assert ind == {"wiki_fx_platform": 4466, "wiki_cbl": 390}


def test_renamed_page_keeps_its_indicator_and_absent_days_are_recorded(db):
    c = db.scalar(select(Country))
    day2 = _tsv([("Libya", "LY", "en.wikipedia", 15580374, "Main_Page", "Q5296", 2900)])   # the page fell below the threshold
    with _client({D1.isoformat(): DAY1_RENAMED, D2.isoformat(): day2}) as cl:
        wikireading.run(db, D1, D2, client=cl)
    vals = {(i.key, i.day): i.value for i in db.scalars(select(Indicator).where(Indicator.country_id == c.id))}
    assert vals[("wiki_fx_platform", D1)] == 4466 and vals[("wiki_fx_platform", D2)] is None
    # stored days are skipped, and re-storing a day replaces it
    with _client({}) as cl:
        assert wikireading.run(db, D1, D2, client=cl)["skipped"] == 2
    wikireading.store_day(db, c, D1, [wikireading.parse_line(l) for l in DAY1.splitlines()])
    assert db.query(WikiReading).filter(WikiReading.day == D1).count() == 4


def test_api_shapes(client, users, db):
    with _client({D1.isoformat(): DAY1}) as cl:
        wikireading.run(db, D1, D1, client=cl)
    login(client, "j@example.org", "journo-password-1")
    ind = client.get("/api/indicators", params={"days": 1500, "theme": "economy"}).json()["indicators"]
    fx = next(i for i in ind if i["key"] == "wiki_fx_platform")
    assert fx["rows"] == [{"day": D1.isoformat(), "value": 4466.0}] and fx["unit"] == "views a day" and "90 views" in fx["note"]
    rd = client.get("/api/wiki-reading", params={"days": 400}).json()
    day = next(d for d in rd["days"] if d["day"] == D1.isoformat())
    assert [p["views"] for p in day["pages"]] == sorted((p["views"] for p in day["pages"]), reverse=True)
    assert day["pages"][0]["title"] == "منصة حجز العملة الأجنبية للأفراد" and day["pages"][0]["url"].startswith("https://ar.wikipedia.org/wiki/")
