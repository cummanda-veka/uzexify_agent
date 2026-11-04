"""Deterministic style checks for answer text (norms: docs/style.md).

Each check returns short violation strings. Names and codes copied from the data (`protected`) are
removed before checking, so the data's own spelling never counts against style.
"""

import re

JARGON = re.compile(r"\b[a-z]+_[a-z_]+\b|\bSQL\b|\bv_deals\b|\(Не оплачен\)|\bnull\b", re.IGNORECASE)
ID_CONTEXT = re.compile(r"(№|ИНН|INN|STIR|СТИР|raqam|рақам|сон|son|код|kod)\s*[:#]?\s*$", re.IGNORECASE)
UNGROUPED = re.compile(r"(?<![\d.,\u00a0])(\d{5,})(?![\d.,]|-?(?:raqam|son|рақам|сон))")
DECIMAL_POINT = re.compile(r"(?<![\d.])\d+\.\d+(?![\d.])")
PERCENT = re.compile(r"\d%|\d %")
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
LATIN_WORD = re.compile(r"\b[A-Za-z]{3,}\b")

RU_NOUNS = {
    "сделк": ("сделка", "сделки", "сделок"),
    "компани": ("компания", "компании", "компаний"),
    "тонн": ("тонна", "тонны", "тонн"),
}
RU_COUNT = re.compile(r"(\d[\d\u00a0 ]*(?:,\d+)?)[\u00a0 ](сделк\w*|сделок|компани\w*|тонн\w*)")


def _plural(n_text: str, forms: tuple[str, str, str]) -> str:
    one, few, many = forms
    if "," in n_text:
        return few
    n = int(re.sub(r"\D", "", n_text))
    if 11 <= n % 100 <= 14:
        return many
    return one if n % 10 == 1 else few if 2 <= n % 10 <= 4 else many


def free_text(text: str, protected: list[str]) -> str:
    names = {p for p in protected if len(p) >= 3 and re.search(r"[^\W\d_]", p)}
    for item in sorted(names, key=len, reverse=True):
        text = text.replace(item, " ⟨name⟩ ")
    return text


def _unquoted(text: str) -> str:
    """Text outside «…» / “…” quotes: quoted names keep their own script."""
    return re.sub(r"«[^»]*»|“[^”]*”|\"[^\"]*\"", " ", text)


def lint(text: str, lang: str, kind: str, protected: list[str]) -> list[str]:
    """`lang`: ru | uz_latn | uz_cyrl."""
    issues: list[str] = []
    body = free_text(text, protected)
    lines = body.split("\n")
    prose = "\n".join(line for line in lines if not line.lstrip().startswith("|"))

    if re.search(r"^\s*#", body, re.MULTILINE):
        issues.append("markdown: heading")
    if "```" in body or re.search(r"\[[^\]]+\]\([^)]+\)", body):
        issues.append("markdown: code or link")
    if re.search(r"^\s{2,}[-*] ", body, re.MULTILINE):
        issues.append("markdown: nested list")
    bullets = [line for line in lines if re.match(r"^\s*[-*] ", line)]
    if len(bullets) > 10:
        issues.append(f"length: {len(bullets)} bullets")

    for m in UNGROUPED.finditer(body):
        if not ID_CONTEXT.search(body[: m.start()][-14:]):
            issues.append(f"number: ungrouped {m[1]}")
    if DECIMAL_POINT.search(body):
        issues.append("number: decimal point")
    if PERCENT.search(body):
        issues.append("number: % without NBSP")
    if ISO_DATE.search(body):
        issues.append("date: ISO format")
    # 13+ significant digits in prose are unreadable; round to млн/млрд/трлн in text.
    if re.search(r"\d{1,3}(?:\u00a0\d{3}){4,}", prose):
        issues.append("number: too many digits in prose")

    for m in JARGON.finditer(prose):
        issues.append(f"jargon: {m[0]}")
    if "!" in prose:
        issues.append("tone: exclamation")

    # Names copied from the data ("Nashuya Broker" MChJ, regions) keep their own script.
    names = {p for p in protected if len(p) >= 3}
    names |= {re.sub(r'"([^"]*)"', r"«\1»", p) for p in names}
    unnamed = prose
    for name in sorted(names, key=len, reverse=True):
        unnamed = unnamed.replace(name, " ")
    outside = _unquoted(unnamed)
    if lang == "ru":
        if '"' in outside:
            issues.append("typography: ASCII quotes")
        for m in RU_COUNT.finditer(body):
            word = m[2].casefold()
            stem = next((s for s in RU_NOUNS if word.startswith(s)), None)
            if stem and word in RU_NOUNS[stem]:
                expected = _plural(m[1], RU_NOUNS[stem])
                if word != expected:
                    issues.append(f"agreement: {m[1].strip()} {word} → {expected}")
        latin = [w for w in LATIN_WORD.findall(outside) if w not in {"USD", "name"}]
        if latin:
            issues.append(f"script: latin words in RU {latin[:3]}")
    if lang == "uz_latn":
        if re.search(r"\d[\u00a0 ]ta \w+lar\b", body):
            issues.append("agreement: plural after 'ta'")
        if re.search(r"[oOgG]['`ʼ’]", outside):
            issues.append("typography: wrong apostrophe in oʻ/gʻ")
        if re.search(r"[А-Яа-яЁё]{3,}", outside):
            issues.append("script: cyrillic words in UZ-Latn")
    if lang == "uz_cyrl":
        if re.search(r"\d[\u00a0 ]та \w+лар\b", body):
            issues.append("agreement: plural after 'та'")
        words = [w for w in LATIN_WORD.findall(outside) if w not in {"USD", "name"}]
        if words:
            issues.append(f"script: latin words in UZ-Cyrl {words[:3]}")
    return issues
