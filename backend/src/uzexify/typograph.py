"""Deterministic typography for answer text (RU / UZ Latin / UZ Cyrillic).

Norms: ГОСТ 8.417-2024 §8 (space between a number and a unit sign, incl. %), Мильчин & Чельцова
«Справочник издателя и автора» (digit groups, «тыс.»/«млн»/«млрд»/«трлн», dash vs hyphen, ranges),
Uzbek Latin orthography (Cabinet resolution №339, 1995: oʻ/gʻ and tutuq). Project choices: NBSP as the
group separator and before units, `25 %`, and the apostrophe characters the registry itself uses
(‘ U+2018 in oʻ/gʻ, ’ U+2019 for tutuq), so free text matches the names it quotes.

Never changes a value: only separators, spaces, dashes and apostrophes. Protected spans (names and
codes copied from the data) are left byte-for-byte untouched.
"""

import re

NBSP = "\u00a0"
_PLACEHOLDER = "\ue000{}\ue001"

# Words that follow a number as its unit/scale/counted noun: glue them with NBSP.
_UNIT_WORDS = (
    r"тыс\.|млн|млрд|трлн|сум(?:а|ов|ы)?|сўм|тонн(?:а|ы|у)?|кг|литр(?:а|ов)?|шт\.|"
    r"сдел(?:ка|ки|ок|ку)|компани(?:я|и|й)|USD|долл(?:\.|ар(?:а|ов)?)|п\.\s?п\.|"
    r"ming|mln|mlrd|trln|so‘m|tonna|kilogramm|litr|dona|ta|та|AQSh"
)
_UNIT_AFTER = re.compile(rf"(\d)[ \t]+(?=(?:{_UNIT_WORDS})(?![\w‘’]))", re.IGNORECASE)
_SCALE_UNIT = re.compile(
    r"(?<!\w)(тыс\.|млн|млрд|трлн|ming|mln|mlrd|trln)[ \t]+(?=(?:сум|сўм|so‘m|долл|USD|AQSh|тонн|tonna))",
    re.IGNORECASE,
)
_GROUPED = re.compile(r"(?<=\d)[ \u202f](?=\d{3}(?!\d))")
_PERCENT = re.compile(r"(\d)[ \u00a0\u202f]?%")
_SCALE_DOT = re.compile(r"(?<!\w)(млн|млрд|трлн)\.(?=\s)")
_DECIMAL_POINT = re.compile(r"(?<![\d.,])(\d{1,3}(?:[\u00a0 ]\d{3})*|\d+)\.(\d{1,4})(?![\d.])")
_ISO_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_YEAR_RANGE = re.compile(r"(?<!\d)((?:19|20)\d{2})\s?[-–—]\s?((?:19|20)\d{2})(?!\d)(?!-)")
_SPACED_HYPHEN = re.compile(r"(?<=\S) - (?=\S)")
_BULLET = re.compile(r"^(\s*(?:[-*]\s+)?)(.*)$")
_UZ_OG = re.compile(r"([oOgG])['ʻʼ`’](?=\w)")
_UZ_TUTUQ = re.compile(r"(?<=[A-Za-z])['ʼ`](?=[a-z])")


def _protect(text: str, protected: list[str]) -> tuple[str, list[str]]:
    kept: list[str] = []
    # Only names/codes with letters are data spellings; dates and numbers from SQL rows are not.
    names = {p for p in protected if len(p) >= 3 and re.search(r"[^\W\d_]", p)}
    for item in sorted(names, key=len, reverse=True):
        if item in text:
            text = text.replace(item, _PLACEHOLDER.format(len(kept)))
            kept.append(item)
    return text, kept


def _restore(text: str, kept: list[str]) -> str:
    for i, item in enumerate(kept):
        text = text.replace(_PLACEHOLDER.format(i), item)
    return text


def _fix_line(line: str, uzbek_latin: bool) -> str:
    is_table = line.lstrip().startswith("|")
    line = _ISO_DATE.sub(lambda m: f"{m[3]}.{m[2]}.{m[1]}", line)
    line = _DECIMAL_POINT.sub(r"\1,\2", line)
    line = _GROUPED.sub(NBSP, line)
    line = _PERCENT.sub(rf"\1{NBSP}%", line)
    line = _SCALE_DOT.sub(r"\1", line)
    line = _UNIT_AFTER.sub(rf"\1{NBSP}", line)
    line = _SCALE_UNIT.sub(rf"\1{NBSP}", line)
    line = _YEAR_RANGE.sub(r"\1–\2", line)
    if not is_table:
        # A spaced hyphen between words is a dash; a Markdown bullet ("- " at line start) stays.
        match = _BULLET.match(line)
        if match:
            line = match[1] + _SPACED_HYPHEN.sub(" — ", match[2])
    if uzbek_latin:
        line = _UZ_OG.sub(r"\1‘", line)
        line = _UZ_TUTUQ.sub("’", line)
    return line


def typograph(text: str, language: str, script: str, protected: list[str] | None = None) -> str:
    """Normalise typography of an answer; `protected` strings (data names/codes) stay verbatim."""
    work, kept = _protect(text, protected or [])
    uzbek_latin = language == "uz" and script == "latn"
    work = "\n".join(_fix_line(line, uzbek_latin) for line in work.split("\n"))
    return _restore(work, kept)
