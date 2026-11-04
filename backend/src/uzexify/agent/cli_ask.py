import json

from uzexify.agent import answer_question
from uzexify.agent.runtime import close_runtime


async def _print_event(e: dict) -> None:
    print(f"  · {e['label_ru']}", flush=True)


async def ask_cli(question: str, as_json: bool = False) -> None:
    try:
        res = await answer_question(question, channel="cli", on_event=None if as_json else _print_event)
    finally:
        await close_runtime()
    if as_json:
        print(json.dumps(res.model_dump(), ensure_ascii=False, indent=2))
        return
    print(f"\n[{res.kind}] {res.text}\n")
    for e in res.entities:
        print(
            f"entity {e.kind} «{e.query}»: "
            + ", ".join(f"{m.id} {m.label} ({m.score})" for m in e.matches[:5])
        )
    for ev in res.evidence:
        print(f"-- {ev.sql_id}: {ev.purpose} ({ev.row_count} rows, {ev.duration_ms} ms)\n{ev.sql}")
        for r in ev.rows[:5]:
            print("   ", r)
    print(f"\n{res.duration_ms / 1000:.1f} s · {res.model}")
