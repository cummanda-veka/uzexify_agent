from dataclasses import dataclass, field
from typing import Any

from psycopg_pool import AsyncConnectionPool

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

    def next_sql_id(self) -> str:
        return f"q{len(self.sql) + 1}"


@dataclass
class AgentDeps:
    pool: AsyncConnectionPool
    embedder: Embedder | None
    evidence: EvidenceLog
    question: str
