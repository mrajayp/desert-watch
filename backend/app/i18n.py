"""Interface language for text the API sends (error messages, notes, labels, reasons).

The code is written in English and wraps every user-facing string in `tr()` (not `_()`: many
endpoints take a parameter named `_`). The Arabic catalogue
is in locales/ar/*.json, keyed by the exact English text; a string without an entry stays English.
The browser sends `X-Lang: ar|en` with every request (frontend/src/api.js) and the middleware in
main.py puts it in a context variable, so `_()` needs no request object.

    tr("Unknown theme")                       -> "موضوع غير معروف" when the request asked for Arabic
    tr("{n} articles in {week}", n=3, week=w) -> placeholders are {name}, as in the frontend
    pick(cfg, "label")                       -> cfg["label_ar"] in Arabic, cfg["label"] otherwise
Module-level constants hold the English text (marked with N_()) and are wrapped at response time: `tr(FX_NOTE)`.
tests/test_i18n.py fails when a wrapped literal has no Arabic or an error message is not wrapped."""
import contextvars
import json
import re
from pathlib import Path

LANG: contextvars.ContextVar[str] = contextvars.ContextVar("dw_lang", default="en")
CATALOG_DIR = Path(__file__).resolve().parent / "locales" / "ar"
_AR: dict[str, str] = {}


def load() -> dict[str, str]:
    _AR.clear()
    for f in sorted(CATALOG_DIR.glob("*.json")):
        _AR.update(json.loads(f.read_text(encoding="utf-8")))
    return _AR


load()


def lang() -> str:
    return LANG.get()


def set_lang(value: str | None) -> contextvars.Token:
    return LANG.set("ar" if (value or "").lower().startswith("ar") else "en")


def _fill(s: str, kw: dict) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: str(kw[m.group(1)]) if m.group(1) in kw else m.group(0), s) if kw else s


def tr(en: str, **kw) -> str:
    """English text in, the request's language out."""
    if not isinstance(en, str):
        return en
    return _fill(_AR.get(en, en) if LANG.get() == "ar" else en, kw)


def N_(en: str) -> str:
    """Marks a string for the catalogue where it is defined (a module constant); translate it with tr() when used."""
    return en


def pick(obj: dict | None, base: str = "name") -> str:
    """A bilingual field from config or a row dict: base_ar in Arabic, base / base_en otherwise."""
    if not obj:
        return ""
    en = obj.get(f"{base}_en") or obj.get(base) or ""
    return (obj.get(f"{base}_ar") or en) if LANG.get() == "ar" else (en or obj.get(f"{base}_ar") or "")


def content_path(folder: Path, stem: str, ext: str = ".md") -> Path:
    """A content file in the request's language (stem.ar.md), falling back to English (stem.md)."""
    if LANG.get() == "ar" and (folder / f"{stem}.ar{ext}").exists():
        return folder / f"{stem}.ar{ext}"
    return folder / f"{stem}{ext}"
