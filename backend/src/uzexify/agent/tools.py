from dataclasses import asdict
from typing import Literal

import psycopg
from pydantic_ai import ModelRetry, RunContext

from uzexify import search
from uzexify.agent.deps import AgentDeps, EntityLookup
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


TOOLS = [search_companies, search_brokers, search_products, run_sql]
