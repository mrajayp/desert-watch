from datetime import date

import httpx
from sqlalchemy import select

from app.collectors import fxrate
from app.models import Country, Indicator
from tests.conftest import login

# made-up posts in Al-Mashhad's 2026 template (not their text)
CLOSE = {"id": 1, "date": "2026-10-16T00:30:00", "link": "https://almashhadlibya.com/p/1",
         "title": {"rendered": "ارتفاع جديد في ختام السوق الموازي 15 أكتوبر 2026"},
         "content": {"rendered": "<p>وأغلق الدولار في طرابلس عند 10.19 دينار</p><p>صكوك مصرف الوحدة: 10.34 دينار</p>"
                                 "<p>وسجل اليورو 11.36 دينار</p>"}}
EARLIER = {"id": 2, "date": "2026-10-15T00:40:00", "link": "https://almashhadlibya.com/p/2",
           "title": {"rendered": "تراجع طفيف في ختام السوق الموازي 14 أكتوبر 2026"},
           "content": {"rendered": "<p>وأغلق الدولار في طرابلس عند 10.03 دينار</p><p>وسجل اليورو 11.20 دينار</p>"}}
NOT_A_CLOSE = {"id": 3, "date": "2026-10-15T12:00:00", "link": "https://almashhadlibya.com/p/3",
               "title": {"rendered": "مصرف ليبيا المركزي يعلن أسعار الصرف الرسمية"},
               "content": {"rendered": "<p>سعر الدولار 6.42 دينار</p>"}}
CBL_HTML = """<table id="currency-table"><tbody>
<tr><td>2026-10-15</td><td>الدولار الأمريكي</td><td>1</td><td>6.4242</td><td>6.4403</td><td>6.4081</td></tr>
<tr><td>2026-10-15</td><td>اليورو</td><td>1</td><td>7.2002</td><td>7.2182</td><td>7.1822</td></tr>
<tr><td>2026-10-14</td><td>الدولار الأمريكي</td><td>1</td><td>6.4200</td><td>6.4361</td><td>6.4039</td></tr>
</tbody></table>"""


def _client(posts, cbl=CBL_HTML, seen=None, blocked=False):
    def handler(request):
        if seen is not None:
            seen.append((request.method, request.url.host, dict(request.url.params), request.content))
        if request.url.host == "cbl.gov.ly":
            return httpx.Response(200, text=cbl)
        if blocked and request.url.host == "almashhadlibya.com":
            return httpx.Response(403, text="<html>Attention Required! | Cloudflare</html>", headers={"content-type": "text/html"})
        if int(request.url.params.get("page", "1")) > 1:
            return httpx.Response(400, json={"code": "rest_post_invalid_page_number"})
        return httpx.Response(200, json=posts, headers={"X-WP-TotalPages": "1"})
    return httpx.Client(transport=httpx.MockTransport(handler))


def _values(db):
    c = db.scalar(select(Country))
    return {(i.key, i.day): i.value for i in db.scalars(select(Indicator).where(Indicator.country_id == c.id))}


def test_parallel_and_official_rates_are_stored_per_day(db):
    seen = []
    with _client([CLOSE, EARLIER, NOT_A_CLOSE], seen=seen) as cl:
        res = fxrate.run(db, client=cl)
    assert not res["errors"]
    v = _values(db)
    assert v[("usd_lyd_parallel", date(2026, 10, 15))] == 10.19 and v[("usd_lyd_parallel", date(2026, 10, 14))] == 10.03
    assert v[("usd_lyd_parallel_cheque", date(2026, 10, 15))] == 10.34 and v[("eur_lyd_parallel", date(2026, 10, 15))] == 11.36
    assert v[("usd_lyd_official", date(2026, 10, 15))] == 6.4242 and v[("eur_lyd_official", date(2026, 10, 15))] == 7.2002
    assert not any(k[0] == "usd_lyd_parallel" and val == 6.42 for k, val in v.items())   # the official-rate story is not a close
    # one request for the last few days of the currency category
    wp = [p for m, h, p, _ in seen if h == "almashhadlibya.com"]
    assert len(wp) == 1 and wp[0]["categories"] == "8" and "after" in wp[0] and res["source"] == "almashhad"


def test_cloudflare_challenge_falls_back_to_the_mirror(db):
    seen = []
    with _client([CLOSE], seen=seen, blocked=True) as cl:
        res = fxrate.run(db, client=cl)
    assert res["source"] == "libyaakhbar" and not res["errors"]
    assert _values(db)[("usd_lyd_parallel", date(2026, 10, 15))] == 10.19
    assert any(h == "www.libyaakhbar.com" and p.get("tags") == "98" for _, h, p, _ in seen)


def test_rerun_replaces_and_history_uses_the_banks_own_date_filter(db):
    with _client([CLOSE]) as cl:
        fxrate.run(db, client=cl)
    fixed = dict(CLOSE, content={"rendered": "<p>وأغلق الدولار في طرابلس عند 10.21 دينار</p>"})
    seen = []
    with _client([fixed], seen=seen) as cl:
        fxrate.run(db, client=cl, history=True, cbl_since=date(2023, 11, 1))
    assert _values(db)[("usd_lyd_parallel", date(2026, 10, 15))] == 10.21
    assert db.query(Indicator).filter(Indicator.key == "usd_lyd_parallel").count() == 1
    # history: the closing-post search, and the bank's own date filter one year at a time
    assert any(h == "almashhadlibya.com" and p.get("search") == "ختام السوق الموازي" for _, h, p, _ in seen)
    posts = [body for m, h, _, body in seen if h == "cbl.gov.ly" and m == "POST"]
    assert len(posts) == date.today().year - 2023 + 1 and b"pub_date=2023-11-01+-+2023-12-31" in posts[0]


def test_api_draws_dollar_lines_on_one_chart(client, users, db):
    with _client([CLOSE, EARLIER]) as cl:
        fxrate.run(db, client=cl)
    login(client, "j@example.org", "journo-password-1")
    r = client.get("/api/indicators", params={"days": 1500, "theme": "economy"}).json()
    usd = [i for i in r["indicators"] if i.get("chart") == "usd"]
    assert {i["key"] for i in usd} == {"usd_lyd_parallel", "usd_lyd_parallel_cheque", "usd_lyd_official"}
    assert r["charts"]["usd"] == "One US dollar in Libyan dinars" and all(i["unit"] == "dinars" for i in usd)


def test_archive_fills_only_days_the_daily_sources_do_not_have(db, tmp_path):
    with _client([CLOSE]) as cl:
        fxrate.run(db, client=cl)                       # 2026-10-15 parallel 10.19 from the daily source
    f = tmp_path / "lo.jsonl"
    f.write_text("\n".join([
        '{"snapshot": "20190716", "rates": [{"market": "parallel", "currency": "USD", "sell": 4.51, "updated": "2019-07-15"},'
        ' {"market": "official", "currency": "USD", "sell": 1.3991, "updated": "2019-07-15"}]}',
        '{"snapshot": "20190720", "rates": [{"market": "parallel", "currency": "USD", "sell": 4.51, "updated": "2019-07-15"}]}',
        '{"snapshot": "20261016", "rates": [{"market": "parallel", "currency": "USD", "sell": 9.99, "updated": "2026-10-15"}]}',
    ]), encoding="utf-8")
    res = fxrate.import_archive(db, str(f))
    v = _values(db)
    assert res["updates"] == 3 and v[("usd_lyd_parallel", date(2019, 7, 15))] == 4.51
    assert v[("usd_lyd_official", date(2019, 7, 15))] == 1.3991       # the pre-2021 official rate is kept
    assert v[("usd_lyd_parallel", date(2026, 10, 15))] == 10.19          # the daily source wins


def test_midday_needs_the_market_name_and_close_beats_the_weekly_summary(db):
    from app import fxparse
    assert fxparse.classify_almashhad("تغيير جديد.. السوق الموازي (الأربعاء 14 أكتوبر 2026)") == "midday"
    assert fxparse.classify_almashhad("تغيير جديد في سعر إيداع البطاقات المصرفية") is None
    weekly = {"id": 9, "date": "2026-10-16T18:00:00", "link": "https://almashhadlibya.com/p/9",
              "title": {"rendered": "حصاد أسبوعي للسوق الموازي"}, "content": {"rendered": "<p>لينهي الأسبوع عند 10.40 دنانير</p>"}}
    rows = {(r[0], r[1]): r[2] for r in fxparse.parse_almashhad_posts([CLOSE, weekly], "best")}
    assert rows[(date(2026, 10, 15), "USD")] == 10.19          # Thursday 15 Oct: the close post wins over the weekly summary
