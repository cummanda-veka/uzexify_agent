from dataclasses import dataclass, field
from typing import Any

from psycopg_pool import AsyncConnectionPool

from uzexify.charts import ChartSpec
from uzexify.embeddings import Embedder
from uzexify.sqlguard import SqlResult


@dataclass
class EntityLookup:
    kind: str  # company | broker | product
    query: str
    matches: list[dict[str, Any]]  # {"id","label","score", ...raw fields}


@dataclass
class EvidenceLog:
    sql: list[SqlResult] = field(default_factory=list)
    entities: list[EntityLookup] = field(default_factory=list)
    charts: list[ChartSpec] = field(default_factory=list)
    _issued: int = 0

    def next_sql_id(self) -> str:
        """Reserve a unique id before the query runs; parallel run_sql calls must not share one."""
        self._issued += 1
        return f"q{self._issued}"


@dataclass
class AgentDeps:
    pool: AsyncConnectionPool
    embedder: Embedder | None
    evidence: EvidenceLog
    question: str
