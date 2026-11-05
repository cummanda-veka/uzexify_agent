"""Run multi-turn dialogs (evals/dialogs.yaml) against the local agent.

Each scenario keeps one session, so follow-ups depend on conversation memory. Checks per turn:
answer kind, required words, an attached chart where asked, and the script of the answer.
Usage: uv run python -m evals.dialog_run [--only id,...] [--label NAME]
"""

import argparse
import asyncio
import json
import re
from datetime import date
from pathlib import Path

import yaml

from uzexify.agent import answer_question
from uzexify.agent.runtime import close_runtime

HERE = Path(__file__).parent


def _script(text: str) -> str:
    cyr = len(re.findall(r"[А-Яа-яЁёЎўҚқҒғҲҳ]", text))
    lat = len(re.findall(r"[A-Za-z]", text))
    return "cyrl" if cyr > lat else "latn"


async def run_dialog(dialog: dict) -> dict:
    session = f"dialog:{dialog['id']}:{date.today().isoformat()}"
    turns = []
    for i, turn in enumerate(dialog["turns"], 1):
        res = await answer_question(turn["q"], session_id=session, channel="eval")
        problems = []
        if res.kind != turn.get("expect", "answer"):
            problems.append(f"kind {res.kind} (expected {turn.get('expect', 'answer')})")
        for word in turn.get("must", []):
            if word.casefold() not in res.text.casefold():
                problems.append(f"missing «{word}»")
        if turn.get("chart") and not res.charts:
            problems.append("no chart")
        if turn.get("script") and _script(res.text) != turn["script"]:
            problems.append(f"script {_script(res.text)} (expected {turn['script']})")
        turns.append(
            {
                "turn": i,
                "q": turn["q"],
                "kind": res.kind,
                "text": res.text,
                "sql": [e.purpose for e in res.evidence],
                "charts": len(res.charts),
                "seconds": round(res.duration_ms / 1000, 1),
                "problems": problems,
            }
        )
        mark = "ok" if not problems else "FAIL " + "; ".join(problems)
        print(f"\n[{dialog['id']} #{i}] {turn['q']}\n  → {res.kind}, {res.duration_ms / 1000:.1f}s, {mark}")
        print("  " + res.text.replace("\n", "\n  "))
    return {"id": dialog["id"], "turns": turns}


async def main(args) -> None:
    dialogs = yaml.safe_load((HERE / "dialogs.yaml").read_text())
    if args.only:
        dialogs = [d for d in dialogs if d["id"] in args.only.split(",")]
    try:
        results = await asyncio.gather(*(run_dialog(d) for d in dialogs))
    finally:
        await close_runtime()
    failed = sum(bool(t["problems"]) for r in results for t in r["turns"])
    total = sum(len(r["turns"]) for r in results)
    print(f"\n{total - failed}/{total} turns passed")
    out = HERE / "reports" / f"dialogs-{date.today().isoformat()}-{args.label}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"Report: {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--only")
    p.add_argument("--label", default="run")
    asyncio.run(main(p.parse_args()))
