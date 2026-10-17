"""Google Alerts: generate the alert query list from config, and keep it in sync with
the alert_feed table. Alerts are created by a person in a Google account with
"Deliver to: RSS feed"; the feed URLs are pasted back into the admin page."""
import re

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import settings
from .models import AlertFeed, Country, Region, Theme
from .i18n import N_, tr

AR = re.compile("[؀-ۿ]")
MAX_THEME_TERMS = 8
MAX_ALIASES = 3

SETTINGS = {   # Google Alerts' own option names; the admin page shows them in the interface language
    N_("How often"): N_("As-it-happens"),
    N_("Sources"): N_("Automatic"),
    N_("Language"): N_("Arabic for (AR) alerts, English for (EN) alerts"),
    N_("Region"): N_("Any region"),
    N_("How many"): N_("All results"),
    N_("Deliver to"): N_("RSS feed"),
}


def _q(term: str) -> str:
    return f'"{term}"' if " " in term or AR.search(term) else term


def _or(terms: list[str]) -> str:
    terms = [_q(t) for t in terms]
    return terms[0] if len(terms) == 1 else "(" + " OR ".join(terms) + ")"


def build_specs(s: Session, country: Country) -> list[dict]:
    cfg = yaml.safe_load(open(settings.CONFIG_DIR / "countries" / country.config.get("config_file", f"{country.name_en.lower()}.yaml"), encoding="utf-8"))
    regions = {r.slug: r for r in s.scalars(select(Region).where(Region.country_id == country.id))}
    themes = {t.slug: t for t in s.scalars(select(Theme).where(Theme.active.is_(True)))}
    name_en, name_ar = country.name_en, country.name_ar
    specs = []
    # 1. districts: one alert per district per language, tagged to that district
    for d in cfg["districts"]:
        aliases = [d["name_en"], *d.get("aliases", [])]
        en = list(dict.fromkeys(a for a in aliases if not AR.search(a)))[:MAX_ALIASES]
        ar = list(dict.fromkeys([d["name_ar"], *[a for a in aliases if AR.search(a)]]))[:MAX_ALIASES]
        specs.append({"key": f"district:{d['slug']}:en", "lang": "en", "region": d["slug"], "theme": None,
                      "label": f"{d['name_en']} (EN)", "query": f"{_or(en)} {name_en}"})
        specs.append({"key": f"district:{d['slug']}:ar", "lang": "ar", "region": d["slug"], "theme": None,
                      "label": f"{d['name_en']} (AR)", "query": f"{_or(ar)} {name_ar}"})
    # 2. themes: national, one alert per theme per language
    for slug, t in themes.items():
        if t.en_terms:
            specs.append({"key": f"theme:{slug}:en", "lang": "en", "region": None, "theme": slug,
                          "label": f"{t.name_en} (EN)", "query": f"{name_en} {_or(t.en_terms[:MAX_THEME_TERMS])}"})
        if t.ar_terms:
            specs.append({"key": f"theme:{slug}:ar", "lang": "ar", "region": None, "theme": slug,
                          "label": f"{t.name_en} (AR)", "query": f"{name_ar} {_or(t.ar_terms[:MAX_THEME_TERMS])}"})
    # 3. hand-written gap-targeted alerts
    for e in cfg.get("extra_alerts", []):
        specs.append({"key": f"extra:{e['key']}:{e['lang']}", "lang": e["lang"], "region": e.get("region"),
                      "theme": e.get("theme"), "label": e["label"], "query": e["query"]})
    for sp in specs:
        sp["region_id"] = regions[sp["region"]].id if sp.get("region") in regions else None
        sp["theme_id"] = themes[sp["theme"]].id if sp.get("theme") in themes else None
    return specs


def sync_specs(s: Session) -> int:
    """Create/refresh alert_feed rows from the generated specs. Feed URLs are kept."""
    n = 0
    for c in s.scalars(select(Country)):
        for sp in build_specs(s, c):
            row = s.scalar(select(AlertFeed).where(AlertFeed.key == sp["key"]))
            if not row:
                row = AlertFeed(country_id=c.id, key=sp["key"])
                s.add(row)
                n += 1
            row.label, row.query, row.lang = sp["label"], sp["query"], sp["lang"]
            row.region_id, row.theme_id = sp["region_id"], sp["theme_id"]
    s.commit()
    return n


FEED_RE = re.compile(r"^https://www\.google\.[a-z.]+/alerts/feeds/\d+/\d+$")


def attach_feeds(s: Session, text: str) -> dict:
    """Lines of '<key> <feed url>' (tab, comma or space separated). Returns counts and problems."""
    ok, problems = 0, []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = re.split(r"[\s,;]+", line)
        if len(parts) < 2:
            problems.append(tr("{line}: expected '<key> <feed url>'", line=line[:60]))
            continue
        key, url = parts[0], parts[-1]
        row = s.scalar(select(AlertFeed).where(AlertFeed.key == key))
        if not row:
            problems.append(tr("{key}: unknown alert key", key=key))
            continue
        if not FEED_RE.match(url):
            problems.append(tr("{key}: not a Google Alerts feed URL", key=key))
            continue
        row.feed_url, row.active = url, True
        ok += 1
    s.commit()
    return {"attached": ok, "problems": problems}


def write_list(s: Session, out_dir) -> tuple[str, str]:
    """Write the alert list as Markdown (to read) and CSV (key, label, query) for setup."""
    import csv
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = s.scalars(select(AlertFeed).order_by(AlertFeed.key)).all()
    md = ["# Google Alerts to create", "",
          "Create each alert at https://www.google.com/alerts → *Show options*, with these settings:", ""]
    md += [f"- **{k}:** {v}" for k, v in SETTINGS.items()]
    md += ["", "Then copy each alert's RSS feed URL (the RSS icon next to the alert) and paste lines of",
           "`<key> <feed url>` into **Admin → Google Alerts**. Alerts only collect from the day they are created.", ""]
    groups = {"district": "Districts (tag results to the district)", "theme": "Themes (national)",
              "extra": "Gap-targeted (south, minorities, recovery)"}
    for prefix, title in groups.items():
        md += [f"## {title}", "", "| Key | Label | Query (paste exactly) |", "|---|---|---|"]
        for r in rows:
            if r.key.startswith(prefix + ":"):
                md.append(f"| `{r.key}` | {r.label} | `{r.query}` |")
        md.append("")
    md_path = out_dir / "google_alerts.md"
    md_path.write_text("\n".join(md), encoding="utf-8")
    csv_path = out_dir / "google_alerts.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["key", "label", "language", "query", "feed_url"])
        for r in rows:
            w.writerow([r.key, r.label, r.lang, r.query, r.feed_url or ""])
    return str(md_path), str(csv_path)
