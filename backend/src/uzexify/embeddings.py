"""Embeddings over an OpenAI-compatible endpoint + `uzexify embed`."""

import asyncio
import logging

import psycopg
from openai import AsyncOpenAI
from pgvector.psycopg import register_vector

from uzexify.settings import get_settings

log = logging.getLogger(__name__)
BATCH = 32
PARALLEL = 4
REQUEST_TIMEOUT_S = 3.0


def _is_gemini(model: str) -> bool:
    return "gemini-embedding" in model


class Embedder:
    def __init__(self, model: str | None = None, batch: bool = True, timeout_s: float = REQUEST_TIMEOUT_S):
        s = get_settings()
        self.model = model or s.embedding_model
        self.batch = batch
        self.client = AsyncOpenAI(
            base_url=s.embedding_base_url, api_key=s.embedding_api_key, timeout=timeout_s, max_retries=1
        )

    def query_text(self, q: str) -> str:
        return f"task: search result | query: {q}" if _is_gemini(self.model) else q

    def doc_text(self, title: str, text: str) -> str:
        return f"title: {title} | text: {text}" if _is_gemini(self.model) else text

    async def _call(self, texts: list[str]) -> list[list[float]]:
        r = await self.client.embeddings.create(model=self.model, input=texts)
        vecs = [d.embedding for d in sorted(r.data, key=lambda d: d.index)]
        if len(vecs) != len(texts):
            raise RuntimeError(f"embedding count mismatch: {len(vecs)} != {len(texts)}")
        return vecs

    async def embed_query(self, text: str) -> list[float]:
        return (await self._call([self.query_text(text)]))[0]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        size = BATCH if self.batch else 1
        chunks = [texts[i : i + size] for i in range(0, len(texts), size)]
        sem = asyncio.Semaphore(PARALLEL)

        async def one(chunk: list[str]) -> list[list[float]]:
            async with sem:
                for attempt in range(3):
                    try:
                        return await self._call(chunk)
                    except Exception:
                        if attempt == 2:
                            raise
                        await asyncio.sleep(1 + attempt)
                raise AssertionError

        out: list[list[float]] = []
        for part in await asyncio.gather(*(one(c) for c in chunks)):
            out.extend(part)
        return out


async def embed_products() -> None:
    s = get_settings()
    emb = Embedder(timeout_s=30)
    with psycopg.connect(s.database_url) as conn:
        register_vector(conn)
        rows = conn.execute(
            "SELECT product, product_name, product_category FROM products ORDER BY product"
        ).fetchall()
        texts = [emb.doc_text(name or "none", f"{prod}. Категория: {cat}") for prod, name, cat in rows]
        vecs = await emb.embed_documents(texts)
        with conn.transaction(), conn.cursor() as cur:
            cur.executemany(
                "UPDATE products SET embedding = %s::vector, embedding_model = %s WHERE product = %s",
                [(v, emb.model, r[0]) for v, r in zip(vecs, rows, strict=True)],
            )
        n = conn.execute("SELECT count(*) FROM products WHERE embedding_model = %s", (emb.model,)).fetchone()
    print(f"embedded {n[0] if n else 0} products with {emb.model} (dim {len(vecs[0])})")
