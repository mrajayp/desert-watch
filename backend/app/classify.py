"""Rule-based theme and place tagging. Pure functions over pre-compiled term lists.

The rules stay as the interpretable baseline even after the learned classifier
switches on (see learning.py).

Title first: a term in the title is enough; a snippet-only match needs two distinct
terms, or a co-occurrence pair inside one snippet segment. Snippets are cleaned at match
time (clean_snippet), so re-tagging fixes old items too."""
import html
import re
from dataclasses import dataclass, field

from .textnorm import normalise, term_variants

COOC_WINDOW = 6  # a co-occurrence pair counts only when its two words are this close (in tokens)


def _compile(terms) -> tuple[frozenset, tuple]:
    """Normalised variants split into single words (set lookup) and phrases (substring search)."""
    vs = {v for t in terms for v in term_variants(t)}
    return frozenset(v for v in vs if " " not in v), tuple(sorted(v for v in vs if " " in v))


def _found(c, n: str, toks: set) -> set:
    single, multi = c
    return (single & toks) | {v for v in multi if f" {v} " in n}


def _positions(toks: list, phrase: str) -> list[int]:
    p = phrase.split()
    if len(p) == 1:
        return [i for i, t in enumerate(toks) if t == p[0]]
    return [i for i in range(len(toks) - len(p) + 1) if toks[i:i + len(p)] == p]


@dataclass
class ThemeRule:
    theme_id: int
    slug: str
    version: int
    include: list[str] = field(default_factory=list)  # normalised phrase variants
    exclude: list[str] = field(default_factory=list)
    cooc: list[list[str]] = field(default_factory=list)  # one word from every group, within COOC_WINDOW tokens
    strict: bool = False
    require_country: bool = False
    term_of: dict = field(default_factory=dict)        # variant -> the term as written in the theme
    mask: list[str] = field(default_factory=list)      # phrases blanked out before matching ("المياه الإقليمية")
    veto: list = field(default_factory=list)           # [(weak variants, context variants)]

    def __post_init__(self):
        self._inc = (frozenset(v for v in self.include if " " not in v), tuple(v for v in self.include if " " in v))
        self._exc = (frozenset(v for v in self.exclude if " " not in v), tuple(v for v in self.exclude if " " in v))
        self._cooc = [(frozenset(v for v in g if " " not in v), tuple(v for v in g if " " in v)) for g in self.cooc]

    @classmethod
    def build(cls, theme_id, slug, version, en_terms, ar_terms, exclude, cooc=None, strict=False, require_country=False,
              veto=None, mask=None):
        term_of: dict = {}
        for t in [*(en_terms or []), *(ar_terms or []), *(t for g in cooc or [] for t in g)]:
            for v in term_variants(t):
                term_of.setdefault(v, t)
        inc = sorted({v for t in [*(en_terms or []), *(ar_terms or [])] for v in term_variants(t)})
        groups = [sorted({v for t in g for v in term_variants(t)}) for g in (cooc or []) if g]
        exc = sorted({v for t in exclude or [] for v in term_variants(t)})
        masks = sorted({v for t in mask or [] for v in term_variants(t)}, key=lambda v: -len(v))
        vetoes = [(frozenset(v for t in r.get("terms", []) for v in term_variants(t)), _compile(r.get("context", [])))
                  for r in veto or [] if r.get("terms") and r.get("context")]
        return cls(theme_id, slug, version, inc, exc, groups, bool(strict), bool(require_country), term_of, masks, vetoes)

    # ---- matching over normalised (space-padded) fields
    def _terms(self, n: str, skip: frozenset) -> list[str]:
        """Distinct theme terms in one field. A term inside a longer hit ("clashes" in "armed
        clashes") is not counted again."""
        toks = n.split()
        found = _found(self._inc, n, set(toks)) - skip
        if not found:
            return []
        covered, terms = set(), set()
        for v in sorted(found, key=lambda v: (-len(v.split()), v)):
            size = len(v.split())
            free = [i for i in _positions(toks, v) if not covered.intersection(range(i, i + size))]
            if free:
                terms.add(self.term_of.get(v, v))
                for i in free:
                    covered.update(range(i, i + size))
        return sorted(terms)

    def _pair(self, n: str) -> str | None:
        """A co-occurrence match: one word from every group within COOC_WINDOW tokens."""
        if not self._cooc:
            return None
        toks = n.split()
        tset = set(toks)
        hits = [_found(g, n, tset) for g in self._cooc]
        if not all(hits):
            return None
        pos = [[(i, v) for v in sorted(h) for i in _positions(toks, v)] for h in hits]
        for i0, v0 in pos[0]:
            picked = [v0]
            for p in pos[1:]:
                near = [(abs(i - i0), v) for i, v in p if abs(i - i0) <= COOC_WINDOW]
                if not near:
                    break
                picked.append(min(near)[1])
            else:
                return "+".join(self.term_of.get(v, v) for v in picked)
        return None

    def _masked(self, n: str) -> str:
        for m in self.mask:
            while f" {m} " in n:
                n = n.replace(f" {m} ", " ")
        return n

    def match(self, title: str, segments: list[str] = ()) -> tuple[str, list[str]] | None:
        """(field, terms) for normalised title + cleaned snippet segments, or None.
        Excludes and veto contexts look at the whole text."""
        full = title + " ".join(segments)
        if _found(self._exc, full, set(full.split())):
            return None
        if self.mask:
            title, segments = self._masked(title), [self._masked(x) for x in segments]
        skip = frozenset()
        if self.veto:
            ftoks = set(full.split())
            skip = frozenset(v for weak, ctx in self.veto if _found(ctx, full, ftoks) for v in weak)
        terms = self._terms(title, skip)
        if terms:
            return "title", terms
        pair = self._pair(title)
        if pair:
            return "title", [pair]
        snip = sorted({t for seg in segments for t in self._terms(seg, skip)})
        if len(snip) >= 2:
            return "snippet", snip
        for seg in segments:
            pair = self._pair(seg)
            if pair:
                return "snippet", [pair]
        return None

    def matches(self, norm_text: str) -> list[str]:
        """Terms matched in one normalised text treated as a title (any single term counts)."""
        m = self.match(norm_text)
        return m[1] if m else []


@dataclass
class PlaceRule:
    region_id: int
    variants: list[str]

    @classmethod
    def build(cls, region_id, aliases):
        return cls(region_id, sorted({v for a in aliases for v in term_variants(a)}))


# ---------------------------------------------------------------- snippets
# Segment breaks inside search snippets: Google's "..." joins, WordPress "[…]", sidebar " · " / " | " lists.
_SEG = re.compile(r"\s*(?:\[…\]|\.\.\.|…|\s·\s|\s\|\s)\s*")
_WP_POST = re.compile(r"\s*(?:The post\s.*?\sappeared first on\s|ظهرت المقالة\s.*?\sأولا?ً?\s*على\s).*$", re.S)
# "Tripoli, March 31, 2026 (LANA) -", "طرابلس 31 مارس 2026 م (وال) -", "طرابلس (المشهد) –"
_DATELINE = re.compile(r"^\s*(?P<pre>[^().\n]{0,80}?)\(\s*[^()]{1,25}?\s*\)\s*"
                       r"(?P<post>[A-Za-z]+\.? \d{1,2},? \d{4}\s*)?(?P<dash>[-–—_ـ:]+)?\s*")
_DATE_END = re.compile(r"(?:19|20)\d{2}\s*(?:م\s*)?[,،]?\s*$")
_STOP = {"that", "with", "from", "this", "have", "were", "will", "their", "after", "about", "said", "which",
         "been", "more", "than", "into", "over", "also", "they", "what", "when", "news", "says", "your", "other",
         "التي", "الذي", "الذين", "خلال", "وذلك", "عليه", "عليها", "اليوم", "واضاف", "اخبار", "الاخبار", "كانت",
         "يكون", "الان", "اكثر", "وقال", "وكان", "بشان", "حيث"}


def split_segments(snippet: str | None) -> list[str]:
    return [x.strip() for x in _SEG.split(snippet or "") if x and x.strip()]


def _content_tokens(text: str) -> set:
    return {w for w in normalise(text).split() if len(w) >= 4 and w not in _STOP}


def strip_dateline(text: str) -> str:
    """Drop a leading news-agency dateline: the place in it is where the agency filed from,
    not what the story is about."""
    m = _DATELINE.match(text)
    if not m:
        return text
    words = len(m["pre"].split())
    if _DATE_END.search(m["pre"]) or (m["post"] and words <= 4) or (m["dash"] and words <= 3):
        return text[m.end():]
    return text


def clean_snippet(source_key: str | None, title: str | None, snippet: str | None) -> str:
    """The part of a stored snippet that may count for themes, places and the relevance guard.
    Decodes HTML entities, drops the WordPress "The post ... appeared first on ..." footer and a
    leading dateline. Google Alerts snippets are keyword excerpts built around the alert's own
    query, so only segments that share two or more words with the title are kept."""
    if not snippet:
        return ""
    sn = html.unescape(html.unescape(snippet))  # some feeds double-encode ("&amp;#8217;")
    sn = strip_dateline(_WP_POST.sub("", sn))
    if source_key == "galerts":
        tt = _content_tokens(title or "")
        sn = " … ".join(x for x in split_segments(sn) if len(tt & _content_tokens(x)) >= 2)
    return sn.strip()


def classify_item(title: str | None, snippet: str | None, rules: list[ThemeRule]) -> dict[int, tuple[str, list[str]]]:
    """theme_id -> (field, terms), title first. `snippet` should already be cleaned (clean_snippet)."""
    nt = normalise(title)
    segs = [x for x in (normalise(seg) for seg in split_segments(snippet)) if x.strip()]
    out = {}
    for r in rules:
        m = r.match(nt, segs)
        if m:
            out[r.theme_id] = m
    return out


def classify_themes(text: str, rules: list[ThemeRule]) -> dict[int, list[str]]:
    """One text treated as a title (any single term counts)."""
    n = normalise(text)
    out = {}
    for r in rules:
        hits = r.matches(n)
        if hits:
            out[r.theme_id] = hits
    return out


def tag_places(text: str, rules: list[PlaceRule]) -> list[int]:
    n = normalise(text)
    return [r.region_id for r in rules if any(f" {v} " in n for v in r.variants)]
