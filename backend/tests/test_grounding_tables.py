from decimal import Decimal

from uzexify.agent.output import scale_table_cells
from uzexify.numbers import extract_numbers, is_grounded

TABLE = "Итог:\n| Товар | Сумма, трлн сумов | Сделок |\n|---|---:|---:|\n| Хлопок | 13,16 | 9 930 |"


def test_scaled_table_cell_is_checked_at_header_scale():
    nums = extract_numbers(scale_table_cells(TABLE))
    evidence = [Decimal("13158958787431.85"), Decimal(9930)]
    assert all(is_grounded(n, evidence) for n in nums)
    # Without the header scale the same cell would wrongly read as 13,16.
    assert not all(is_grounded(n, evidence) for n in extract_numbers(TABLE))


def test_unscaled_columns_are_untouched():
    assert "9 930 трлн" not in scale_table_cells(TABLE)
