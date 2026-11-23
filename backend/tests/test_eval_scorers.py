import pytest

from evals.scorers import _values


def _case(column: str, value: str, match: str) -> dict:
    return {
        "expect_kind": "answer",
        "checks": [{"column": column, "match": match}],
        "reference_rows": [{column: value}],
    }


@pytest.mark.parametrize(
    ("text", "ok"),
    [
        ("Склад продавца находится в Ферганской области.", True),
        ("Склад продавца: Ферганская область.", True),
        ("Склад продавца находится в Наманганской области.", False),
        ("Склад продавца находится в Ферганском районе.", False),
    ],
)
def test_ru_text_check_accepts_grammatical_case_only(text, ok):
    assert _values(_case("region_ru", "Ферганская область", "text_ru"), {"text": text}) is ok


@pytest.mark.parametrize(
    ("text", "ok"),
    [
        ("STIR raqami — 993681515.", True),
        ("STIR raqami — 993681000.", False),
    ],
)
def test_text_check_is_exact_substring(text, ok):
    assert _values(_case("inn", "993681515", "text"), {"text": text}) is ok


def test_text_check_does_not_accept_similar_words():
    assert _values(_case("product_name", "Бензин", "text"), {"text": "Товар: бензол."}) is False
