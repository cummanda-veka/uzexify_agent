from decimal import Decimal

from uzexify.numbers import extract_numbers, is_grounded


def test_rounding_and_grouping():
    first = extract_numbers("1,2 млрд")[0]
    assert first.value == Decimal(1200000000)
    assert first.tolerance == Decimal(50000000)
    assert is_grounded(first, [Decimal(1234567890)])
    assert not is_grounded(extract_numbers("1,3 млрд")[0], [Decimal(1234567890)])
    assert is_grounded(extract_numbers("106 647")[0], [Decimal(106647)])
    assert extract_numbers("1\u00a0234\u202f567.89")[0].value == Decimal("1234567.89")


def test_exclusions_and_question():
    text = "1. Запись от 03.01.2022 и 2026-10-30 в 2024 году: 123 и 456."
    assert [n.value for n in extract_numbers(text, question="Что такое 123?")] == [Decimal(456)]
    assert extract_numbers("3) Пункт\n42. Следующий") == []


def test_scales_and_precision():
    assert extract_numbers("2 million")[0].value == Decimal(2000000)
    assert extract_numbers("12,34 ming")[0].tolerance == Decimal(5)
    assert extract_numbers("2024 тыс")[0].value == Decimal(2024000)


def test_signs():
    assert extract_numbers("Разница: -12,5")[0].value == Decimal("-12.5")
    assert extract_numbers("Разница: \u221212,5")[0].value == Decimal("-12.5")
    assert extract_numbers("снижение на -1,2 млрд")[0].value == Decimal(-1200000000)
    # A negative answer is not grounded by positive evidence, and vice versa.
    assert not is_grounded(extract_numbers("-12,5")[0], [Decimal("12.5")])
    assert is_grounded(extract_numbers("-12,5")[0], [Decimal("-12.5")])
    assert not is_grounded(extract_numbers("12,5")[0], [Decimal("-12.5")])


def test_bullets_and_ranges_are_not_signs():
    assert [n.value for n in extract_numbers("- 5 сделок\n- **7** сделок")] == [Decimal(5), Decimal(7)]
    assert [n.value for n in extract_numbers("от 100-200 тонн")] == [Decimal(100), Decimal(200)]


def test_days_written_with_month_names_are_dates():
    text = "С 3 января 2022 года по 30 октября 2026 года; 2026-yil 1-yanvardan 30-oktabrgacha; 30 октябрда"
    assert extract_numbers(text) == []


def test_scaled_number_needs_the_base_unit_value():
    shown = extract_numbers("25,70 трлн сумов")[0]
    assert is_grounded(shown, [Decimal("25700580756298.50")])
    # A bare 25.70 or a count of 1 is not evidence for trillions.
    assert not is_grounded(shown, [Decimal("25.70")])
    assert not is_grounded(extract_numbers("1 трлн сумов")[0], [Decimal(1)])
