"""Text normalisation for Arabic + English keyword matching (no models, no tokens), the language
heuristic and the English plural variants."""
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
# English possessive: "Libya's" -> libya, "NOC’s" -> noc ("migrants'" loses only the apostrophe below)
_POSSESSIVE = re.compile(r"(?<=\w)['’ʼ]s\b")
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
    t = _POSSESSIVE.sub("", t.translate(_AR_MAP).lower())
    t = t.replace("-", " ").replace("’", "'").replace("'", "")
    t = _NON_WORD.sub(" ", t)
    return " " + _SPACES.sub(" ", t).strip() + " "


# Latin-script languages: the commonest function words of each, kept to words that are rare in the
# other two (so "in", "a", "al", "per", "come", "plus", "son" are left out: English, Italian or a name).
# Elisions count by their stub ("l'Italie", "dell'area": l, dell), never the English possessive "'s".
_LATIN_WORDS = {
    "en": frozenset("""the and of to is are was were for on with as by at from that this it be has have had says said
        after over into not will who its their than more new about against between during amid off out up
        than been would could should also""".split()),
    "fr": frozenset("""le la les des du de un une et est dans pour sur au aux que qui pas avec ce cette ces ses sa
        sont été ont par nous vous ils elle elles à où mais ou selon après contre entre aussi ans morts leur leurs cet
        lui être fait très tout tous dont en l d qu n c j aujourd""".split()),
    "it": frozenset("""il lo la le gli un una uno di del della dei delle degli dello dal dalla dai dalle nel nella nei
        nelle nello alla alle agli allo sul sulla sui sulle con che chi è sono ha hanno anche più tra fra questo questa
        questi queste ed da dopo secondo contro oggi ieri morti feriti ma se si suo sua loro sia stato stata essere
        viene vengono mentre ancora già tutto tutti l c dell nell dall sull""".split()),
}
# words only one of the two writes, counted double: a headline with a single "è" or "à" is already telling
_LATIN_STRONG = {"à": "fr", "où": "fr", "aujourd": "fr", "è": "it", "più": "it", "già": "it", "perché": "it"}
_LATIN_TOKEN = re.compile(r"[a-zà-öø-ÿœ]+")
_FR_ACCENTS, _IT_ACCENTS = set("çêâîôûœë"), set("ìò")   # the accents one of the two uses and the other hardly does


def detect_lang(text: str | None) -> str:
    """'ar' when Arabic letters are over 30% of the letters; otherwise 'fr' or 'it' when the text carries at
    least two of that language's function words and more of them than English ones; else 'en'. A stopword
    heuristic, not a model: a short Italian headline without articles still reads as 'en'."""
    if not text:
        return "und"
    ar = len(_AR_CHAR.findall(text))
    letters = sum(ch.isalpha() for ch in text) or 1
    if ar / letters > 0.3:
        return "ar"
    toks = _LATIN_TOKEN.findall(text.lower())
    score = {lang: sum(1 for t in toks if t in words) for lang, words in _LATIN_WORDS.items()}
    for t in toks:
        if t in _LATIN_STRONG:
            score[_LATIN_STRONG[t]] += 1
    fr, it = score["fr"], score["it"]
    if max(fr, it) < 2 or max(fr, it) <= score["en"]:
        return "en"
    if fr != it:
        return "fr" if fr > it else "it"
    fr_acc, it_acc = sum(ch in _FR_ACCENTS for ch in text), sum(ch in _IT_ACCENTS for ch in text)
    return "it" if it_acc > fr_acc else "fr"


# Arabic attaches the article and some prepositions to the following word
# (ال، و، ب، ل، ف، بال، وال، لل). Generate those prefixed variants so
# "مستشفى" matches "والمستشفى" / "بمستشفى".
_AR_PREFIXES = ["", "و", "ب", "ل", "ف", "ال", "وال", "بال", "لل", "فال", "كال"]


# English: a term matches its regular plural or third-person form too ("protest" finds "protests",
# "refinery" finds "refineries", "clash" finds "clashes"); a phrase inflects its last word ("power cut"
# finds "power cuts"). Past and -ing forms are not generated: on the exclusion and veto lists the same
# rule shifts meaning ("storm" to "stormed", "traffic" to "trafficked") and "fuel" would match "fueled
# tensions", so the verb forms that matter stay written in the lists (killed, killing, abducted).
_EN_WORD = re.compile(r"^[a-z]+$")
_EN_IRREGULAR = {"woman": "women", "man": "men", "child": "children", "person": "people", "wife": "wives",
                 "life": "lives", "crisis": "crises", "analysis": "analyses"}
# words whose -s form is nearly always another sense in headlines ("rhetoric fuels abuses"): no plural
_EN_NO_PLURAL = frozenset({"fuel"})


def english_plural(word: str) -> str | None:
    """The regular plural / third-person form of a lower-case English word, or None when there is no safe
    one: non-letters, fewer than 3 letters, words already ending in s ("clashes", "militias") or in -ed,
    and the few words whose -s form means something else (_EN_NO_PLURAL)."""
    if word in _EN_IRREGULAR:
        return _EN_IRREGULAR[word]
    if not _EN_WORD.match(word) or len(word) < 3 or word.endswith(("s", "ed")) or word in _EN_NO_PLURAL:
        return None
    if word.endswith(("x", "z", "ch", "sh")):
        return word + "es"
    if word.endswith("y") and word[-2] not in "aeiou":
        return word[:-1] + "ies"
    return word + "s"


def term_variants(term: str) -> list[str]:
    n = normalise(term).strip()
    if not n:
        return []
    if not _AR_CHAR.search(n):
        head, _, last = n.rpartition(" ")
        plural = english_plural(last)
        return [n] if not plural else sorted({n, (head + " " + plural).strip()})
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
