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


def _distinct_words(terms) -> set:
    """Terms that are not just the plural of another one ("migrants" next to "migrant")."""
    low = {t.lower() for t in terms}
    return {t for t in low if not any(t in (u + "s", u + "es") for u in low)}


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
    # a co-occurrence pair does not fire when one of these words sits within COOC_WINDOW tokens of
    # either half of it ("women killed" next to "shelling": conflict casualties, not violence against women)
    cooc_veto: list[str] = field(default_factory=list)

    def __post_init__(self):
        self._inc = (frozenset(v for v in self.include if " " not in v), tuple(v for v in self.include if " " in v))
        self._exc = (frozenset(v for v in self.exclude if " " not in v), tuple(v for v in self.exclude if " " in v))
        self._cooc = [(frozenset(v for v in g if " " not in v), tuple(v for v in g if " " in v)) for g in self.cooc]
        self._cooc_veto = (frozenset(v for v in self.cooc_veto if " " not in v), tuple(v for v in self.cooc_veto if " " in v))

    @classmethod
    def build(cls, theme_id, slug, version, en_terms, ar_terms, exclude, cooc=None, strict=False, require_country=False,
              veto=None, mask=None, cooc_veto_context=None):
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
        cooc_veto = sorted({v for t in cooc_veto_context or [] for v in term_variants(t)})
        return cls(theme_id, slug, version, inc, exc, groups, bool(strict), bool(require_country), term_of, masks, vetoes,
                   cooc_veto)

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

    def _tainted(self, n: str, toks: list, tset: set) -> set[int]:
        """Token positions within COOC_WINDOW of a pair-veto context word: no half of a pair may sit there."""
        out: set[int] = set()
        for v in _found(self._cooc_veto, n, tset):
            size = len(v.split())
            for i in _positions(toks, v):
                out.update(range(max(0, i - COOC_WINDOW), i + size + COOC_WINDOW))
        return out

    def _pair(self, n: str) -> str | None:
        """A co-occurrence match: one word from every group within COOC_WINDOW tokens, and no
        pair-veto context word (cooc_veto) within COOC_WINDOW of either of them."""
        if not self._cooc:
            return None
        toks = n.split()
        tset = set(toks)
        hits = [_found(g, n, tset) for g in self._cooc]
        if not all(hits):
            return None
        bad = self._tainted(n, toks, tset) if self.cooc_veto else set()
        pos = [[(i, v) for v in sorted(h) for i in _positions(toks, v) if i not in bad] for h in hits]
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
        if len(_distinct_words(snip)) >= 2:
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


def _definite_only(norm_alias: str, variants: list[str]) -> list[str]:
    """For an ambiguous Arabic alias written with the article (الخمس), keep the definite forms only
    (الخمس, بالخمس, والخمس, للخمس ...): the bare word that term_variants also makes (خمس, "five") is the
    common word the alias is confused with. Aliases without the article are left as they are."""
    first, _, rest = norm_alias.partition(" ")
    if not (first.startswith("ال") and len(first) > 3):
        return variants
    base, tail = first[2:], (" " + rest if rest else "")
    indefinite = {p + base + tail for p in ("", "و", "ب", "ل", "ف")}
    return [v for v in variants if v not in indefinite]


@dataclass
class PlaceRule:
    """One region's aliases as normalised variants. An ambiguous alias is also a common word once
    the Arabic article is stripped (الخمس -> خمس "five", الجميل -> جميل) or a place elsewhere
    (Tripoli in Lebanon, البيضاء in Yemen): it tags only when the text also names the country or an
    unambiguous alias of some region (tag_places). negatives: a variant does not count at all when
    one of its context words is in the text (Tripoli next to Lebanon)."""
    region_id: int
    variants: list[str]                                      # unambiguous aliases
    ambiguous: list[str] = field(default_factory=list)       # aliases that need the country or another place beside them
    negatives: dict[str, tuple] = field(default_factory=dict)  # variant -> compiled words that veto it

    @classmethod
    def build(cls, region_id, aliases, ambiguous=(), negatives: dict | None = None):
        """aliases as written; `ambiguous` the subset (as written) that are homonyms; `negatives`
        alias (as written) -> words that veto it. Aliases are compared after normalisation."""
        amb = {normalise(a).strip() for a in ambiguous}
        neg = {normalise(k).strip(): _compile(v) for k, v in (negatives or {}).items() if v}
        plain, weak, vetoes = set(), set(), {}
        for a in aliases:
            key = normalise(a).strip()
            vs = term_variants(a)
            if key in amb:
                vs = _definite_only(key, vs)
            (weak if key in amb else plain).update(vs)
            if key in neg:
                for v in vs:
                    vetoes[v] = neg[key]
        return cls(region_id, sorted(plain - weak), sorted(weak), vetoes)

    def _present(self, variants: list[str], n: str, toks: set) -> bool:
        return any(f" {v} " in n and not (v in self.negatives and _found(self.negatives[v], n, toks)) for v in variants)

    def plain_hit(self, n: str, toks: set) -> bool:
        """An unambiguous alias is in the normalised text (and not vetoed)."""
        return self._present(self.variants, n, toks)

    def weak_hit(self, n: str, toks: set) -> bool:
        """An ambiguous alias is in the normalised text (and not vetoed): counts only when anchored."""
        return self._present(self.ambiguous, n, toks)


# ---------------------------------------------------------------- snippets
# Segment breaks inside search snippets: Google's "..." joins, WordPress "[…]", sidebar " · " / " | " lists.
_SEG = re.compile(r"\s*(?:\[…\]|\.\.\.|…|\s·\s|\s\|\s)\s*")
_WP_POST = re.compile(r"\s*(?:The post\s.*?\sappeared first on\s|ظهرت المقالة\s.*?\sأولا?ً?\s*على\s).*$", re.S)
# "Tripoli, March 31, 2026 (LANA) -", "طرابلس 31 مارس 2026 م (وال) -", "طرابلس (المشهد) –"
_DATELINE = re.compile(r"^\s*(?P<pre>[^().\n]{0,80}?)\(\s*(?P<tag>[^()]{1,25}?)\s*\)\s*"
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
    if _DATE_END.search(m["pre"]) or (m["post"] and words <= 4) or (m["dash"] and words <= 3 and not _acronym(m["pre"], m["tag"])):
        return text[m.end():]
    return text


def _acronym(pre: str, tag: str) -> bool:
    """"Benghazi Medical Centre (BMC) - the hospital ..." is a sentence: the brackets spell the words before them."""
    letters = re.sub(r"[^A-Za-z]", "", tag)
    initials = "".join(w[0] for w in pre.split() if w[:1].isalpha()).upper()
    return len(letters) >= 2 and letters.isupper() and initials.endswith(letters)


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


def tag_places(text: str, rules: list[PlaceRule], country_terms: list[str] | tuple = ()) -> list[int]:
    """Region ids whose aliases appear in the text. An ambiguous alias (PlaceRule) counts only when
    the text is anchored: it also names the country (`country_terms`, normalised variants of the
    name and demonyms) or an unambiguous alias of any region. A negated alias never counts."""
    n = normalise(text)
    toks = set(n.split())
    plain = {r.region_id for r in rules if r.plain_hit(n, toks)}
    anchored = bool(plain) or any(f" {t} " in n for t in country_terms)
    weak = {r.region_id for r in rules if r.region_id not in plain and r.weak_hit(n, toks)} if anchored else set()
    return [r.region_id for r in rules if r.region_id in plain or r.region_id in weak]
