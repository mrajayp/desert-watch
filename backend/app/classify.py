"""Rule-based theme and place tagging. Pure functions over pre-compiled term lists.

The rules stay as the interpretable baseline even after the learned classifier
switches on (see learning.py)."""
from dataclasses import dataclass, field

from .textnorm import normalise, term_variants


@dataclass
class ThemeRule:
    theme_id: int
    slug: str
    version: int
    include: list[str] = field(default_factory=list)  # normalised phrase variants
    exclude: list[str] = field(default_factory=list)
    cooc: list[list[str]] = field(default_factory=list)  # every group must hit
    strict: bool = False
    require_country: bool = False

    @classmethod
    def build(cls, theme_id, slug, version, en_terms, ar_terms, exclude, cooc=None, strict=False, require_country=False):
        inc = sorted({v for t in [*en_terms, *ar_terms] for v in term_variants(t)})
        exc = sorted({v for t in exclude for v in term_variants(t)})
        groups = [sorted({v for t in g for v in term_variants(t)}) for g in (cooc or []) if g]
        return cls(theme_id, slug, version, inc, exc, groups, bool(strict), bool(require_country))

    def matches(self, norm_text: str) -> list[str]:
        if any(f" {e} " in norm_text for e in self.exclude):
            return []
        hits = [t for t in self.include if f" {t} " in norm_text]
        if not hits and self.cooc:
            per_group = [next((t for t in g if f" {t} " in norm_text), None) for g in self.cooc]
            if all(per_group):
                hits = ["+".join(per_group)]
        return hits


@dataclass
class PlaceRule:
    region_id: int
    variants: list[str]

    @classmethod
    def build(cls, region_id, aliases):
        return cls(region_id, sorted({v for a in aliases for v in term_variants(a)}))


def classify_themes(text: str, rules: list[ThemeRule]) -> dict[int, list[str]]:
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
