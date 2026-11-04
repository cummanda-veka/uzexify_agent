"""Deterministic evaluators shared by the report and Pydantic Evals."""

import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from uzexify.numbers import extract_numbers, is_grounded
from uzexify.text import name_key


def _kind(case, result):
    return result["kind"] == case["expect_kind"]


def _values(case, result):
    if case["expect_kind"] != "answer":
        return True
    numbers = extract_numbers(result["text"])
    normalized = name_key(result["text"])
    for check in case.get("checks", []):
        for row in case["reference_rows"]:
            value = row[check["column"]]
            if value is None:
                return False
            if check["match"] == "number":
                try:
                    expected = Decimal(str(value))
                except InvalidOperation:
                    return False
                if not any(is_grounded(number, [expected]) for number in numbers):
                    return False
            elif check["match"] == "text":
                expected = name_key(str(value))
                if not expected or expected not in normalized:
                    return False
            else:
                raise ValueError(f"Unknown check type: {check['match']}")
    return bool(case["reference_rows"])


def _no_fabricated(case, result):
    if case["expect_kind"] not in ("no_data", "clarify"):
        return True
    return not extract_numbers(result["text"], case["question"])


def _data_strings(result) -> list[str]:
    """Names/values copied from the data (company names, regions, addresses) — script-neutral."""
    out = [m["label"] for e in result.get("entities", []) for m in e["matches"]]
    out += [c for ev in result.get("evidence", []) for row in ev["rows"] for c in row if isinstance(c, str)]
    return sorted({s for s in out if len(s) >= 3}, key=len, reverse=True)


def _language(case, result):
    expected = case["lang"]
    if result["language"] != ("ru" if expected == "ru" else "uz"):
        return False
    text = result["text"]
    for s in _data_strings(result):
        text = text.replace(s, " ")
    latin = sum("LATIN" in unicodedata.name(c, "") for c in text if c.isalpha())
    cyrillic = sum("CYRILLIC" in unicodedata.name(c, "") for c in text if c.isalpha())
    return latin > cyrillic if expected == "uz_latn" else cyrillic > latin


def _time(case, result):
    return result["duration_ms"] <= 90_000


SCORERS = {
    "KindMatches": _kind,
    "ExpectedValuesPresent": _values,
    "NoFabricatedNumbers": _no_fabricated,
    "LanguageMatches": _language,
    "WithinTimeLimit": _time,
}


def evaluate_case(case, result):
    return {name: fn(case, result) for name, fn in SCORERS.items()}


@dataclass
class KindMatches(Evaluator):
    def evaluate(self, ctx: EvaluatorContext) -> bool:
        return _kind(ctx.inputs, ctx.output)


@dataclass
class ExpectedValuesPresent(Evaluator):
    def evaluate(self, ctx: EvaluatorContext) -> bool:
        return _values(ctx.inputs, ctx.output)


@dataclass
class NoFabricatedNumbers(Evaluator):
    def evaluate(self, ctx: EvaluatorContext) -> bool:
        return _no_fabricated(ctx.inputs, ctx.output)


@dataclass
class LanguageMatches(Evaluator):
    def evaluate(self, ctx: EvaluatorContext) -> bool:
        return _language(ctx.inputs, ctx.output)


@dataclass
class WithinTimeLimit(Evaluator):
    def evaluate(self, ctx: EvaluatorContext) -> bool:
        return _time(ctx.inputs, ctx.output)
