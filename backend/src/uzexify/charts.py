"""Charts bound to SQL evidence.

The model never supplies chart values: it names a successful SQL result (`sql_id`) and its
columns. The server validates the reference and the units, stores a `ChartSpec`, and every
renderer (web, Telegram PNG) reads the values from the same SQL rows.
"""

import json
import math
import re
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any, Literal

from pydantic import BaseModel

from uzexify.sqlguard import SqlResult

ChartType = Literal["bar", "hbar", "line", "grouped_bar", "panels"]
MIN_POINTS = 2
MAX_POINTS = 40
MAX_SERIES = 4
# Words in a column alias that pin its unit ("usd_all", "total_uzs", "volume_tonnes"); two different
# units may never share an axis, whatever unit labels the model declares.
_UNIT_WORDS = {
    "usd": "usd",
    "dollar": "usd",
    "dollars": "usd",
    "uzs": "uzs",
    "sum": "uzs",
    "som": "uzs",
    "soum": "uzs",
    "ton": "t",
    "tons": "t",
    "tonne": "t",
    "tonnes": "t",
    "tonna": "t",
    "kg": "kg",
    "litr": "l",
    "litre": "l",
    "liter": "l",
    "pct": "pct",
    "percent": "pct",
    "share": "pct",
    "count": "count",
    "cnt": "count",
}


def _column_units(column: str) -> set[str]:
    return {_UNIT_WORDS[w] for w in re.split(r"[^0-9a-z]+", column.casefold()) if w in _UNIT_WORDS}


def _check_axis(columns: list[str], declared: list[str]) -> None:
    """One axis = one unit: by the declared units and by the units the column aliases name."""
    if len({u.strip().casefold() for u in declared}) != 1:
        raise ChartRejected(
            f"series {columns} have different units {declared}; they cannot share an axis — use panels"
        )
    named = set().union(*(_column_units(c) for c in columns))
    if len(named) > 1:
        raise ChartRejected(
            f"columns {columns} are in different units ({sorted(named)}); give each unit its own panel "
            "with its real unit"
        )


_UNIT_COLUMNS = ("currency", "unit")


class ChartRejected(Exception):
    pass


class ChartSeries(BaseModel):
    column: str
    unit: str
    label: str


class ChartSpec(BaseModel):
    id: str
    sql_id: str
    type: ChartType
    x: str
    series: list[ChartSeries]
    title: str


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def validate_chart(
    chart_id: str,
    result: SqlResult,
    chart_type: ChartType,
    x: str,
    y: list[str],
    units: list[str],
    title: str,
    labels: list[str] | None = None,
) -> ChartSpec:
    """Check that the chart can be drawn faithfully from `result`; raise ChartRejected with a fixable reason."""
    if result.truncated:
        raise ChartRejected(f"{result.sql_id} is truncated; aggregate in SQL so the chart has every row")
    if not MIN_POINTS <= result.row_count <= MAX_POINTS:
        raise ChartRejected(
            f"{result.sql_id} has {result.row_count} rows; a chart needs {MIN_POINTS}..{MAX_POINTS} "
            "(aggregate or LIMIT in SQL)"
        )
    cols = result.columns
    if x not in cols:
        raise ChartRejected(f"x column {x!r} not in {cols}")
    if not y or len(y) > MAX_SERIES:
        raise ChartRejected(f"give 1..{MAX_SERIES} y columns")
    if len(units) != len(y):
        raise ChartRejected("units must have one entry per y column (e.g. 'so‘m', 'USD', 'тонна', 'сделок')")
    if any(not u.strip() for u in units):
        raise ChartRejected("every series needs a non-empty unit")
    labels = labels or y
    if len(labels) != len(y) or any(not lb.strip() for lb in labels):
        raise ChartRejected("labels must have one non-empty legend label per y column")
    missing = [c for c in y if c not in cols]
    if missing:
        raise ChartRejected(f"y columns {missing} not in {cols}")
    if x in y:
        raise ChartRejected("x and y must be different columns")

    xi = cols.index(x)
    xs = [row[xi] for row in result.rows]
    if any(v is None for v in xs):
        raise ChartRejected(f"x column {x!r} has NULLs; filter or label them in SQL")
    if len({str(v) for v in xs}) != len(xs):
        raise ChartRejected(f"x column {x!r} has duplicate values; group by it in SQL")
    for col in y:
        ci = cols.index(col)
        if not all(_is_number(row[ci]) for row in result.rows):
            raise ChartRejected(f"y column {col!r} must be numeric with no NULLs")

    # Mixed currencies/units inside one result cannot share an axis.
    for uc in _UNIT_COLUMNS:
        if uc in cols:
            distinct = {row[cols.index(uc)] for row in result.rows}
            if len(distinct) > 1:
                raise ChartRejected(
                    f"rows mix several {uc} values {sorted(map(str, distinct))}; filter one in SQL "
                    "(or use amount_uzs) before charting"
                )

    if chart_type in ("bar", "hbar", "line") and len(y) != 1:
        raise ChartRejected(f"{chart_type} takes exactly one y column; use grouped_bar or panels for several")
    if chart_type == "grouped_bar":
        if len(y) < 2:
            raise ChartRejected("grouped_bar needs 2+ comparable y columns")
        _check_axis(y, units)
    if chart_type == "panels":
        if len(y) < 2:
            raise ChartRejected("panels needs 2+ y columns (one panel each)")
        # Each panel groups the series with the same declared unit; every such group is one axis.
        groups: dict[str, list[int]] = {}
        for i, u in enumerate(units):
            groups.setdefault(u.strip().casefold(), []).append(i)
        for idx in groups.values():
            _check_axis([y[i] for i in idx], [units[i] for i in idx])

    return ChartSpec(
        id=chart_id,
        sql_id=result.sql_id,
        type=chart_type,
        x=x,
        series=[
            ChartSeries(column=c, unit=u.strip(), label=lb.strip())
            for c, u, lb in zip(y, units, labels, strict=True)
        ],
        title=title.strip(),
    )


PALETTE = ["#7fb2ff", "#ffcf6b", "#5fd39a", "#ff8a7a"]


def vega_lite(spec: ChartSpec, result: SqlResult) -> dict[str, Any]:
    """Fixed Vega-Lite template (no transforms, no aggregation) filled with the SQL rows."""
    cols = result.columns
    values = [dict(zip(cols, row, strict=True)) for row in result.rows]
    order = [str(row[cols.index(spec.x)]) for row in result.rows]
    long_labels = max(len(s) for s in order) > 14
    x_enc = {
        "field": spec.x,
        "type": "ordinal",
        "sort": order,
        "title": None,
        "axis": {"labelAngle": -35 if long_labels else 0, "labelLimit": 180},
    }
    axis_style = {
        "labelColor": "#b9c0d0",
        "titleColor": "#8a93a8",
        "titleFontWeight": "normal",
        "gridColor": "#22252f",
        "domainColor": "#2a2e3a",
        "tickColor": "#2a2e3a",
        "labelFontSize": 12,
    }
    # Legend shows the model's labels instead of SQL aliases; the mapping is JSON, not executable input.
    names = json.dumps({s.column: s.label for s in spec.series}, ensure_ascii=False)
    legend = {"orient": "top", "title": None, "labelExpr": f"{names}[datum.label] || datum.label"}

    def layer(col: str, unit: str, color: str, mark: str) -> dict[str, Any]:
        y_enc = {"field": col, "type": "quantitative", "title": unit, "axis": {"format": ",~r"}}
        if mark == "line":
            return {
                "mark": {"type": "line", "point": True, "color": color, "strokeWidth": 2.5},
                "encoding": {"x": x_enc, "y": y_enc},
            }
        if spec.type == "hbar":
            return {
                "mark": {"type": "bar", "color": color, "cornerRadiusEnd": 4},
                "encoding": {"y": {**x_enc, "axis": {}}, "x": y_enc},
            }
        return {
            "mark": {"type": "bar", "color": color, "cornerRadiusEnd": 4},
            "encoding": {"x": x_enc, "y": y_enc},
        }

    base: dict[str, Any] = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "background": "#0d0f16",
        "padding": 16,
        "data": {"values": values},
        "config": {
            "font": "Noto Sans",
            "axis": axis_style,
            "title": {"color": "#eef1f8", "fontSize": 15, "anchor": "start"},
            "view": {"stroke": None},
            "legend": {"labelColor": "#b9c0d0", "titleColor": "#b9c0d0"},
        },
        "title": spec.title,
    }
    # Every category keeps its own room (the web chart scrolls the same way), so no label is dropped.
    per_category = 0 if spec.type == "line" else len(spec.series) * 26 + 44
    width = max(640, len(order) * per_category)

    def grouped(members: list[ChartSeries], unit: str, height: int) -> dict[str, Any]:
        # fold only reshapes the SQL columns into rows; no aggregation or computed values.
        order = [m.column for m in members]
        return {
            "width": width,
            "height": height,
            "transform": [{"fold": order, "as": ["series", "value"]}],
            "mark": {"type": "bar", "cornerRadiusEnd": 3},
            "encoding": {
                "x": x_enc,
                "xOffset": {"field": "series", "sort": order},
                "y": {"field": "value", "type": "quantitative", "title": unit},
                "color": {
                    "field": "series",
                    "sort": order,
                    "scale": {"domain": order, "range": PALETTE[: len(order)]},
                    "legend": legend,
                },
            },
        }

    if spec.type in ("bar", "hbar", "line"):
        s = spec.series[0]
        return {**base, "width": width, "height": 320, **layer(s.column, s.unit, PALETTE[0], spec.type)}
    if spec.type == "grouped_bar":
        return {**base, **grouped(spec.series, spec.series[0].unit, 320)}
    # panels: one chart per unit (series sharing a unit share a panel), stacked, each with its own axis.
    groups: dict[str, list[ChartSeries]] = {}
    for s in spec.series:
        groups.setdefault(s.unit, []).append(s)
    panels = [
        {"width": width, "height": 200, "title": unit, **layer(members[0].column, unit, PALETTE[0], "bar")}
        if len(members) == 1
        else {"title": unit, **grouped(members, unit, 200)}
        for unit, members in groups.items()
    ]
    return {**base, "vconcat": panels}


_FONTS_DIR = Path(__file__).parent / "fonts"


@cache
def _converter() -> ModuleType:
    import vl_convert

    # Bundled Noto Sans (OFL) covers Russian and Uzbek Latin/Cyrillic; no system fonts needed.
    vl_convert.register_font_directory(str(_FONTS_DIR))
    return vl_convert


def chart_png(spec: ChartSpec, result: SqlResult) -> bytes:
    """Render the chart for Telegram from the same rows the web chart uses (no network access)."""
    return _converter().vegalite_to_png(
        json.dumps(vega_lite(spec, result), ensure_ascii=False),
        scale=2,
        format_locale="ru-RU",
        allowed_base_urls=[],
    )
