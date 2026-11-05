from dataclasses import asdict
from typing import Literal

import psycopg
from pydantic_ai import ModelRetry, RunContext

from uzexify import search
from uzexify.agent.deps import AgentDeps, EntityLookup
from uzexify.agent.output import stray_numbers
from uzexify.charts import ChartRejected, validate_chart
from uzexify.settings import get_settings
from uzexify.sqlguard import SqlRejected, run_readonly

MODEL_ROWS = 50
CELL_CHARS = 200


def _jsonable(d: dict) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in d.items()}


async def search_companies(
    ctx: RunContext[AgentDeps], query: str, role: Literal["any", "seller", "buyer"] = "any"
) -> list[dict]:
    """Find participants (companies) by name (any script: Uzbek Latin/Cyrillic, Russian) or exact 9-digit INN.

    Call this BEFORE filtering deals by a company. Only hits with confident=true (or exact INN)
    may be treated as the company the user meant. Returns up to 8 candidates with deal counts.
    """
    async with ctx.deps.pool.connection() as conn:
        hits = await search.search_companies(conn, query, role=role)
    rows = [_jsonable(asdict(h)) for h in hits]
    ctx.deps.evidence.entities.append(
        EntityLookup("company", query, [{"id": h.inn, "label": h.name, **r} for h, r in zip(hits, rows)])
    )
    return rows


async def search_brokers(ctx: RunContext[AgentDeps], query: str) -> list[dict]:
    """Find brokers by name or code (e.g. BK012). Call before filtering by broker."""
    async with ctx.deps.pool.connection() as conn:
        hits = await search.search_brokers(conn, query)
    rows = [_jsonable(asdict(h)) for h in hits]
    ctx.deps.evidence.entities.append(
        EntityLookup("broker", query, [{"id": h.code, "label": h.name, **r} for h, r in zip(hits, rows)])
    )
    return rows


async def search_products(ctx: RunContext[AgentDeps], query: str, query_ru: str | None = None) -> list[dict]:
    """Find product rows (deals.product / v_deals.product) matching a product term.

    `query`: the term exactly as the user wrote it (any language). `query_ru`: its Russian
    translation (e.g. query='bug‘doy', query_ru='пшеница'). Returns up to 15 candidates with
    product_name (base name), category, unit and deal counts. Filter SQL by the relevant
    `product` or `product_name` values from this result.
    """
    async with ctx.deps.pool.connection() as conn:
        hits = await search.search_products(conn, query, query_ru=query_ru, embedder=ctx.deps.embedder)
    rows = [_jsonable(asdict(h)) for h in hits]
    ctx.deps.evidence.entities.append(
        EntityLookup(
            "product",
            query,
            [{"id": h.product, "label": h.product, "score": h.rrf, **r} for h, r in zip(hits, rows)],
        )
    )
    return rows


async def run_sql(ctx: RunContext[AgentDeps], sql: str, purpose: str) -> dict:
    """Run one read-only PostgreSQL SELECT against the UZEX database and return rows.

    All arithmetic (sums, averages, percentages, differences, currency conversion, rounding)
    MUST be done in SQL. `purpose`: short description of what the query computes.
    """
    s = get_settings()
    ev = ctx.deps.evidence
    try:
        res = await run_readonly(
            ctx.deps.pool, sql, s.sql_max_rows, s.sql_timeout_ms, sql_id=ev.next_sql_id()
        )
    except SqlRejected as e:
        raise ModelRetry(f"SQL rejected: {e.reason}") from e
    except psycopg.Error as e:
        msg = (getattr(e.diag, "message_primary", None) or str(e)).splitlines()[0][:300]
        raise ModelRetry(f"SQL error: {msg}") from e
    res.purpose = purpose
    ev.sql.append(res)
    rows = [[(c[:CELL_CHARS] if isinstance(c, str) else c) for c in r] for r in res.rows[:MODEL_ROWS]]
    out: dict = {"sql_id": res.sql_id, "columns": res.columns, "rows": rows, "row_count": res.row_count}
    if res.truncated or res.row_count > MODEL_ROWS:
        out["note"] = "результат неполный — агрегируй в SQL (result is incomplete; aggregate in SQL)"
    return out


async def make_chart(
    ctx: RunContext[AgentDeps],
    sql_id: str,
    type: Literal["bar", "hbar", "line", "grouped_bar", "panels"],
    x: str,
    y: list[str],
    units: list[str],
    labels: list[str],
    title: str,
) -> dict:
    """Attach a chart to the answer, drawn from the rows of a run_sql result. You pass NO values.

    Use it when a picture helps: a trend over 3+ periods (line), a ranking or category split of
    3+ rows (bar; hbar when labels are long). Several measures in the SAME unit share one chart
    (e.g. all deals vs without cancelled: two lines, or grouped bars). Measures in different
    units/currencies (USD vs so‘m, tonnes vs deals) never share an axis, because the reader would
    compare numbers that are not comparable: use panels (one panel per unit) or chart one of them.
    `sql_id`: a run_sql result of this answer whose rows are exactly the chart (2..40 rows, ordered
    as they should appear; compute and round in SQL). `x`: category/period column. `y`: numeric
    column(s). `units`: one human unit per y column in the answer language (e.g. "so‘m", "USD",
    "тонна", "сделок"). `labels`: one short legend label per y column in the answer language (e.g.
    "Все сделки", "Без аннулированных"). `title`: short title in the answer language; it may name
    the period and the product ("Цена бензина АИ-92 в 2025 году") but carries no data values —
    those belong in the answer text, where they are checked.
    """
    ev = ctx.deps.evidence
    result = next((r for r in ev.sql if r.sql_id == sql_id), None)
    if result is None:
        raise ModelRetry(f"unknown sql_id {sql_id!r}; use one returned by run_sql in this answer")
    # Same grounding as the answer text: years, numbers from the question and whole product/code
    # tokens from the data ("АИ-92") are fine; any other number in a title or legend is unverified.
    stray = stray_numbers(" ".join([title, *labels]), ctx.deps.question, ev)
    if stray:
        raise ModelRetry(
            f"chart title/labels contain numbers not from the data or question: {stray}; "
            "name the period or product, and keep values in the answer text"
        )
    try:
        spec = validate_chart(f"c{len(ev.charts) + 1}", result, type, x, y, units, title, labels)
    except ChartRejected as e:
        raise ModelRetry(f"chart rejected: {e}") from e
    ev.charts.append(spec)
    return {"chart_id": spec.id, "points": result.row_count}


TOOLS = [search_companies, search_brokers, search_products, run_sql, make_chart]
