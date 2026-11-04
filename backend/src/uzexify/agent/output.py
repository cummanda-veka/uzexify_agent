from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_ai import ModelRetry, RunContext

from uzexify.agent.deps import AgentDeps, EvidenceLog
from uzexify.numbers import extract_numbers, is_grounded


class Answer(BaseModel):
    kind: Literal["answer", "no_data", "clarify"]
    language: Literal["ru", "uz"]
    script: Literal["latn", "cyrl"]
    text: str = Field(description="Final answer text for the user, in the question's language and script.")
    sql_ids: list[str] = Field(default_factory=list, description="sql_id values of run_sql results used.")


def _to_dec(v: Any) -> Decimal | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    if isinstance(v, str):
        s = v.replace(" ", "").replace("\u00a0", "")
        if s and len(s) <= 40:
            try:
                return Decimal(s)
            except InvalidOperation:
                return None
    return None


def evidence_numbers(ev: EvidenceLog) -> set[Decimal]:
    out: set[Decimal] = set()

    def add(v: Any) -> None:
        d = _to_dec(v)
        if d is not None:
            out.add(d)
        elif isinstance(v, str):
            for n in extract_numbers(v):
                out.add(n.value)

    for r in ev.sql:
        out.add(Decimal(r.row_count))
        for row in r.rows:
            for c in row:
                add(c)
    for e in ev.entities:
        out.add(Decimal(len(e.matches)))
        for m in e.matches:
            for v in m.values():
                add(v)
    return out


def ungrounded(text: str, question: str, ev: EvidenceLog) -> list[str]:
    nums = evidence_numbers(ev)
    return [n.raw for n in extract_numbers(text, question=question) if not is_grounded(n, nums)]


async def validate_answer(ctx: RunContext[AgentDeps], out: Answer) -> Answer:
    ev = ctx.deps.evidence
    if out.kind == "answer" and not ev.sql:
        raise ModelRetry("kind='answer' requires at least one successful run_sql call in this run.")
    bad = ungrounded(out.text, ctx.deps.question, ev)
    if bad:
        raise ModelRetry(
            "Числа не найдены в результатах SQL: "
            + ", ".join(bad[:10])
            + ". Compute them with a run_sql query (ROUND in SQL) or remove them from the text."
        )
    return out
