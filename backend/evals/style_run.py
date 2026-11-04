"""Style benchmark: run the style question set, lint every answer, and have a judge model grade it.

    uv run python -m evals.style_run --label v1 [--model ID] [--judge ID] [--only s_ru_01,...]

Report: evals/reports/style-<label>.json, plus a console summary with per-rule counts and the
weakest answers. Correctness is measured by evals.run; this measures how answers read.
"""

import argparse
import asyncio
import json
import os
import statistics
from collections import Counter
from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_ai import Agent, PromptedOutput

from evals.style_lint import lint
from uzexify.settings import get_settings

HERE = Path(__file__).parent
JUDGE_MODEL = "cpa-coolthings/claude-opus-5-5"

RUBRIC = """You are a senior editor of a business news desk, a native reader of Russian and Uzbek (Latin
and Cyrillic). A chatbot answered a user's question about exchange-deal statistics. Judge how well the
answer serves that reader as writing; facts were checked elsewhere, so do not judge the numbers.

Read it as the user would and ask: does it answer the question at once and clearly, in natural,
idiomatic language of the question's script, at a length and shape that suit the content? Would you
publish it as-is, after a light edit, or would you rewrite it?

Score 1–10: 10 — you would publish it unchanged; 8–9 — a light edit you might or might not bother
with; 6–7 — noticeable problems a reader would feel; ≤5 — confusing, wrong language, or unhelpful.

Report only issues a reader would actually notice (unclear meaning, awkward or unnatural phrasing,
ambiguity about what a number covers, missing part of the answer, clutter, wrong register). Do not
list matters of taste or alternative phrasings of something already fine. Quote the fragment and give
the fix. Empty list if none.

House conventions, which are correct: "25 %" with a space; spaces in digit groups (NBSP); names of
companies and products exactly as in the registry, including their quotes, script and Uzbek
apostrophes (‘ in o‘/g‘, ’ for tutuq)."""


class Verdict(BaseModel):
    score: int = Field(ge=1, le=10)
    issues: list[str]


def protected_strings(result: dict) -> list[str]:
    out = [m["label"] for e in result.get("entities", []) for m in e["matches"]]
    out += [c for ev in result.get("evidence", []) for row in ev["rows"] for c in row if isinstance(c, str)]
    return out


async def run(args) -> None:
    if args.model:
        os.environ["LLM_MODEL"] = args.model
        get_settings.cache_clear()
    from uzexify.agent import answer_question
    from uzexify.agent.models import build_model

    cases = yaml.safe_load((HERE / "style.yaml").read_text(encoding="utf-8"))["cases"]
    if args.only:
        wanted = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    # PromptedOutput: Opus via the gateway rejects forced tool_choice, so ask for JSON instead.
    judge = Agent(build_model(args.judge), output_type=PromptedOutput(Verdict), instructions=RUBRIC)
    sem = asyncio.Semaphore(args.concurrency)

    async def one(case: dict) -> dict:
        async with sem:
            res = (
                await answer_question(case["question"], session_id="style:" + case["id"], channel="eval")
            ).model_dump(mode="json")
            expect = case.get("expect_kind", "answer")
            issues = lint(res["text"], case["lang"], res["kind"], protected_strings(res))
            if res["kind"] != expect:
                issues.append(f"kind: {res['kind']} (expected {expect})")
            charts = len(res.get("charts") or [])
            prompt = (
                f"Question ({case['lang']}): {case['question']}\n"
                f"Answer kind: {res['kind']}; charts attached: {charts}\n\nAnswer:\n{res['text']}"
            )
            try:
                verdict = (await judge.run(prompt)).output
            except Exception as e:  # judge failure must not hide the lint result
                verdict = Verdict(score=1, issues=[f"judge error: {type(e).__name__}"])
            return {
                "id": case["id"],
                "lang": case["lang"],
                "question": case["question"],
                "kind": res["kind"],
                "text": res["text"],
                "charts": charts,
                "duration_ms": res["duration_ms"],
                "lint": issues,
                "score": verdict.score,
                "judge": verdict.issues,
            }

    rows = await asyncio.gather(*(one(c) for c in cases))
    scores = [r["score"] for r in rows]
    rules = Counter(i.split(":")[0] for r in rows for i in r["lint"])
    summary = {
        "cases": len(rows),
        "lint_clean": sum(not r["lint"] for r in rows),
        "lint_rules": dict(rules.most_common()),
        "judge_mean": round(statistics.mean(scores), 2),
        "judge_min": min(scores),
        "judge_ge9": sum(s >= 9 for s in scores),
        "p95_ms": sorted(r["duration_ms"] for r in rows)[int(0.95 * (len(rows) - 1))],
    }
    out = HERE / "reports" / f"style-{date.today().isoformat()}-{args.label}.json"
    out.write_text(
        json.dumps({"summary": summary, "cases": rows}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for r in sorted(rows, key=lambda r: (r["score"], -len(r["lint"])))[: args.show]:
        print(f"\n=== {r['id']} score={r['score']} lint={r['lint']}\nQ: {r['question']}\nA: {r['text']}")
        for i in r["judge"]:
            print(f"   - {i}")
    print(f"\nReport: {out}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--label", required=True)
    p.add_argument("--model")
    p.add_argument("--judge", default=JUDGE_MODEL)
    p.add_argument("--only")
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--show", type=int, default=12)
    asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    main()
