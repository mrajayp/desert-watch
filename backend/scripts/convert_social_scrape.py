"""Convert the social-media scrape exports (Oct 2023 - Aug 2024; "Social Media scraped data")
into a JSON file for `python -m app.cli import-social-scrape`. Run locally (needs pandas +
openpyxl); the JSON, not the spreadsheets, is what gets loaded. The output stays out of git
(data/ is ignored).

    uv run --with pandas --with openpyxl python scripts/convert_social_scrape.py "<export folder>" data/imports/social_scrape.json

What it does:
  * domains: rebuild full hostnames from article links (the export's "Domain" column is only the
    first hostname label), drop link shorteners / tools / file hosts, keep per-domain totals
  * Facebook pages: classify each page as media / official / political-org, or exclude it
    (sport, commerce, personal pages); totals per page
  * probe each new news domain for a WordPress-style RSS feed
  * labels ("Authentic/Inauthentic" + affiliation) are carried as published, for organisations only
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pandas as pd

SRC, OUT = Path(sys.argv[1]), Path(sys.argv[2])
SOURCE = "Social Media scraped data"
PERIOD = {"from": "2023-10-01", "to": "2024-08-10"}

NOT_OUTLETS = {"bit.ly", "buff.ly", "snip.ly", "bulk.ly", "sticker.ly", "tim.ly", "litt.ly", "view.genial.ly",
               "calendar.time.ly", "wetransfer.com", "lizard.wetransfer.com", "clubhouse.com", "limu.qualtrics.com",
               "kobo-ee.nrc.no", "sooqalmanazil.com", "libyanjobs.kinsta.cloud", "sudancareer.com", "enjoy.ly",
               "gplusss.com", "aucc.ly", "ncb.ly", "lpc.ly", "technical.ly"}

MEDIA = re.compile(r"news|akhbar|akbhar|\btv\b|tv$|channel|press|journal|observer|witness|today|times|post|breaking|"
                   r"gate|media|radio|zoom|alhadath|alahrar|218|alwasat|lana|sada|mag|paper|agency|fassato|msdr|youm|"
                   r"drooj|noon|nabaa|libyapress|tnn|screen\.?shot|alwataniya|alrasmia|alsabq|elkul|network|extralibya|"
                   r"libya24|tripoli\.?24|libyatt|alasema|dernazoom|hunazuwara|modonlibya|amazegh|oya|youm5|alzzawia", re.I)
OFFICIAL = re.compile(r"gov|ministry|municipal|council|centralbank|central\.?bank|noclibya|hnec|embassy|airport|"
                      r"ncdc|gecol|owqaf|lgm\b|lgm\.|ssf\.|rctoc|mof\.|mot\.|LibyanGovernment|HAKOMITNA|PFGuard", re.I)
EXCLUDE = re.compile(r"\bsc\b|scly|club|football|league|olympic|barca|ittihad|ahli|alahly|alnsr|store|shop|perfume|"
                     r"furn|food|pizza|cafe|latte|sweets|fashion|beauty|market|cake|flower|paint|juice|gelato|tourism|"
                     r"mobile|phone|libyana|hospital|school|academy|kids|antique|home|sponge|limu\.edu|utsu|"
                     r"cars?\b|motors?|clinic|salon|dr\.|official$", re.I)


def norm_host(link):
    return urlsplit(str(link)).netloc.lower().removeprefix("www.")


def classify_page(name, source_type):
    n = str(name or "")
    if not n or n == "nan":
        return None
    if EXCLUDE.search(n):
        return None
    if OFFICIAL.search(n):
        return "official"
    if MEDIA.search(n):
        return "media"
    return None  # unknown kind: left out (could be a person or a business)


def probe_rss(host, client):
    for path in ("/feed/", "/rss", "/rss.xml"):
        try:
            r = client.get(f"https://{host}{path}")
            if r.status_code == 200 and (b"<rss" in r.content[:2000] or b"<feed" in r.content[:2000]) and b"<item" in r.content:
                return f"https://{host}{path}"
        except Exception:  # noqa: BLE001
            pass
    return None


def main():
    arts = pd.read_excel(SRC / "Domain Article Page" / "Articles from All Sources (2).xlsx", header=2).dropna(how="all")
    arts["host"] = arts["Link"].map(norm_host)
    domains = []
    with httpx.Client(timeout=15, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (desert-watch import)"}) as c:
        for _, r in arts.iterrows():
            if r["host"] in NOT_OUTLETS or r["host"].endswith(".blogspot.com"):
                continue
            libyan = r["host"].endswith(".ly") or r["host"].endswith(".com.ly") or any(
                k in r["host"] for k in ("libya", "lywitness", "arraedlg", "alwatan-ly", "alsaaa24", "janaly", "lananews",
                                         "almarsad", "addresslibya", "fassato", "msdrnews", "atlibya", "tanasuh",
                                         "afrigatenews", "lj-bc", "alkofiya", "zajel", "almashhadlibya"))
            domains.append({
                "host": r["host"], "name": r["Domain"], "libyan": libyan,
                "articles": int(r["Article Vol"]), "fb_posts": int(r["FB Post Vol"]),
                "fb_engagement": int(r["Total FB Engmnt"]), "tweets": int(r["Tweet Vol"]),
                "source_type": str(r["Affiliation"]).lower(),
                "affiliation": None if pd.isna(r["Category"]) else str(r["Category"]),
                "rss": probe_rss(r["host"], c) if libyan else None,
            })
    pages = pd.read_excel(SRC / "Facebook Engagement Page" / "Authentic Page Details.xlsx", header=2).dropna(how="all")
    fb = []
    for _, r in pages.iterrows():
        kind = classify_page(r["Page Name"], r["Source Type"])
        if not kind:
            continue
        aff = str(r["Affiliation"])
        fb.append({
            "page": str(r["Page Name"]), "link": str(r["Link"]), "kind": kind,
            "source_type": str(r["Source Type"]).lower(),
            "affiliation": None if aff in ("Authentic", "nan") else aff,
            "posts": int(r["Post Volume"]), "interactions": int(r["Interactions"]),
            "comments": int(r["Comments"]), "shares": int(r["Shares"]),
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"source": SOURCE, "period": PERIOD, "domains": domains, "facebook_pages": fb},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"domains kept {len(domains)} (rss found {sum(1 for d in domains if d['rss'])}); "
          f"facebook pages kept {len(fb)} of {len(pages)} "
          f"(media {sum(1 for p in fb if p['kind']=='media')}, official {sum(1 for p in fb if p['kind']=='official')})")


if __name__ == "__main__":
    main()
