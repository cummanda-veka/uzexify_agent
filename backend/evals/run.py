"""Run the golden dataset locally or against the HTTP API."""

import argparse
import asyncio
import json
import math
import os
import re
import statistics
import time
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path

import httpx
import psycopg
import yaml
from psycopg.rows import dict_row
from pydantic_evals import Case, Dataset

from evals.scorers import (
    ExpectedValuesPresent,
    KindMatches,
    LanguageMatches,
    NoFabricatedNumbers,
    WithinTimeLimit,
    evaluate_case,
)
from uzexify import observability
from uzexify.settings import get_settings

HERE = Path(__file__).resolve().parent


def percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def load_cases():
    cases = yaml.safe_load((HERE / "golden.yaml").read_text(encoding="utf-8"))
    if isinstance(cases, dict):
        cases = cases["cases"]
    with psycopg.connect(get_settings().database_url, row_factory=dict_row) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        for case in cases:
            case["reference_rows"] = []
            if case["expect_kind"] == "answer":
                rows = conn.execute(case["reference_sql"]).fetchall()
                if not rows:
                    raise ValueError(f"Reference SQL returned no rows: {case['id']}")
                for check in case["checks"]:
                    if check["column"] not in rows[0]:
                        raise ValueError(f"Unknown reference column {check['column']} in {case['id']}")
                case["reference_rows"] = rows
    return cases


def summary(rows):
    answers = [r for r in rows if r["expected_kind"] == "answer"]
    refusals = [r for r in rows if r["expected_kind"] == "no_data"]
    clarifications = [r for r in rows if r["expected_kind"] == "clarify"]

    def accuracy(group, pred):
        return {"passed": sum(pred(r) for r in group), "total": len(group)}

    return {
        "answer_accuracy": accuracy(answers, lambda r: r["correct"]),
        "unsafe_no_data": sum(
            r["result"]["kind"] not in ("no_data", "error") or not r["scores"]["NoFabricatedNumbers"]
            for r in refusals
        ),
        "no_data_total": len(refusals),
        "clarify_accuracy": accuracy(clarifications, lambda r: r["correct"]),
        "language": accuracy(rows, lambda r: r["scores"]["LanguageMatches"]),
        "p50_ms": statistics.median([r["result"]["duration_ms"] for r in rows]) if rows else None,
        "p95_ms": percentile([r["result"]["duration_ms"] for r in rows], 0.95),
        "cost": None,
    }


async def run(args):
    if args.model:
        if args.target != "local":
            raise ValueError("--model is supported only for --target local")
        os.environ["LLM_MODEL"] = args.model
        get_settings.cache_clear()
    cases = load_cases()
    tracing = observability.init_tracing()
    results = {}
    async with httpx.AsyncClient(timeout=100) as client:

        async def task(case):
            started = time.perf_counter()
            try:
                if args.target == "local":
                    from uzexify.agent import answer_question

                    if tracing:
                        from langfuse import propagate_attributes

                        tags = propagate_attributes(tags=["eval", case["id"]])
                    else:
                        tags = nullcontext()
                    with tags:
                        result = (
                            await answer_question(
                                case["question"], session_id="eval:" + case["id"], channel="eval"
                            )
                        ).model_dump(mode="json")
                else:
                    response = await client.post(
                        args.base_url.rstrip("/") + "/api/ask",
                        json={"question": case["question"], "session_id": "eval:" + case["id"]},
                        headers={"X-Client": "eval"},
                    )
                    response.raise_for_status()
                    result = response.json()
            except Exception as exc:
                result = {
                    "kind": "error",
                    "language": "ru" if case["lang"] == "ru" else "uz",
                    "text": "",
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                    "error": f"{type(exc).__name__}: {exc}",
                    "trace_id": None,
                }
            scores = evaluate_case(case, result)
            correct = all(scores.values())
            if result.get("trace_id"):
                observability.score(result["trace_id"], "correct", float(correct))
            results[case["id"]] = {
                "id": case["id"],
                "question": case["question"],
                "expected_kind": case["expect_kind"],
                "scores": scores,
                "correct": correct,
                "result": result,
                "reference_rows": case["reference_rows"],
            }
            return result

        dataset = Dataset(
            name="uzexify-golden",
            cases=[Case(name=c["id"], inputs=c) for c in cases],
            evaluators=[
                KindMatches(),
                ExpectedValuesPresent(),
                NoFabricatedNumbers(),
                LanguageMatches(),
                WithinTimeLimit(),
            ],
        )
        try:
            report = await dataset.evaluate(task, max_concurrency=args.concurrency)
            report.print()
        finally:
            if args.target == "local":
                from uzexify.agent.runtime import close_runtime

                await close_runtime()
            observability.flush()
    rows = [results[c["id"]] for c in cases if c["id"] in results]
    totals = summary(rows)
    print(json.dumps(totals, ensure_ascii=False, indent=2))
    directory = HERE / "reports"
    directory.mkdir(exist_ok=True)
    label = re.sub(r"[^\w.-]+", "-", args.label).strip(".-") or "run"
    path = directory / f"{datetime.now(UTC):%Y-%m-%d}-{label}.json"
    payload = {
        "target": args.target,
        "model_override": args.model,
        "label": args.label,
        "created_at": datetime.now(UTC).isoformat(),
        "summary": totals,
        "cases": rows,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Report: {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("local", "http"), required=True)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--model")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    if args.concurrency < 1:
        parser.error("--concurrency must be positive")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
