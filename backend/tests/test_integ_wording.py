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
    assert '("fb_url")' in six_hourly   # collected under its own lock since the per-collector lock (C-R1.2)
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
    assert "import { backfilledNote, gapLabel, lensNeed, verdictSentence, weekEnd, weekRange } from '../charts/trendText'" in s
    assert "meta.lenses.find((l) => l.key === filters.lens)" in s
    # the verdict sentence carries the counts, the interval and the chance; the note under it names the
    # comparison in the one word "expected" (B-R1.5 glossary), and the backfilled note follows when set
    assert "verdictSentence(c, need, red)" in s and "gapLabel(c, red, need)" in s and "backfilledNote(c)" in s
    assert "The expected level is what other topics get for the same need." in s
    assert "The expected level is this theme’s usual level." in s
    assert "The score counts" not in s
    assert "fmt(b.expected_4w)" not in s and "minimum need" not in s and "{expected} usual." not in s


LEGEND = "Red means the shortfall is larger than chance would explain. Among the red gaps on a page, about 1 in 10 will still be chance."
WORDS = ROOT / "frontend" / "src" / "charts" / "trendText.js"


def test_verdict_wording_on_every_surface():
    """A-R2.2: every page builds the verdict from the same words (charts/trendText.js), red only for `short`,
    and the three pages that colour gaps carry the 1-in-10 legend line."""
    words = WORDS.read_text(encoding="utf-8")
    # the sentence table: expected (never usual) in the sentences, the "1 in N" chance, the interval
    for s in ("Fewer articles than expected", "Fewer articles than other topics get for {what}", "Possibly fewer than expected: {counts}. Not enough to be sure.",
              "About as expected: {counts}.", "More articles than expected", "Too few to judge: {counts}, so even none at all could be chance.",
              "A shortfall this size happens by chance about once in {n} such weeks.", "It could easily be chance.",
              ", likely {lo} to {hi} times fewer", ", likely {lo} to {hi} times more",
              "The expected level rests partly on weeks we searched back for, which find fewer articles. We widened the margin to allow for it."):
        assert s in words, s
    assert "than usual" not in words
    for page in ("charts/TrendBars.jsx", "charts/Heatmap.jsx", "pages/ThisWeek.jsx"):
        assert LEGEND in _src(page), page
    # the surfaces render from the verdict, not from the gap threshold
    assert "verdictSentence(c, need, red)" in _src("pages/ThisWeek.jsx") and "verdictOf(c, red) === 'short'" in _src("pages/ThisWeek.jsx")
    assert "verdictSentence(c, need, red)" in _src("charts/Heatmap.jsx")
    assert "verdictSentence(g, needOf(g.lens), red)" in _src("pages/Contribute.jsx")
    assert "gapFill(r, red)" in _src("charts/TrendBars.jsx") and "pillClass(v)" in _src("charts/TrendBars.jsx")
    scales = _src("charts/scales.js")
    assert "if (v === 'short') {" in scales and "if (v === 'possibly_short') return css('gap-1')" in scales
    assert "if (v === 'over') return css('gap-over')" in scales
    # the Trends intro no longer says "clearly short"
    assert "fell short by more than chance would explain" in _src("pages/Trends.jsx") and "fell clearly short" not in _src("pages/Trends.jsx")


def test_md_how_we_decide_a_cell_is_short():
    """The method page has the section, in both languages, and the help page the three glossary terms."""
    assert "## How we decide a cell is short" in MD
    sec = MD.split("## How we decide a cell is short")[1].split("\n## ")[0]
    for s in ("Dispersion", "false-discovery rate at 10%", "Benjamini-Hochberg", "at least 1.5 times", "about 1 in 10 is still chance",
              "likely 1.8 to 3.6 times fewer", "once in N such weeks", "Collection drift widens the margin", "fewer than 8 weeks",
              "wider than 4 times either way", "test_stats_simulation.py"):
        assert s in sec, s
    assert "in six cases" in MD and "1.15 times" not in MD and "flag a gap from about 1.5 times fewer" not in MD
    ar = (ROOT / "backend" / "app" / "content" / "how_the_numbers_work.ar.md").read_text(encoding="utf-8")
    assert "## كيف نقرر أن الخلية أقل من المتوقع" in ar and "بنجاميني-هوكبرغ" in ar and "في ست حالات" in ar
    help_md = (ROOT / "backend" / "app" / "content" / "help.md").read_text(encoding="utf-8")
    help_ar = (ROOT / "backend" / "app" / "content" / "help.ar.md").read_text(encoding="utf-8")
    for anchor in ("{#short}", "{#possibly-fewer}", "{#chance}"):
        assert anchor in help_md and anchor in help_ar, anchor
    assert "about 1 in 10 will still be chance" in help_md and "in six cases" in help_md and "From about 1.5 times fewer it turns red" not in help_md
    assert "في ست حالات" in help_ar
