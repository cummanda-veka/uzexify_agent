"""Normalization helpers for Uzbek and Russian names."""

import re
import unicodedata
from typing import Literal

_APOSTROPHES = "ʻʼ‘’`´'"
_TRANSLITERATION = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "ғ": "g",
        "д": "d",
        "е": "e",
        "ё": "yo",
        "ж": "j",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "қ": "q",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "ў": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "x",
        "ҳ": "h",
        "ц": "s",
        "ч": "ch",
        "ш": "sh",
        "щ": "sh",
        "ъ": "",
        "ы": "i",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
)
_LEGAL_FORMS = re.compile(r"\b(?:masuliyati\s+cheklangan\s+jamiyati|mchj|xk|ok|aj|qk)\b")


def fold(s: str) -> str:
    normalized = unicodedata.normalize("NFKC", s).casefold()
    # NFKC turns the spacing acute accent into a space plus combining acute.
    normalized = normalized.replace(" \u0301", "")
    return " ".join(
        "".join(
            "" if c in _APOSTROPHES else " " if unicodedata.category(c).startswith("P") else c
            for c in normalized
        ).split()
    )


def to_latin(s: str) -> str:
    return s.translate(_TRANSLITERATION)


def name_key(s: str) -> str:
    return " ".join(_LEGAL_FORMS.sub(" ", to_latin(fold(s))).split())


def product_key(s: str) -> str:
    return to_latin(fold(s))


def detect_lang(s: str) -> Literal["ru", "uz"]:
    lowered = s.casefold()
    if any(c in lowered for c in "ўқғҳ"):
        return "uz"
    letters = [c for c in lowered if c.isalpha()]
    cyrillic = sum("CYRILLIC" in unicodedata.name(c, "") for c in letters)
    return "ru" if letters and cyrillic > len(letters) / 2 else "uz"
