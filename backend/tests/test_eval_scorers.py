import pytest

from evals.scorers import _values


def _case(column: str, value: str) -> dict:
    return {
        "expect_kind": "answer",
        "checks": [{"column": column, "match": "text"}],
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
def test_text_check_accepts_inflection_only(text, ok):
    assert _values(_case("region_ru", "Ферганская область"), {"text": text}) is ok


@pytest.mark.parametrize(
    ("text", "ok"),
    [
        ("STIR raqami — 993681515.", True),
        ("STIR raqami — 993681000.", False),
        ("STIR raqami — 9936815.", False),
    ],
)
def test_text_check_keeps_identifiers_exact(text, ok):
    assert _values(_case("inn", "993681515"), {"text": text}) is ok
