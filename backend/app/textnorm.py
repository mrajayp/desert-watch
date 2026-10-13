"""Text normalisation for Arabic + English keyword matching (no models, no tokens)."""
import re
import unicodedata

_AR_DIACRITICS = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭ]")
_TATWEEL = "ـ"
_AR_MAP = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ئ": "ي",
    "ة": "ه",
    "ؤ": "و",
})
_NON_WORD = re.compile(r"[^\w\s]+", re.UNICODE)
_SPACES = re.compile(r"\s+")
_AR_CHAR = re.compile("[؀-ۿ]")


def normalise(text: str | None) -> str:
    """Lower-case, strip Arabic diacritics/tatweel, unify alef/ya/ta-marbuta,
    drop punctuation, collapse whitespace. Pad with spaces so callers can do
    whole-phrase matching with ' term ' in ' text '."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = _AR_DIACRITICS.sub("", t).replace(_TATWEEL, "")
    t = t.translate(_AR_MAP).lower()
    t = t.replace("-", " ").replace("’", "'").replace("'", "")
    t = _NON_WORD.sub(" ", t)
    return " " + _SPACES.sub(" ", t).strip() + " "


def detect_lang(text: str | None) -> str:
    if not text:
        return "und"
    ar = len(_AR_CHAR.findall(text))
    letters = sum(ch.isalpha() for ch in text) or 1
    return "ar" if ar / letters > 0.3 else "en"


# Arabic attaches the article and some prepositions to the following word
# (ال، و، ب، ل، ف، بال، وال، لل). Generate those prefixed variants so
# "مستشفى" matches "والمستشفى" / "بمستشفى".
_AR_PREFIXES = ["", "و", "ب", "ل", "ف", "ال", "وال", "بال", "لل", "فال", "كال"]


def term_variants(term: str) -> list[str]:
    n = normalise(term).strip()
    if not n:
        return []
    if not _AR_CHAR.search(n):
        return [n]
    first, _, rest = n.partition(" ")
    had_al = first.startswith("ال") and len(first) > 3
    base = first[2:] if had_al else first
    # After normalisation a feminine ta-marbuta (ة→ه) is indistinguishable from the masculine
    # possessive suffix (ـه, "his"): "النائبة" (the female MP) vs "ونائبه" (and his deputy).
    # For such words keep the article: only generate the definite prefixed forms.
    ta_marbuta = term.strip().split(" ")[0].endswith("ة")
    prefixes = [p for p in _AR_PREFIXES if not (ta_marbuta and had_al and "ال" not in p and p != "لل")]
    out = {n}
    for p in prefixes:
        out.add((p + base + (" " + rest if rest else "")).strip())
    return sorted(out)
