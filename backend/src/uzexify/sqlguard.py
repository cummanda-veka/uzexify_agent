"""Defence-in-depth SQL validation + read-only execution.

The real security boundary is the `uzex_agent` role (SELECT-only, read-only
transactions). This parser check rejects obvious misuse early with a readable
error the model can act on.
"""

import datetime as dt
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import sqlglot
from psycopg_pool import AsyncConnectionPool
from sqlglot import exp

ALLOWED_TABLES = {
    "v_deals",
    "deals",
    "contracts",
    "participants",
    "brokers",
    "usd_rates",
    "regions",
    "products",
}
FORBIDDEN_FUNCS = {
    "pg_sleep",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "lo_import",
    "lo_export",
    "set_config",
    "pg_terminate_backend",
    "pg_cancel_backend",
}
FORBIDDEN_NODES = tuple(
    getattr(exp, n)
    for n in ("Insert", "Update", "Delete", "Create", "Drop", "Alter", "Command", "Into", "Lock", "Merge")
    if hasattr(exp, n)
)


class SqlRejected(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class SqlResult:
    sql_id: str
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    duration_ms: int
    purpose: str = ""
    extra: dict = field(default_factory=dict)


def _func_name(node: exp.Func) -> str:
    if isinstance(node, exp.Anonymous):
        return str(node.this).lower()
    return (node.sql_name() or "").lower()


def validate_sql(sql: str) -> None:
    try:
        stmts = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise SqlRejected(f"parse error: {str(e).splitlines()[0][:200]}") from e
    if len(stmts) != 1:
        raise SqlRejected("exactly one statement is allowed")
    root = stmts[0]
    if not isinstance(root, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise SqlRejected("only SELECT queries are allowed")
    cte_names = {c.alias_or_name.lower() for c in root.find_all(exp.CTE)}
    for node in root.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise SqlRejected(f"{type(node).__name__} is not allowed")
        if isinstance(node, exp.Func):
            name = _func_name(node)
            if name in FORBIDDEN_FUNCS or name.startswith("dblink"):
                raise SqlRejected(f"function {name} is not allowed")
        if isinstance(node, exp.Table) and node.name:
            name = node.name.lower()
            if node.db or (name not in ALLOWED_TABLES and name not in cte_names):
                raise SqlRejected(
                    f"table {node.sql()} is not allowed; use: {', '.join(sorted(ALLOWED_TABLES))}"
                )


def _cell(v: Any) -> Any:
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() and abs(v) < 2**53 else float(v)
    if isinstance(v, (dt.date, dt.datetime, dt.time)):
        return v.isoformat()
    if isinstance(v, (int, float, str, bool)) or v is None:
        return v
    return str(v)


async def run_readonly(
    pool: AsyncConnectionPool, sql: str, max_rows: int, timeout_ms: int, sql_id: str = "q1"
) -> SqlResult:
    validate_sql(sql)
    t = time.perf_counter()
    async with pool.connection() as conn, conn.transaction():
        await conn.execute("SET TRANSACTION READ ONLY")
        await conn.execute(f"SET LOCAL statement_timeout = {int(timeout_ms)}")  # ty: ignore[no-matching-overload]
        async with conn.cursor() as cur:
            await cur.execute(sql)  # ty: ignore[no-matching-overload] - validated dynamic SQL
            columns = [d.name for d in cur.description or []]
            raw = await cur.fetchmany(max_rows + 1)
    truncated = len(raw) > max_rows
    rows = [[_cell(v) for v in r] for r in raw[:max_rows]]
    return SqlResult(
        sql_id=sql_id,
        sql=sql,
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
        duration_ms=int((time.perf_counter() - t) * 1000),
    )
