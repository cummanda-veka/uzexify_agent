"""Extract displayed numbers and compare them with query evidence."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class DisplayedNumber:
    value: Decimal
    tolerance: Decimal
    raw: str


_SCALES = {
    "тыс": 3,
    "тысяч": 3,
    "ming": 3,
    "млн": 6,
    "миллион": 6,
    "mln": 6,
    "million": 6,
    "млрд": 9,
    "миллиард": 9,
    "mlrd": 9,
    "milliard": 9,
    "трлн": 12,
    "trln": 12,
}
# A sign counts only when glued to the digits ("-12,5", "−12,5"); a Markdown bullet "- 5" has a space,
# and a range "100-200" is excluded by the lookbehind, which also guards the sign.
_NUMBER = re.compile(
    r"(?<![\w\d])(?P<sign>[-\u2212]?)(?P<number>\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d+)"
    r"(?:[,.]\d+)?(?:[ \u00a0\u202f]*(?P<scale>тысяч|тыс|миллиард|миллион|млрд|млн|трлн|milliard|million|mlrd|mln|trln|ming)(?!\w))?",
    re.IGNORECASE,
)
_DATE = re.compile(r"(?<!\d)(?:\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2})(?!\d)")
_LIST_MARKER = re.compile(r"^[^\S\r\n]*\d+[.)](?!\d)", re.MULTILINE)


def extract_numbers(text: str, question: str | None = None) -> list[DisplayedNumber]:
    excluded = [m.span() for pattern in (_DATE, _LIST_MARKER) for m in pattern.finditer(text)]
    question_values = {n.value for n in extract_numbers(question)} if question is not None else set()
    result = []
    for match in _NUMBER.finditer(text):
        if any(match.start() < end and match.end() > start for start, end in excluded):
            continue
        raw = match.group()
        number = match.group("number")
        # The fractional suffix is outside the named integer group.
        suffix = text[match.start("number") + len(number) : match.end()]
        fraction = re.match(r"[,.](\d+)", suffix)
        digits = re.sub(r"[ \u00a0\u202f]", "", number)
        if fraction:
            digits += "." + fraction.group(1)
        scale = _SCALES.get((match.group("scale") or "").casefold(), 0)
        value = Decimal(digits) * (Decimal(10) ** scale)
        if match.group("sign"):
            value = -value
        if not fraction and not scale and Decimal(2000) <= value <= Decimal(2030):
            continue
        if value in question_values:
            continue
        precision = len(fraction.group(1)) if fraction else 0
        tolerance = Decimal("0.5") * (Decimal(10) ** (scale - precision))
        result.append(DisplayedNumber(value=value, tolerance=tolerance, raw=raw))
    return result


def is_grounded(n: DisplayedNumber, evidence: Iterable[Decimal]) -> bool:
    return any(abs(n.value - value) <= n.tolerance for value in evidence)
