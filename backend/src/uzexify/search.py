"""Entity resolution: companies, brokers (lexical) and products (hybrid lexical + vector, RRF)."""

import asyncio
import datetime as dt
import logging
import re
from dataclasses import dataclass
from typing import Literal, LiteralString, cast

from psycopg import AsyncConnection

from uzexify.embeddings import REQUEST_TIMEOUT_S, Embedder
from uzexify.settings import get_settings
from uzexify.text import name_key, product_key

log = logging.getLogger(__name__)
MIN_SCORE = 0.3
RRF_K = 60

Role = Literal["any", "seller", "buyer"]


@dataclass
class CompanyHit:
    inn: str
    name: str
    region: str | None
    role: str | None
    n_deals_sold: int
    n_deals_bought: int
    score: float
    confident: bool


@dataclass
class BrokerHit:
    code: str
    name: str
    inn: str | None
    region: str | None
    n_deals: int
    score: float
    confident: bool


@dataclass
class ProductHit:
    product: str
    product_name: str | None
    category: str | None
    unit: str | None
    n_deals: int
    first_deal: dt.date | None
    last_deal: dt.date | None
    lexical_score: float | None
    vector_similarity: float | None
    rrf: float


_ROLE_FILTER = {"any": "", "seller": "AND n_deals_sold > 0", "buyer": "AND n_deals_bought > 0"}


async def search_companies(
    conn: AsyncConnection, query: str, role: Role = "any", limit: int = 8
) -> list[CompanyHit]:
    min_conf = get_settings().company_match_min_score
    q = query.strip()
    cols = "inn, name, region_uz, role, n_deals_sold, n_deals_bought"
    if re.fullmatch(r"\d{9}", q):
        rows = await (
            await conn.execute(f"SELECT {cols}, 1.0 FROM participants WHERE inn = %s", (q,))
        ).fetchall()
    else:
        k = name_key(q)
        if not k:
            return []
        sql = cast(
            LiteralString,
            f"""SELECT {cols}, greatest(similarity(name_key, %(k)s), word_similarity(%(k)s, name_key)) AS s
                FROM participants
                WHERE (name_key %% %(k)s OR %(k)s <%% name_key) {_ROLE_FILTER[role]}
                ORDER BY s DESC, n_deals_sold + n_deals_bought DESC LIMIT %(lim)s""",
        )
        rows = await (await conn.execute(sql, {"k": k, "lim": limit * 3})).fetchall()
    hits = [
        CompanyHit(
            r[0], r[1], r[2], r[3], r[4] or 0, r[5] or 0, round(float(r[6]), 3), float(r[6]) >= min_conf
        )
        for r in rows
        if float(r[6]) >= MIN_SCORE
    ]
    return hits[:limit]


async def search_brokers(conn: AsyncConnection, query: str, limit: int = 5) -> list[BrokerHit]:
    min_conf = get_settings().company_match_min_score
    q = query.strip()
    cols = "code, name, inn, region_uz, n_deals"
    if re.fullmatch(r"(?i)bk\d{3}", q):
        rows = await (
            await conn.execute(f"SELECT {cols}, 1.0 FROM brokers WHERE upper(code) = upper(%s)", (q,))
        ).fetchall()
    else:
        k = name_key(q)
        if not k:
            return []
        rows = await (
            await conn.execute(
                f"""SELECT {cols}, greatest(similarity(name_key, %(k)s), word_similarity(%(k)s, name_key)) AS s
                    FROM brokers ORDER BY s DESC LIMIT %(lim)s""",
                {"k": k, "lim": limit},
            )
        ).fetchall()
    return [
        BrokerHit(r[0], r[1], r[2], r[3], r[4] or 0, round(float(r[5]), 3), float(r[5]) >= min_conf)
        for r in rows
        if float(r[5]) >= MIN_SCORE
    ]


async def _lexical(conn: AsyncConnection, key: str, n: int = 20) -> list[tuple[str, float]]:
    if not key:
        return []
    rows = await (
        await conn.execute(
            """SELECT product, greatest(similarity(name_key, %(k)s), word_similarity(%(k)s, name_key)) AS s
               FROM products ORDER BY s DESC LIMIT %(n)s""",
            {"k": key, "n": n},
        )
    ).fetchall()
    return [(r[0], float(r[1])) for r in rows if float(r[1]) >= 0.2]


async def _vector(conn: AsyncConnection, vec: list[float], n: int = 20) -> list[tuple[str, float]]:
    rows = await (
        await conn.execute(
            """SELECT product, 1 - (embedding <=> %s::vector) FROM products
               WHERE embedding IS NOT NULL ORDER BY embedding <=> %s::vector LIMIT %s""",
            (vec, vec, n),
        )
    ).fetchall()
    return [(r[0], float(r[1])) for r in rows]


async def search_products(
    conn: AsyncConnection,
    query: str,
    query_ru: str | None = None,
    embedder: Embedder | None = None,
    limit: int = 15,
) -> list[ProductHit]:
    vec_task = None
    if embedder is not None:
        vec_task = asyncio.create_task(asyncio.wait_for(embedder.embed_query(query), REQUEST_TIMEOUT_S))
    lists: list[list[tuple[str, float]]] = [await _lexical(conn, product_key(query))]
    if query_ru:
        lists.append(await _lexical(conn, product_key(query_ru)))
    lexical = {p: max(s for lst in lists for q, s in lst if q == p) for lst in lists for p, _ in lst}
    vector: dict[str, float] = {}
    if vec_task is not None:
        try:
            vec = await vec_task
            vres = await _vector(conn, vec)
            if vres:
                lists.append(vres)
                vector = dict(vres)
        except Exception as e:  # noqa: BLE001 - degrade to lexical-only
            log.warning("product embedding failed, lexical only: %s", e)

    rrf: dict[str, float] = {}
    for lst in lists:
        for rank, (p, _) in enumerate(lst):
            rrf[p] = rrf.get(p, 0.0) + 1.0 / (RRF_K + rank + 1)
    top = sorted(rrf, key=lambda p: -rrf[p])[:limit]
    if not top:
        return []
    rows = await (
        await conn.execute(
            """SELECT product, product_name, product_category, unit, n_deals, first_deal, last_deal
               FROM products WHERE product = ANY(%s)""",
            (top,),
        )
    ).fetchall()
    meta = {r[0]: r for r in rows}
    return [
        ProductHit(
            product=p,
            product_name=meta[p][1],
            category=meta[p][2],
            unit=meta[p][3],
            n_deals=meta[p][4] or 0,
            first_deal=meta[p][5],
            last_deal=meta[p][6],
            lexical_score=round(lexical[p], 3) if p in lexical else None,
            vector_similarity=round(vector[p], 3) if p in vector else None,
            rrf=round(rrf[p], 5),
        )
        for p in top
        if p in meta
    ]
