"""Libyan dinar exchange-rate parsers (researched and tested 2026-10-17, see docs/research). No network here.

Every public source function returns a list of tuples

    (date: datetime.date, currency: str, value: float, source_url: str)

value = Libyan dinars per ONE unit of the foreign currency.

Currency codes
    USD      cash US dollar (parallel sources: Tripoli / Al-Mushir cash close; CBL: official average)
    USD_CHQ  parallel-market dollar bought with a bank cheque / transfer ("الصكوك"), Wahda bank, Tripoli
    EUR GBP TRY EGP TND JOD and the rest of the CBL list: ISO 4217

Sources (market is implied by the function, not by the code):
    parse_almashhad_posts   PARALLEL  almashhadlibya.com WP REST (category 8) or its libyaakhbar.com mirror (tag 98)
    parse_cbl_html          OFFICIAL  cbl.gov.ly/currency-exchange-rates/ (GET = latest day; POST pub_date range = history)
    parse_eanlibya_html     PARALLEL  eanlibya.com/exchangerate/ (single hand-updated snapshot)
    parse_pricesly_json     PARALLEL  api.prices.ly/api/prices/today (single automated snapshot, often wrong; cross-check only)
    parse_generic_post      PARALLEL  any outlet's rate story (lywitness weekly roundups etc.), weak fallback
    parse_headline          PARALLEL  Desert Watch corpus titles/snippets, weakest fallback / audit

Nothing here keeps personal data: no author names, no WhatsApp/Facebook ids, no comments. Only
(date, currency, value, url) leaves a parser. prices.ly's `message_id` (a WhatsApp group id plus the
sender's @lid) is dropped on purpose.

No network code in this module: fetching stays in the collector (polite_get).
"""
from __future__ import annotations

import datetime as dt
import html as _html
import re
from typing import Iterable

Row = tuple  # (date, currency, value, source_url)

TRIPOLI = dt.timezone(dt.timedelta(hours=2))  # Libya is UTC+2 all year (no DST)

# ---------------------------------------------------------------- text helpers

_DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬', '01234567890123456789.,')


def norm(text: str) -> str:
    """Arabic-Indic/Persian digits -> ASCII, Arabic decimal mark -> '.', drop tatweel, collapse spaces."""
    t = (text or '').translate(_DIGITS).replace('ـ', '')  # tatweel: "خـتام" -> "ختام"
    t = t.replace('\xa0', ' ').replace('&nbsp', ' ')
    return re.sub(r'\s+', ' ', t).strip()


def html_to_text(fragment: str) -> str:
    """Strip tags (block boundaries become ' | '), unescape entities, normalise digits."""
    t = re.sub(r'<(script|style)\b.*?</\1>', ' ', fragment or '', flags=re.S | re.I)
    t = re.sub(r'</?(p|div|li|tr|td|th|h\d|br|ul|ol|table|tbody|thead)\b[^>]*>', ' | ', t, flags=re.I)
    t = re.sub(r'<[^>]+>', ' ', t)
    t = _html.unescape(t)
    t = norm(t)
    return re.sub(r'(\s*\|\s*)+', ' | ', t)


def to_float(s: str) -> float | None:
    s = norm(s).replace(',', '.')
    if s.count('.') > 1 or s.endswith('.') or s.startswith('.'):
        return None  # e.g. "9." in a broken template
    try:
        return float(s)
    except ValueError:
        return None


NUM = r'(\d{1,2}(?:[.,]\d{1,4})?)'

AR_MONTHS = {
    'يناير': 1, 'فبراير': 2, 'مارس': 3, 'ابريل': 4, 'أبريل': 4, 'إبريل': 4, 'مايو': 5, 'يونيو': 6, 'يونيه': 6,
    'يوليو': 7, 'يوليه': 7, 'اغسطس': 8, 'أغسطس': 8, 'أغسطس': 8, 'سبتمبر': 9, 'اكتوبر': 10, 'أكتوبر': 10,
    'نوفمبر': 11, 'ديسمبر': 12,
    # Libyan (Jamahiriya-era) month names still appear in some archives
    'أي النار': 1, 'النوار': 2, 'الربيع': 3, 'الطير': 4, 'الماء': 5, 'الصيف': 6, 'ناصر': 7,
    'هانيبال': 8, 'الفاتح': 9, 'التمور': 10, 'الحرث': 11, 'الكانون': 12,
}
_MONTH_RE = '|'.join(sorted(map(re.escape, AR_MONTHS), key=len, reverse=True))
DATE_RE = re.compile(r'(\d{1,2})\s*(' + _MONTH_RE + r')\s*,?\s*(\d{4})')

AR_WEEKDAYS = {'الاثنين': 0, 'الإثنين': 0, 'الثلاثاء': 1, 'الأربعاء': 2, 'الاربعاء': 2, 'الخميس': 3,
               'الجمعة': 4, 'السبت': 5, 'الأحد': 6, 'الاحد': 6}
_WD_RE = '|'.join(sorted(map(re.escape, AR_WEEKDAYS), key=len, reverse=True))


def parse_ar_date(text: str) -> dt.date | None:
    """First 'd <Arabic month> yyyy' in text (also '17 ديسمبر2024', '15 أكتوبر, 2026')."""
    m = DATE_RE.search(norm(text))
    if not m:
        return None
    try:
        return dt.date(int(m.group(3)), AR_MONTHS[m.group(2)], int(m.group(1)))
    except ValueError:
        return None


# plausible LYD-per-unit bands (wide on purpose; they only catch template/parse garbage)
BANDS = {'USD': (3, 30), 'USD_CHQ': (3, 30), 'EUR': (3, 35), 'GBP': (4, 40), 'TRY': (0.03, 1.5),
         'EGP': (0.03, 1.5), 'TND': (1, 8), 'JOD': (4, 40)}


def plausible(cur: str, v: float | None) -> bool:
    if v is None:
        return False
    lo, hi = BANDS.get(cur, (0.0001, 1000))
    return lo <= v <= hi


def _ok(rows: Iterable[Row]) -> list[Row]:
    return [r for r in rows if plausible(r[1], r[2])]


def _local(ts: str) -> dt.datetime:
    """WP REST 'date' is site-local (Tripoli) and naive: '2026-10-13T00:53:44'."""
    return dt.datetime.fromisoformat(ts[:19])


# ---------------------------------------------------------------- 1. Al-Mashhad (primary parallel)

# USD Tripoli cash close; ordered newest template first (the template drifted 2024 -> 2026)
_CLOSE_USD = [
    re.compile(r'أغلق\s+(?:الدولار\s+)?في\s+(?:العاصمة\s+)?طرابلس\s+عند\s+(?:مستوى\s+)?' + NUM),        # 2025-11..
    re.compile(NUM + r'\s*(?:دينار|دنانير)\s+في\s+(?:تداولات\s+)?(?:الغرف\s+ب|غرف\s+)?(?:مدينة\s+طرابلس|أسواق\s+المشير)'),  # 2024-12..2025, 2026-05
    re.compile(r'تداولات\s+مدينة\s+طرابلس\s+' + NUM),                                          # 2025-10 "سعره في تداولات مدينة طرابلس 7.545"
    re.compile(r'طرابلس\s+مستوى\s+' + NUM + r'\s*دينار'),                                        # 2026-01 "سجلت العاصمة طرابلس مستوى 8.655"
    re.compile(r'(?:ليغلق|وأغلق|أغلق)[^|]{0,60}?ختام\s+تعاملات\s+اليوم[^0-9|]{0,40}' + NUM),      # 2024-02
    re.compile(r'سجل\s+ل?\s*' + NUM + r'\s*دينار\s+في\s+ختام'),                                    # 2023-12
    re.compile(r'في\s+(?:العاصمة\s+)?طرابلس\s+(?:نحو|عند\s+مستوى|عند|مستوى)\s+' + NUM),             # 2025-11 "في طرابلس نحو 7.54"
    re.compile(r'صرف\s+الدولار[^|]{0,80}?ختام\s+التعاملات[^|]{0,80}?إلى\s+' + NUM + r'\s*دينار'),     # 2023-11
    re.compile(r'أغلق\s+في\s+تداولات\s+(?:غرف\s+)?طرابلس\s+عند\s+' + NUM),                          # 2026-01 variant
    re.compile(r'(?:ليسجل|وصل\s+ل|وبلغت\s+قيمته|بلغت\s+قيمته)\s*' + NUM + r'\s*دينار'),               # 2023-11..2024-02
    re.compile(r'الدولار[^|]{0,80}?طرابلس[^0-9|]{0,25}' + NUM + r'\s*دينار'),                       # loose
    re.compile(r'(?:الدولار\s+الأمريكي\s+)?كاش\s+(?:نحو\s+)?' + NUM),                                 # 2026-02 "كاش نحو 9.97"
    re.compile(r'الدولار(?:(?!صك|شيك|حوال)[^|]){0,200}?' + NUM + r'\s*دينار'),                       # last resort, lead paragraph only
]
_MIDDAY_USD = [
    re.compile(r'في\s+طرابلس\s+[^0-9|]{0,40}?' + NUM + r'\s*دينار'),                       # "سجل في طرابلس ارتفاعا جديدا إلى 10.22 دينار"
]
_EUR = re.compile(r'اليورو[^0-9|]{0,90}?' + NUM + r'\s*(?:دينار|د\.ل)')
_GBP = re.compile(r'(?:الجنيه\s+الإسترليني|الجنيه\s+الاسترليني|الإسترليني|الاسترليني|الباوند)[^0-9|]{0,90}?' + NUM + r'\s*(?:دينار|د\.ل)')
_CHQ = re.compile(r'(?:(?:صكوك\s+)?مصرف\s+الوحدة\s*:?|بشيك\s+الوحدة)\s*' + NUM + r'\s*دينار')
_SIMPLE = {'TRY': r'الليرة\s+التركية\s*:\s*', 'EGP': r'الجنيه\s+المصري\s*:\s*',
           'TND': r'الدينار\s+التونسي\s*:\s*', 'JOD': r'الدينار\s+الأردني\s*:\s*'}


def _first(patterns, text):
    for p in patterns:
        m = p.search(text)
        if m:
            v = to_float(m.group(1))
            if v is not None:
                return v
    return None


def _post_market_date(title: str, text: str, published: dt.datetime) -> dt.date:
    """Trading day a post describes: date in the title, else in the body, else the publish date
    (posts published before 06:00 Tripoli time describe the previous evening's close)."""
    d = parse_ar_date(title) or parse_ar_date(text[:400])
    if d and abs((published.date() - d).days) <= 3:
        return d
    return (published - dt.timedelta(hours=6)).date()


_WEEKLY_USD = [
    re.compile(r'(?:لينهي|ينهي)\s+الأسبوع\s+عند\s*\|?\s*' + NUM),
    re.compile(r'ختام\s+تعاملات\s+(?:يوم\s+)?الخميس[^|]{0,40}?عند\s+' + NUM + r'\s*دينار'),
]


_CLOSE_TITLE = re.compile(r'ختام\s+(?:(?:تعاملات|تداولات|التداولات)\s+)?(?:ال)?سوق\s+(?:ال)?موازي|ختام\s+(?:تعاملات|تداولات)\s+(?:ال)?سوق')


def classify_almashhad(title: str) -> str | None:
    t = norm(_html.unescape(title))
    if _CLOSE_TITLE.search(t):
        return 'close'
    if 'أسبوعي' in t or 'أسبوع' in t:
        return 'weekly'
    # midday posts name the parallel market (a "تغيير جديد" post about bank-card deposits is not one)
    if (t.startswith('تغيير جديد') or t.startswith('قفزة جديدة..')) and 'السوق الموازي' in t:
        return 'midday'
    return None


def parse_almashhad_post(post: dict) -> tuple[str | None, list[Row]]:
    """One WP REST post dict (id, date, link, title{rendered}, content{rendered})."""
    title = norm(_html.unescape(post['title']['rendered']))
    kind = classify_almashhad(title)
    if not kind:
        return None, []
    text = html_to_text(post['content']['rendered'])
    url = post['link']
    if kind == 'weekly':  # Thursday close from the Friday/Saturday weekly summary
        pub = _local(post['date']).date()
        thu = pub - dt.timedelta(days=(pub.weekday() - 3) % 7 or 7) if pub.weekday() != 3 else pub
        return kind, _ok([(thu, 'USD', _first(_WEEKLY_USD, text), url)])
    day = _post_market_date(title, text, _local(post['date']))
    # the USD quote always precedes the euro paragraph; cutting there stops EUR/GBP figures leaking in
    cut = text.find('اليورو')
    head = text[:cut] if cut > 0 else text
    usd = _first(_CLOSE_USD if kind == 'close' else _MIDDAY_USD + _CLOSE_USD, head)
    rows = [(day, 'USD', usd, url)]
    for cur, pat in (('EUR', _EUR), ('GBP', _GBP), ('USD_CHQ', _CHQ)):
        m = pat.search(text)
        rows.append((day, cur, to_float(m.group(1)) if m else None, url))
    for cur, lead in _SIMPLE.items():
        m = re.search(lead + NUM, text)
        if m:
            rows.append((day, cur, to_float(m.group(1)), url))
    rows = _ok(rows)
    # internal consistency: drop EUR/GBP if the EUR/USD or GBP/USD cross is absurd (template mix-ups)
    u = next((r[2] for r in rows if r[1] == 'USD'), None)
    if u:
        rows = [r for r in rows if not (r[1] == 'EUR' and not 0.95 <= r[2] / u <= 1.35)
                and not (r[1] == 'GBP' and not 1.05 <= r[2] / u <= 1.60)
                and not (r[1] == 'USD_CHQ' and not 0.9 <= r[2] / u <= 1.25)]
    return kind, rows


RANK = {'close': 3, 'weekly': 2, 'midday': 1}
TYPO_TOL = 0.03   # a quote more than 3% from the same day's other quotes is a typo ("10.8" for 10.08)


def parse_almashhad_posts(posts: list[dict], kind: str = 'close') -> list[Row]:
    """Daily rows from Al-Mashhad posts. kind='close' (evening close series), 'midday' (the "تغيير جديد"
    series) or 'best' (close > weekly Thursday close > midday, per day and currency; within a rank the
    latest-published post wins). Free-text stories are never used (they mix cash, cheque and official
    figures). Corrections from the 2026-10-17 check:
    - a close post that repeats a day another close post already gave is dated by its publish time
      minus 6 hours instead (stale dates in titles or bodies overwrote real closes);
    - a dollar quote more than 3% from the median of the same day's other quotes is dropped."""
    best: dict[tuple, tuple] = {}
    quotes: dict[dt.date, list[float]] = {}
    close_days: dict[dt.date, int] = {}
    for p in sorted(posts, key=lambda p: p['date']):
        k, rows = parse_almashhad_post(p)
        if not k or (kind != 'best' and k != kind):
            continue
        if k == 'close' and rows:
            day = rows[0][0]
            if day in close_days and close_days[day] != p['id']:
                moved = (_local(p['date']) - dt.timedelta(hours=6)).date()
                rows = [(moved, *r[1:]) for r in rows]
                day = moved
            close_days.setdefault(day, p['id'])
        for r in rows:
            if r[1] == 'USD':
                quotes.setdefault(r[0], []).append(r[2])
            key = (r[0], r[1])
            if key not in best or RANK[k] >= best[key][0]:
                best[key] = (RANK[k], r)
    out = []
    for (day, cur), (_, r) in best.items():
        others = [q for q in quotes.get(day, []) if q != r[2]]
        if cur == 'USD' and len(others) >= 2:
            mid = sorted(others)[len(others) // 2]
            if abs(r[2] - mid) / mid > TYPO_TOL:
                continue
        out.append(r)
    return sorted(out, key=lambda r: (r[0], r[1]))


# ---------------------------------------------------------------- 2. CBL official

CBL_CODES = {
    'الدولار الأمريكي': 'USD', 'اليورو': 'EUR', 'الجنيه الاسترليني': 'GBP', 'الدولار الكندي': 'CAD',
    'الدولار الاسترالي': 'AUD', 'الفرنك السويسري': 'CHF', 'الكرونر السويدي': 'SEK', 'الكرونر النرويجي': 'NOK',
    'الكرونر الدنمركي': 'DKK', 'الين الياباني': 'JPY', 'الريال السعودي': 'SAR', 'الدرهم الاماراتي': 'AED',
    'الدينار التونسي': 'TND', 'الدينار الجزائري': 'DZD', 'الدرهم المغربي': 'MAD', 'اوقية موريتانية': 'MRU',
    'فرنك افريقي': 'XOF', 'الروبل الروسي': 'RUB', 'الليرة التركية': 'TRY', 'الايوان الصيني': 'CNY',
}
_CBL_ROW = re.compile(r'<tr>\s*(.*?)</tr>', re.S)
_CBL_CELL = re.compile(r'<td[^>]*>(.*?)</td>', re.S)


def parse_cbl_detail(page_html: str, url: str = 'https://cbl.gov.ly/currency-exchange-rates/') -> list[dict]:
    """All rows of the CBL rates table: date, code, units, avg, sell, buy (LYD per ONE unit)."""
    out = []
    i = page_html.find('id="currency-table"')
    body = page_html[i:] if i >= 0 else page_html
    for row in _CBL_ROW.findall(body):
        cells = [html_to_text(c).strip(' |') for c in _CBL_CELL.findall(row)]
        if len(cells) != 6:
            continue
        cells = [re.sub(r'^(التاريخ|العملة|الوحدة|المتوسط|بيع|شراء)\s*:\s*', '', c) for c in cells]
        try:
            day = dt.date.fromisoformat(cells[0][:10])
        except ValueError:
            continue
        name = re.sub(r'\s+', ' ', cells[1])
        code = CBL_CODES.get(name)
        if not code:
            continue
        m = re.search(r'(\d+)', cells[2])
        units = int(m.group(1)) if m else 1
        vals = [to_float(m.group(0)) if (m := re.search(r'\d+(?:[.,]\d+)?', c)) else None for c in cells[3:6]]
        if None in vals:
            continue
        avg, sell, buy = (v / units for v in vals)
        out.append({'date': day, 'code': code, 'units': units, 'avg': avg, 'sell': sell, 'buy': buy, 'url': url})
    return out


def parse_cbl_html(page_html: str, url: str = 'https://cbl.gov.ly/currency-exchange-rates/',
                   codes: Iterable[str] = ('USD', 'EUR', 'GBP', 'TRY', 'TND')) -> list[Row]:
    """Official CBL average (mid) rate per day. Works on the GET page (latest day) and on the
    POST pub_date='YYYY-MM-DD - YYYY-MM-DD' response (history)."""
    want = set(codes) if codes else None
    seen = {}
    for r in parse_cbl_detail(page_html, url):
        if want is None or r['code'] in want:
            seen[(r['date'], r['code'])] = (r['date'], r['code'], round(r['avg'], 4), url)
    return sorted(seen.values())


def parse_cbl_home(page_html: str, url: str = 'https://cbl.gov.ly/') -> list[Row]:
    """Fallback: the home-page widget ('أسعار الصرف ليوم: 15 أكتوبر, 2026' + buy/sell). Returns mid."""
    m = re.search(r'أسعار الصرف ليوم:.*?<span>([^<]+)</span>', page_html, re.S)
    if not m:
        return []
    day = parse_ar_date(m.group(1))
    out = []
    for name, buy, sell in re.findall(r'<h3[^>]*>([^<]+)</h3>.*?شراء</div>\s*<span>\s*([\d.,]+).*?بيع</div>\s*<span>\s*([\d.,]+)',
                                      page_html[m.end():m.end() + 20000], re.S):
        code = CBL_CODES.get(norm(name))
        b, s = to_float(buy), to_float(sell)
        if code and b and s and day:
            out.append((day, code, round((b + s) / 2, 4), url))
    return out


# ---------------------------------------------------------------- 3. eanlibya (fallback parallel)

_EAN_NAMES = {'الدولار': 'USD', 'اليورو': 'EUR', 'الإسترليني': 'GBP', 'الاسترليني': 'GBP',
              'الليرة التركية': 'TRY', 'الدينار التونسي': 'TND', 'الجنيه المصري': 'EGP'}


def eanlibya_stamp(page_html: str) -> tuple[dt.date | None, str | None, bool]:
    """('آخر تحديث: الخميس 14 أكتوبر 2026 - 18:05') -> (trading date, 'HH:MM', weekday_agrees).
    The stamp is typed by hand: on 2026-10-17 it said Thursday 14 Oct (14 Oct was a Wednesday) while
    the numbers were Thursday 15 Oct's. If weekday and date disagree, the weekday wins when it points
    to a day within 3 days of the stated date."""
    m = re.search(r'آخر تحديث:\s*(' + _WD_RE + r')?\s*([^<|]*?\d{4})\s*-?\s*(\d{1,2}:\d{2})?', norm(_html.unescape(page_html)))
    if not m:
        return None, None, False
    day = parse_ar_date(m.group(2))
    if not day:
        return None, m.group(3), False
    wd = AR_WEEKDAYS.get(m.group(1) or '')
    if wd is None or wd == day.weekday():
        return day, m.group(3), wd is not None
    cands = [day + dt.timedelta(days=k) for k in range(-3, 4) if (day + dt.timedelta(days=k)).weekday() == wd]
    return (cands[0] if cands else day), m.group(3), False


def parse_eanlibya_html(page_html: str, url: str = 'https://www.eanlibya.com/exchangerate/') -> list[Row]:
    day, _, _ = eanlibya_stamp(page_html)
    if not day:
        return []
    i = page_html.find('exchange-table')  # first table = parallel market ("السوق الموازي")
    seg = page_html[i:i + 60000] if i >= 0 else page_html
    rows = []
    for name, val in re.findall(r'<td class="column-2">([^<]+)</td>\s*<td class="column-3">(?:<i[^>]*></i>)?\s*([\d.,]+)\s*</td>', seg):
        code = _EAN_NAMES.get(norm(name))
        if code:
            rows.append((day, code, to_float(val), url))
    return _ok(rows)


# ---------------------------------------------------------------- 4. prices.ly (cross-check only)

_PL_FIELDS = {'usd_tripoli': 'USD', 'euro_tripoli': 'EUR', 'usd_checks_wahda_tripoli': 'USD_CHQ'}


def parse_pricesly_json(obj: dict, url: str = 'https://api.prices.ly/api/prices/today',
                        official_cross: float | None = None) -> list[Row]:
    """Latest snapshot only. The feed is parsed automatically from a WhatsApp dealer group; on
    2026-10-16 it reported usd_tripoli 9.27 while every news source had ~10.2 (its EUR/USD cross was
    1.22 against the CBL cross of 1.12). USD is dropped when the parallel EUR/USD cross is more than 5%
    from `official_cross` (CBL EUR avg / USD avg, same day), or outside 0.95-1.20 when no cross is given.
    message_id (a WhatsApp group id plus the sender's @lid: personal identifiers) is never read."""
    data = (obj or {}).get('data') or {}
    ts = data.get('timestamp')
    if obj.get('message') != 'success' or not isinstance(ts, (int, float)):
        return []
    day = dt.datetime.fromtimestamp(ts, TRIPOLI).date()
    rows = _ok([(day, code, float(data[f]), url) for f, code in _PL_FIELDS.items()
                if isinstance(data.get(f), (int, float))])
    u = next((r[2] for r in rows if r[1] == 'USD'), None)
    e = next((r[2] for r in rows if r[1] == 'EUR'), None)
    if u and e:
        x = e / u
        bad = abs(x / official_cross - 1) > 0.05 if official_cross else not 0.95 <= x <= 1.20
        if bad:
            rows = [r for r in rows if r[1] != 'USD']  # the USD field is the one that goes wrong
    return rows


# ---------------------------------------------------------------- 5. generic outlet stories (weak)

NUM_DEC = r'(\d{1,2}[.,]\d{1,4})'  # free text: require decimals ("حاجز 10 دنانير" is a threshold, not a quote)
_SENT_SPLIT = re.compile(r'(?<!\d)[.!؟?](?!\d)|\|')
_PAR_KW = re.compile(r'السوق الموازية|السوق الموازي|الموازي|السوق السوداء|سوق المشير|أسواق المشير')
_USD_IN = re.compile(r'(?:الدولار|دولار)([^|]{0,160}?)' + NUM_DEC + r'(?!\s*%)')
_OFFICIAL_HINT = re.compile(r'رسمي|المركزي|المصرف')
_FORECAST_HINT = re.compile(r'توقع|متوقع|يتوقع|مرتقب|سيصل|قد يصل|قد يهبط|سيهبط|هدف|سيناريو')
_CHEQUE_HINT = re.compile(r'صك|الصكوك|بالصك|المقاصة|الدفتري|حوال')
_NOT_LEVEL = re.compile(r'بزيادة|بارتفاع|بانخفاض|بنسبة|قرش|مليار|مليون|ألف|%|أعلى|اعلى|أدنى|ادنى')


def _last_weekday(on_or_before: dt.date, weekday: int) -> dt.date:
    return on_or_before - dt.timedelta(days=(on_or_before.weekday() - weekday) % 7)


def parse_generic_post(title: str, text: str, published: dt.datetime, url: str) -> list[Row]:
    """Best-effort USD cash rate from a free-text parallel-market story.
    Date rules: explicit date in the sentence > 'أمس <weekday>' (previous such weekday) > 'اليوم <weekday>' >
    'خلال الأسبوع الماضي' (weekly close = last Thursday before publication) > publish date
    (before 06:00 Tripoli -> previous day)."""
    t = norm(title) + ' | ' + norm(text)
    for sent in _SENT_SPLIT.split(t):
        if not _PAR_KW.search(sent):
            continue
        if _OFFICIAL_HINT.search(sent) and not re.search(r'الموازي', sent):
            continue
        if _FORECAST_HINT.search(sent):
            continue
        for m in _USD_IN.finditer(sent):
            gap = m.group(1)
            win = sent[max(0, m.start() - 80): m.end() + 25]
            post = sent[m.end(): m.end() + 25]
            if _CHEQUE_HINT.search(gap) or _NOT_LEVEL.search(gap[-25:]) or _OFFICIAL_HINT.search(gap):
                continue
            if _OFFICIAL_HINT.search(win) and not _PAR_KW.search(win):
                continue  # "... بيانات مصرف ليبيا المركزي ... سعر الدولار ... 6.39" inside a parallel story
            if _CHEQUE_HINT.search(post) or 'رسمي' in post:
                continue  # "الدولار يسجل 6.31 دينار رسمياً" / "10.55 عبر الصكوك"
            v = to_float(m.group(2))
            if not plausible('USD', v):
                continue
            pub = published.date()
            d = parse_ar_date(sent)
            wm = re.search(r'(أمس|اليوم)\s*،?\s*(' + _WD_RE + ')', sent)
            if d and 0 <= (pub - d).days <= 7:
                day = d
            elif wm:
                wd = AR_WEEKDAYS[wm.group(2)]
                day = _last_weekday(pub - dt.timedelta(days=1 if wm.group(1) == 'أمس' else 0), wd)
            elif re.search(r'الأسبوع الماضي|نهاية الأسبوع|ختام الأسبوع', sent):
                day = _last_weekday(pub - dt.timedelta(days=1), 3)
            else:
                day = (published - dt.timedelta(hours=6)).date()
            return [(day, 'USD', v, url)]
    return []


def parse_wp_posts_generic(posts: list[dict]) -> list[Row]:
    out = []
    for p in posts:
        out += parse_generic_post(_html.unescape(p['title']['rendered']), html_to_text(p['content']['rendered']),
                                  _local(p['date']), p['link'])
    return out


# ---------------------------------------------------------------- 6. corpus headlines (audit)

def parse_headline(title: str, snippet: str, published: dt.datetime, url: str) -> list[Row]:
    """Weakest fallback, for items already in the Desert Watch corpus (title + snippet only).
    Needs a parallel-market keyword; skips sentences about the official rate or cheques."""
    t = norm(_html.unescape((title or '') + ' | ' + (snippet or '')))
    if not re.search(r'الموازي|السوداء|المشير', t):
        return []
    return parse_generic_post('', t, published, url)


# ---------------------------------------------------------------- series hygiene (use before storing)

def clean_series(rows: list[Row], official: dict | None = None, window: int = 5, tol: float = 0.12) -> tuple[list[Row], list[Row]]:
    """Split rows into (kept, dropped).
    - parallel USD/EUR at or below the official rate is dropped (the gap has been 15-60% since 2024;
      a value that low is an official figure that leaked into a parallel story);
    - a point more than `tol` (12%) away from the median of its `window` neighbours on each side
      (same currency) is dropped as a parse error. Real one-day moves in this market are < 6%."""
    official = official or {}
    kept, dropped = [], []
    by_cur: dict[str, list[Row]] = {}
    for r in sorted(rows, key=lambda r: (r[1], r[0])):
        by_cur.setdefault(r[1], []).append(r)
    for cur, rs in by_cur.items():
        for i, r in enumerate(rs):
            off = official.get((r[0], cur.replace('_CHQ', '')))
            if off and r[2] <= off * 1.02:
                dropped.append(r); continue
            nb = [x[2] for x in rs[max(0, i - window): i] + rs[i + 1: i + 1 + window]]
            if len(nb) >= 3:
                med = sorted(nb)[len(nb) // 2]
                if abs(r[2] / med - 1) > tol:
                    dropped.append(r); continue
            kept.append(r)
    return sorted(kept), sorted(dropped)
