from uzexify.agent.deps import EvidenceLog
from uzexify.agent.output import stray_numbers
from uzexify.sqlguard import SqlResult


def _evidence() -> EvidenceLog:
    ev = EvidenceLog()
    ev.sql.append(
        SqlResult("q1", "select", ["product", "price"], [["Бензин АИ-92", 14028458.5]], 1, False, 1)
    )
    return ev


def test_product_code_and_year_may_be_named():
    assert stray_numbers("Цена бензина АИ-92 в 2025 году", "", _evidence()) == []


def test_digit_inside_a_name_does_not_ground_a_claim():
    # "2" occurs inside "АИ-92" but "2 сделки" is an unverified value.
    assert stray_numbers("Бензин АИ-92: 2 сделки", "", _evidence()) == ["2"]
