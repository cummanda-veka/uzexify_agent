import pytest

from uzexify.charts import ChartRejected, validate_chart, vega_lite
from uzexify.sqlguard import SqlResult


def result(columns, rows, truncated=False):
    return SqlResult("q1", "SELECT 1", columns, rows, len(rows), truncated, 1)


EXPORT = result(
    ["year", "total_usd", "total_uzs"],
    [[2024, 219306395.35, 2621400340149.9], [2025, 220524617.85, 2740766106533.96]],
)


def test_usd_and_uzs_cannot_share_an_axis():
    with pytest.raises(ChartRejected, match="panels"):
        validate_chart(
            "c1", EXPORT, "grouped_bar", "year", ["total_usd", "total_uzs"], ["USD", "so‘m"], "Eksport"
        )
    # Same declared unit does not hide differently-suffixed columns.
    with pytest.raises(ChartRejected, match="different units"):
        validate_chart(
            "c1", EXPORT, "grouped_bar", "year", ["total_usd", "total_uzs"], ["so‘m", "so‘m"], "Eksport"
        )


def test_different_units_are_drawn_as_separate_panels():
    spec = validate_chart(
        "c1", EXPORT, "panels", "year", ["total_usd", "total_uzs"], ["USD", "so‘m"], "Eksport"
    )
    vl = vega_lite(spec, EXPORT)
    assert [p["encoding"]["y"]["field"] for p in vl["vconcat"]] == ["total_usd", "total_uzs"]


def test_rows_mixing_currencies_are_rejected():
    mixed = result(["product", "currency", "total"], [["A", "Доллар США", 5.0], ["B", "Узбекский сум", 7.0]])
    with pytest.raises(ChartRejected, match="currency"):
        validate_chart("c1", mixed, "bar", "product", ["total"], ["сум"], "Сумма")


def test_chart_values_come_only_from_sql_rows():
    counts = result(["month", "all", "not_cancelled"], [["2025-01", 9000, 8400], ["2025-02", 9100, 8500]])
    spec = validate_chart(
        "c1", counts, "grouped_bar", "month", ["all", "not_cancelled"], ["сделок", "сделок"], "Сделки"
    )
    assert vega_lite(spec, counts)["data"]["values"] == [
        {"month": "2025-01", "all": 9000, "not_cancelled": 8400},
        {"month": "2025-02", "all": 9100, "not_cancelled": 8500},
    ]


@pytest.mark.parametrize(
    "res, x, y, reason",
    [
        (
            result(
                ["m", "v"],
                [["a", 1]],
            ),
            "m",
            ["v"],
            "rows",
        ),
        (result(["m", "v"], [["a", 1], ["a", 2]]), "m", ["v"], "duplicate"),
        (result(["m", "v"], [["a", 1], ["b", None]]), "m", ["v"], "numeric"),
        (result(["m", "v"], [["a", 1], ["b", 2]], truncated=True), "m", ["v"], "truncated"),
        (result(["m", "v"], [["a", 1], ["b", 2]]), "m", ["w"], "not in"),
    ],
)
def test_rejects_unfaithful_charts(res, x, y, reason):
    with pytest.raises(ChartRejected, match=reason):
        validate_chart("c1", res, "bar", x, y, ["шт"], "t")
