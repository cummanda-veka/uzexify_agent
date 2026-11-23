"""Offline-labelled retrieval benchmark. Run from backend: python -m evals.retrieval.

Product labels are groups of canonical product-name substrings; alternatives
within a group are equivalent. Embeddings are never written to the database.
"""

import argparse
import asyncio
import json
import math
import random
from datetime import UTC, datetime
from pathlib import Path

import httpx
import psycopg
import yaml

from uzexify.embeddings import Embedder
from uzexify.search import RRF_K, _lexical, search_companies
from uzexify.settings import get_settings
from uzexify.text import name_key, product_key, to_latin

HERE = Path(__file__).resolve().parent
# Embedding variants call EMBEDDING_BASE_URL with the model below; run each provider with its own env.
MODELS = {
    "gemini": "google/gemini-embedding-2",
    "voyage": "mongodb/voyage-4-large",
    "gemini-direct": "gemini-embedding-2-preview",
    "cf-bge-m3": "@cf/baai/bge-m3",
    "cf-qwen3": "@cf/qwen/qwen3-embedding-0.6b",
}
VARIANTS = ("lexical", *(f"hybrid-{key}" for key in MODELS), "hybrid-gemini+rerank")
NEGATIVES = [
    "Qirxam Zolbex MCHJ",
    "Vunqoz Pellixa XK",
    "Zarvix Kuldon AJ",
    "Fomqir Nultex QK",
    "Jaxvul Pirnex MCHJ",
    "Birqoz Xalvut XK",
    "Nuvqil Zerpax AJ",
    "Talvix Qurfon QK",
    "Yorqex Bulzan MCHJ",
    "Pavqir Xenzul XK",
]


def metrics(ranks: list[int | None]) -> dict:
    return {
        "count": len(ranks),
        "recall@5": sum(rank is not None and rank <= 5 for rank in ranks) / len(ranks) if ranks else None,
        "mrr@10": sum(1 / rank for rank in ranks if rank is not None and rank <= 10) / len(ranks)
        if ranks
        else None,
    }


def product_metrics(rows: list[dict]) -> dict:
    successful = [row for row in rows if "error" not in row]
    result = metrics([row["rank"] for row in successful])
    result["recall@5"] = sum(row["recall@5"] for row in successful) / len(successful) if successful else None
    result["errors"] = len(rows) - len(successful)
    return result


def company_cases(rows: list[tuple[str, str]]) -> list[dict]:
    rng = random.Random(42)
    cases = []
    for inn, name in rng.sample(rows, min(40, len(rows))):
        latin = to_latin(name.casefold())
        stripped = name_key(name)
        # A single deletion tests a typo independently of case and legal form.
        chars = [i for i, char in enumerate(stripped) if char.isalpha()]
        typo = (
            stripped[: chars[len(chars) // 2]] + stripped[chars[len(chars) // 2] + 1 :] if chars else stripped
        )
        for kind, query in (
            ("script_swap", latin),
            ("lowercase", name.lower()),
            ("no_legal_form", stripped),
            ("typo", typo),
        ):
            cases.append({"query": query, "expected_inn": inn, "variant": kind})
    cases.extend({"query": name, "expected_inn": None, "variant": "negative"} for name in NEGATIVES)
    return cases


def product_scores(labels: list[str], expected: list) -> tuple[int | None, float]:
    groups = [
        [value.casefold() for value in (item if isinstance(item, list) else [item])] for item in expected
    ]
    matches = [
        next(
            (i for i, label in enumerate(labels, 1) if any(value in label.casefold() for value in group)),
            None,
        )
        for group in groups
    ]
    rank = min((rank for rank in matches if rank is not None), default=None)
    return rank, sum(rank is not None and rank <= 5 for rank in matches) / len(groups)


def cosine(a: list[float], norm_a: float, b: list[float], norm_b: float) -> float:
    if not norm_a or not norm_b:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True)) / (norm_a * norm_b)


def fuse(*ranked: list[str]) -> list[str]:
    scores: dict[str, float] = {}
    for ranking in ranked:
        for rank, product in enumerate(ranking, 1):
            scores[product] = scores.get(product, 0.0) + 1 / (RRF_K + rank)
    return sorted(scores, key=lambda product: (-scores[product], product))


async def rerank(client: httpx.AsyncClient, query: str, products: list[str], api_key: str) -> list[str]:
    if not products:
        return []
    response = await client.post(
        "https://openrouter.ai/api/v1/rerank",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": "cohere/rerank-5-fast", "query": query, "documents": products, "top_n": 15},
    )
    response.raise_for_status()
    return [products[item["index"]] for item in response.json()["results"]]


async def run(variants: list[str], output: Path) -> None:
    settings = get_settings()
    with (HERE / "products.yaml").open(encoding="utf-8") as f:
        cases = yaml.safe_load(f)
    skipped = {}
    if "hybrid-gemini+rerank" in variants and not settings.openrouter_api_key:
        variants = [v for v in variants if v != "hybrid-gemini+rerank"]
        skipped["hybrid-gemini+rerank"] = "OPENROUTER_API_KEY is not configured"

    async with await psycopg.AsyncConnection.connect(settings.database_url) as conn:
        products = await (
            await conn.execute(
                "SELECT product, product_name, product_category FROM products ORDER BY product"
            )
        ).fetchall()
        participants = await (
            await conn.execute("SELECT inn, name FROM participants ORDER BY inn")
        ).fetchall()
        if not products or len(participants) < 40:
            raise RuntimeError("Benchmark requires products and at least 40 participants in the database")
        metadata = {product: name or "" for product, name, _ in products}
        company_results = []
        for case in company_cases(participants):
            hits = await search_companies(conn, case["query"], limit=10)
            rank = next((i for i, hit in enumerate(hits, 1) if hit.inn == case["expected_inn"]), None)
            company_results.append(
                {
                    **case,
                    "rank": rank,
                    "hits": [
                        {"inn": hit.inn, "name": hit.name, "score": hit.score, "confident": hit.confident}
                        for hit in hits
                    ],
                }
            )
        positives = [r for r in company_results if r["expected_inn"] is not None]
        negatives = [r for r in company_results if r["expected_inn"] is None]
        company_summary = metrics([r["rank"] for r in positives])
        company_summary["false_match_rate"] = sum(
            any(hit["confident"] for hit in r["hits"]) for r in negatives
        ) / len(negatives)
        company_summary["confidence_threshold"] = settings.company_match_min_score
        company_summary["by_variant"] = {
            kind: metrics([r["rank"] for r in positives if r["variant"] == kind])
            for kind in ("script_swap", "lowercase", "no_legal_form", "typo")
        }

        models_needed = {
            v.removeprefix("hybrid-").removesuffix("+rerank") for v in variants if v.startswith("hybrid-")
        }
        vectors = {}
        embedders = {}
        model_errors = {}
        for key in sorted(models_needed):
            try:
                emb = Embedder(model=MODELS[key], timeout_s=30)
                texts = [
                    emb.doc_text(name or "none", f"{product}. Категория: {category}")
                    for product, name, category in products
                ]
                docs = await emb.embed_documents(texts)
                vectors[key] = [
                    (row[0], vector, math.sqrt(sum(x * x for x in vector)))
                    for row, vector in zip(products, docs, strict=True)
                ]
                embedders[key] = emb
            except Exception as exc:
                model_errors[key] = f"{type(exc).__name__}: {exc}"

        results = {variant: [] for variant in variants}
        async with httpx.AsyncClient(timeout=30) as client:
            for case in cases:
                query = case["query"]
                lexical = [p for p, _ in await _lexical(conn, product_key(query), n=30)]
                rankings = {"lexical": lexical}
                errors = {}
                for key in sorted(models_needed):
                    try:
                        if key in model_errors:
                            raise RuntimeError(model_errors[key])
                        vector = await embedders[key].embed_query(query)
                        query_norm = math.sqrt(sum(x * x for x in vector))
                        scored = sorted(
                            (
                                (cosine(vector, query_norm, doc, norm), product)
                                for product, doc, norm in vectors[key]
                            ),
                            key=lambda item: (-item[0], item[1]),
                        )
                        rankings[f"hybrid-{key}"] = fuse(lexical, [p for _, p in scored[:30]])
                    except Exception as exc:
                        errors[f"hybrid-{key}"] = f"{type(exc).__name__}: {exc}"
                if "hybrid-gemini+rerank" in variants:
                    try:
                        if "hybrid-gemini" in errors:
                            raise RuntimeError(errors["hybrid-gemini"])
                        rankings["hybrid-gemini+rerank"] = await rerank(
                            client, query, rankings["hybrid-gemini"][:30], settings.openrouter_api_key
                        )
                    except Exception as exc:
                        errors["hybrid-gemini+rerank"] = f"{type(exc).__name__}: {exc}"
                for variant in variants:
                    if variant in errors:
                        results[variant].append({**case, "error": errors[variant]})
                        continue
                    ranked = rankings[variant][:15]
                    rank, recall = product_scores([metadata[product] for product in ranked], case["expected"])
                    results[variant].append(
                        {
                            **case,
                            "rank": rank,
                            "recall@5": recall,
                            "hits": [
                                {"product": product, "product_name": metadata[product]} for product in ranked
                            ],
                        }
                    )

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "models": {key: MODELS[key] for key in sorted(models_needed)},
        "product_label_semantics": "Recall averages the fraction of expected label groups found in top 5; alternatives within groups are equivalent. MRR uses the first relevant hit.",
        "products": {
            variant: {"metrics": product_metrics(rows), "cases": rows} for variant, rows in results.items()
        },
        "companies": {"metrics": company_summary, "cases": company_results},
        "skipped": skipped,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{'Variant':24} {'Recall@5':>10} {'MRR@10':>10} {'Errors':>8}")
    for variant, item in report["products"].items():
        result = item["metrics"]
        recall = f"{result['recall@5']:.3f}" if result["recall@5"] is not None else "n/a"
        mrr = f"{result['mrr@10']:.3f}" if result["mrr@10"] is not None else "n/a"
        print(f"{variant:24} {recall:>10} {mrr:>10} {result['errors']:8}")
    print(
        f"Companies: recall@5={company_summary['recall@5']:.3f}, "
        f"MRR@10={company_summary['mrr@10']:.3f}, "
        f"false-match rate={company_summary['false_match_rate']:.3f}"
    )
    for variant, reason in skipped.items():
        print(f"{variant}: skipped ({reason})")
    print(f"Saved retrieval report to {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variants", default=",".join(VARIANTS), help="Comma-separated retrieval variants")
    parser.add_argument("--output", type=Path, default=HERE / "reports" / "retrieval.json")
    args = parser.parse_args()
    variants = list(dict.fromkeys(part.strip() for part in args.variants.split(",") if part.strip()))
    if not variants or any(variant not in VARIANTS for variant in variants):
        parser.error(f"--variants must contain only: {', '.join(VARIANTS)}")
    asyncio.run(run(variants, args.output))


if __name__ == "__main__":
    main()
