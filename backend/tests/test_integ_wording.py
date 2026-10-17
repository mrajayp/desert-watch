"""Wording guards after the 2026-10-16 integration: the help page and the UI say what the merged code does,
in plain words (findings W1-W5, W7, ui m1/m2)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MD = (ROOT / "backend" / "app" / "content" / "how_the_numbers_work.md").read_text(encoding="utf-8")
SRC = ROOT / "frontend" / "src"


def _src(rel: str) -> str:
    return (SRC / rel).read_text(encoding="utf-8")


def _schedule(prefix: str) -> str:
    return next(line for line in MD.splitlines() if line.startswith(f"- {prefix}:"))


def test_md_owner_voice():
    assert ";" not in MD and chr(0x2014) not in MD  # no em dash


def test_md_schedule_matches_jobs():
    # W2: one list per line. W3: the six-hourly job reads Facebook links.
    assert _schedule("Hourly") == ("- Hourly: outlet feeds, YouTube channels, Google Alerts and the theme model on new "
                                   "articles, then scores and the network for the last 12 weeks.")
    jobs = (ROOT / "backend" / "app" / "jobs.py").read_text(encoding="utf-8")
    six_hourly = jobs.split("def six_hourly")[1].split("@_locked")[0]
    assert 'collect("fb_url")' in six_hourly
    assert "Facebook link readings" in _schedule("Every six hours")
    for prefix in ("Hourly", "Every six hours", "Nightly"):
        assert sum(line.startswith(f"- {prefix}:") for line in MD.splitlines()) == 1


def test_md_any_lens():
    # W4: every lens counts the same outlets, and the Trends line is described for any lens
    assert "every gap score allow for this" in MD and "audience gap allow" not in MD
    assert "Where the lens has no need data for a theme" in MD
    assert "no Wikipedia articles linked to it, or we are still building" not in MD


def test_md_queue_without_model():
    assert "When a model is live it also picks the ones whose score sits closest" in MD


def test_theme_reasons_plain_words():
    # wrapped for translation since 2026-10-17 (t(), N_(), tn()); the English words are unchanged
    s = _src("components/ThemeLabels.jsx")
    assert "snippet: N_('summary')" in s and "'{n} words'" in s and "terms'" not in s
    assert "t('found by a search')" in s and "text = t('word list')" in s
    assert not re.search(r"return t?\(?'search'|text = t?\(?'rule'", s)


def test_outlet_reach_unranked():
    s = _src("components/OutletReach.jsx")
    assert "Not in the Tranco list of the busiest websites, as of {date}." in s
    assert ": 'none'" not in s


def test_admin_and_contribute_wording():
    assert "rule-tagged" not in _src("pages/Admin.jsx")
    c = _src("pages/Contribute.jsx")
    assert "least sure" not in c
    assert "The queue shows articles the classifier or the word lists may have got wrong." in c


def test_gap_panel_expected_and_rounding():
    s = _src("components/GapPanel.jsx")
    assert "import { about } from '../charts/trendText'" in s
    assert "meta.lenses.find((l) => l.key === filters.lens)" in s
    assert "against {expected} expected." in s and "against {expected} usual." in s and "expected: about(b.expected_4w)" in s
    assert "fmt(b.expected_4w)" not in s and "minimum need" not in s
