"""Text preparation and the TF-IDF features of the theme model (char_wb 2-5 + word 1-2 over
textnorm.normalise, l2 per block, as in the 2026-10-16 experiment). Imports scikit-learn."""
import html
import re

import numpy as np
import scipy.sparse as sp
from sklearn.feature_extraction.text import TfidfVectorizer

from ..textnorm import normalise

_WP_POST = re.compile(r"\s*The post .{0,400}? appeared first on .*$", re.S)
_SEGMENTS = re.compile(r"\s*(?:\.\.\.|…| · |\s\|\s)\s*")
TOKEN_PATTERN = r"(?u)\b\w+\b"


def _words(text: str) -> set[str]:
    return {w for w in normalise(text).split() if len(w) >= 4}


def clean_snippet(snippet: str | None, title: str | None = None, source: str | None = None) -> str:
    """Drop what is not the article: HTML entities, WordPress 'The post ... appeared first on ...'
    trailers, and for Google Alerts the excerpt fragments that do not share two words with the
    title (Google builds them around the alert's own query, often from sidebars)."""
    if not snippet:
        return ""
    sn = _WP_POST.sub("", html.unescape(snippet)).replace("[…]", " ")
    if source == "galerts":
        tw = _words(title or "")
        sn = " ... ".join(x for x in _SEGMENTS.split(sn) if x.strip() and len(tw & _words(x)) >= 2)
    return sn.strip()


def item_text(title: str | None, snippet: str | None, source: str | None = None) -> str:
    return " ".join(x for x in (title or "", clean_snippet(snippet, title, source)) if x)


def _vec(analyzer: str, ngram: tuple[int, int], vocab=None, min_df: int = 1, max_features: int | None = None):
    kw = {"token_pattern": TOKEN_PATTERN} if analyzer == "word" else {}
    return TfidfVectorizer(analyzer=analyzer, ngram_range=ngram, sublinear_tf=True, preprocessor=normalise,
                           dtype=np.float32, vocabulary=vocab, min_df=1 if vocab is not None else min_df,
                           max_features=None if vocab is not None else max_features, **kw)


class Features:
    """Two TF-IDF blocks side by side. fit() learns the vocabulary (and idf) from texts;
    from_bundle() rebuilds a fitted copy from stored vocabularies and idf weights."""

    def __init__(self, min_df: tuple[int, int] = (3, 2), max_features: tuple[int, int] = (300_000, 100_000),
                 char_vocab: list[str] | None = None, word_vocab: list[str] | None = None):
        self.char = _vec("char_wb", (2, 5), char_vocab, min_df[0], max_features[0])
        self.word = _vec("word", (1, 2), word_vocab, min_df[1], max_features[1])

    @property
    def n_char(self) -> int:
        return len(self.char.vocabulary_)

    def fit_transform(self, texts: list[str]):
        return sp.hstack([self.char.fit_transform(texts), self.word.fit_transform(texts)]).tocsr()

    def transform(self, texts: list[str]):
        return sp.hstack([self.char.transform(texts), self.word.transform(texts)]).tocsr()

    def pruned(self, keep: np.ndarray) -> "Features":
        """A new (unfitted) Features restricted to the given column indices."""
        nc = self.n_char
        inv_c = {i: t for t, i in self.char.vocabulary_.items()}
        inv_w = {i: t for t, i in self.word.vocabulary_.items()}
        return Features(char_vocab=[inv_c[i] for i in keep[keep < nc]],
                        word_vocab=[inv_w[i - nc] for i in keep[keep >= nc]])

    def to_bundle(self) -> dict:
        return {"char_vocab": dict(self.char.vocabulary_), "char_idf": self.char.idf_.astype(np.float32),
                "word_vocab": dict(self.word.vocabulary_), "word_idf": self.word.idf_.astype(np.float32)}

    @classmethod
    def from_bundle(cls, b: dict) -> "Features":
        f = cls.__new__(cls)
        f.char = _fixed("char_wb", (2, 5), b["char_vocab"], b["char_idf"])
        f.word = _fixed("word", (1, 2), b["word_vocab"], b["word_idf"])
        return f


def _fixed(analyzer, ngram, vocab: dict, idf):
    v = _vec(analyzer, ngram, vocab)
    v.vocabulary_ = vocab
    v.fixed_vocabulary_ = True
    v.idf_ = np.asarray(idf, dtype=np.float32)
    return v
