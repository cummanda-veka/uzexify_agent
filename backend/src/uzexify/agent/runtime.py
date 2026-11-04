"""Process-wide lazy runtime: DB pool, embedder, instructions, agent."""

import asyncio
from dataclasses import dataclass

from pgvector.psycopg import register_vector_async
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool
from pydantic_ai import Agent

from uzexify import observability
from uzexify.agent.deps import AgentDeps
from uzexify.agent.models import build_agent_model
from uzexify.agent.output import Answer, validate_answer
from uzexify.agent.prompt import build_instructions
from uzexify.agent.tools import TOOLS
from uzexify.embeddings import Embedder
from uzexify.settings import get_settings


@dataclass
class Runtime:
    pool: AsyncConnectionPool
    embedder: Embedder | None
    agent: Agent[AgentDeps, Answer]
    instructions: str


_runtime: Runtime | None = None
_lock = asyncio.Lock()


async def _configure(conn: AsyncConnection) -> None:
    await register_vector_async(conn)


def build_agent(instructions: str) -> Agent[AgentDeps, Answer]:
    agent = Agent(
        build_agent_model(),
        deps_type=AgentDeps,
        output_type=Answer,
        instructions=instructions,
        tools=TOOLS,
        retries={"tools": 2, "output": 2},
        name="uzexify",
    )
    agent.output_validator(validate_answer)
    return agent


async def get_runtime() -> Runtime:
    global _runtime
    async with _lock:
        if _runtime is None:
            s = get_settings()
            pool = AsyncConnectionPool(
                s.agent_database_url, min_size=1, max_size=10, configure=_configure, open=False
            )
            observability.init_tracing()
            await pool.open(wait=True)
            async with pool.connection() as conn:
                instructions = await build_instructions(conn)
            embedder = Embedder() if s.embedding_api_key else None
            _runtime = Runtime(pool, embedder, build_agent(instructions), instructions)
        return _runtime


async def close_runtime() -> None:
    global _runtime
    if _runtime is not None:
        await _runtime.pool.close()
        _runtime = None
