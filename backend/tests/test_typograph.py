from uzexify.typograph import NBSP, typograph


def ru(text, protected=None):
    return typograph(text, "ru", "cyrl", protected)


def test_digit_groups_and_units_use_nbsp():
    assert ru("Заключено **106 647 сделок**.") == f"Заключено **106{NBSP}647{NBSP}сделок**."
    assert (
        ru("Сумма 2 740 766 106 533,96 сума") == f"Сумма 2{NBSP}740{NBSP}766{NBSP}106{NBSP}533,96{NBSP}сума"
    )


def test_decimal_point_becomes_comma_but_dates_stay():
    assert ru("Курс 12410.16 сум на 31.12.2024") == f"Курс 12410,16{NBSP}сум на 31.12.2024"


def test_percent_scale_and_dash():
    assert ru("Доля 6,98% - это много") == f"Доля 6,98{NBSP}% — это много"
    assert ru("1,2 млрд. сум") == f"1,2{NBSP}млрд{NBSP}сум"


def test_iso_dates_and_year_ranges():
    assert (
        ru("с 2026-01-01 по 2026-10-30, период 2022-2026") == "с 01.01.2026 по 30.10.2026, период 2022–2026"
    )


def test_markdown_bullets_and_tables_keep_hyphens():
    text = "Итог:\n- Без аннулированных: 99 324\n| Год | Сумма |\n|---|---:|"
    assert ru(text) == f"Итог:\n- Без аннулированных: 99{NBSP}324\n| Год | Сумма |\n|---|---:|"


def test_uzbek_apostrophes_follow_registry_characters():
    out = typograph("Farg'ona viloyatida 5 ta bitim, ma'lumot so'm", "uz", "latn")
    assert out == f"Farg‘ona viloyatida 5{NBSP}ta bitim, ma’lumot so‘m"


def test_protected_names_are_untouched():
    name = '"ТАШУ-ЕНЕРГО - 2" МЧЖ 12.5'
    assert ru(f"Лидер {name} - 1 200 тонн", [name]) == f"Лидер {name} — 1{NBSP}200{NBSP}тонн"


def test_identifiers_and_years_are_not_grouped():
    assert ru("ИНН 915688255, сделка № 247890 в 2024 году") == "ИНН 915688255, сделка № 247890 в 2024 году"
