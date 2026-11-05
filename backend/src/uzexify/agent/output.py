import re
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_ai import ModelRetry, RunContext

from uzexify.agent.deps import AgentDeps, EvidenceLog
from uzexify.numbers import extract_numbers, is_grounded
from uzexify.typograph import typograph


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


_SCALE_WORD = re.compile(r"(?<!\w)(тыс\.|млн|млрд|трлн|ming|mln|mlrd|trln)(?!\w)", re.IGNORECASE)


def scale_table_cells(text: str) -> str:
    """Append the scale named in a table header ("Сумма, трлн сумов") to that column's numeric cells,
    so "13,16" under it is checked as 13,16 trillion."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if not (
            line.lstrip().startswith("|")
            and i + 1 < len(lines)
            and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1])
        ):
            continue
        scales = [(m[1] if (m := _SCALE_WORD.search(h)) else "") for h in line.strip().strip("|").split("|")]
        j = i + 2
        while j < len(lines) and lines[j].lstrip().startswith("|"):
            cells = lines[j].strip().strip("|").split("|")
            cells = [
                f"{c.strip()} {s}" if s and re.fullmatch(r"\s*-?[\d\s\u00a0]+(?:,\d+)?\s*", c) else c
                for c, s in zip(cells, scales + [""] * len(cells))
            ]
            lines[j] = "| " + " | ".join(cells) + " |"
            j += 1
    return "\n".join(lines)


def ungrounded(text: str, question: str, ev: EvidenceLog) -> list[str]:
    nums = evidence_numbers(ev)
    return [
        n.raw for n in extract_numbers(scale_table_cells(text), question=question) if not is_grounded(n, nums)
    ]


def data_strings(ev: EvidenceLog) -> list[str]:
    """Names and codes copied from the data; typography must not touch them."""
    out = [str(m.get("label", "")) for e in ev.entities for m in e.matches]
    out += [c for r in ev.sql for row in r.rows for c in row if isinstance(c, str)]
    return out


_CODE_TOKEN = re.compile(r"[^\W\d_]*\d[\w‘’'-]*", re.UNICODE)


def stray_numbers(text: str, question: str, ev: EvidenceLog) -> list[str]:
    """Numbers in short UI text (chart title, legend) that are not grounded. Whole digit-bearing
    tokens copied from data names ("АИ-92", "М00к") are masked first, so a product can be named;
    a number merely appearing inside such a token ("2" in "АИ-92") is not an exemption."""
    tokens = {t for s in data_strings(ev) for t in _CODE_TOKEN.findall(s) if not t.isdigit()}
    for token in sorted(tokens, key=len, reverse=True):
        text = re.sub(rf"(?<![\w-]){re.escape(token)}(?![\w-])", " ", text)
    return ungrounded(text, question, ev)


async def validate_answer(ctx: RunContext[AgentDeps], out: Answer) -> Answer:
    ev = ctx.deps.evidence
    if out.kind == "answer" and not ev.sql:
        raise ModelRetry("kind='answer' requires at least one successful run_sql call in this run.")
    out.text = typograph(out.text, out.language, out.script, data_strings(ev))
    bad = ungrounded(out.text, ctx.deps.question, ev)
    if bad:
        raise ModelRetry(
            "Числа не найдены в результатах SQL: "
            + ", ".join(bad[:10])
            + ". Compute them with a run_sql query (ROUND in SQL) or remove them from the text."
        )
    return out
