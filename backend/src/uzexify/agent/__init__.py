"""Agent entry point: `answer_question`."""

import asyncio
import logging
import time
import uuid
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from typing import Any, Literal

from pydantic import BaseModel
from pydantic_ai import UsageLimits
from pydantic_ai.exceptions import (
    FallbackExceptionGroup,
    ModelAPIError,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
)
from pydantic_ai.messages import FunctionToolCallEvent, FunctionToolResultEvent, ModelMessage
from pydantic_ai.run import AgentRunResultEvent

from uzexify import observability
from uzexify.agent.deps import AgentDeps, EvidenceLog
from uzexify.agent.runtime import get_runtime
from uzexify.settings import get_settings
from uzexify.text import detect_lang

log = logging.getLogger(__name__)

Kind = Literal["answer", "no_data", "clarify", "error"]
EventCb = Callable[[dict[str, Any]], Awaitable[None]]
MAX_SESSIONS = 200


class EvidenceItem(BaseModel):
    sql_id: str
    purpose: str
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    duration_ms: int


class EntityMatch(BaseModel):
    id: str
    label: str
    score: float | None = None


class EntityItem(BaseModel):
    kind: str
    query: str
    matches: list[EntityMatch]


class AskResult(BaseModel):
    id: str
    session_id: str
    question: str
    language: Literal["ru", "uz"]
    kind: Kind
    text: str
    evidence: list[EvidenceItem]
    entities: list[EntityItem]
    model: str
    duration_ms: int
    trace_id: str | None = None
    error_code: Literal["timeout", "unavailable", "internal"] | None = None


class AgentTimeout(Exception):
    pass


_sessions: OrderedDict[str, list[ModelMessage]] = OrderedDict()

MESSAGES = {
    "fallback": {
        "ru": "Не удалось сформулировать проверенный ответ; ниже результат запроса из базы.",
        "uz": "Tekshirilgan javobni shakllantirib bo‘lmadi; quyida bazadan olingan so‘rov natijasi.",
    },
    "internal": {
        "ru": "Не удалось получить проверенный ответ. Попробуйте переформулировать вопрос.",
        "uz": "Tekshirilgan javob olinmadi. Savolni boshqacha yozib ko‘ring.",
    },
    "timeout": {
        "ru": "Превышено время ожидания ответа. Попробуйте упростить вопрос.",
        "uz": "Javob kutish vaqti tugadi. Savolni soddalashtirib ko‘ring.",
    },
    "unavailable": {
        "ru": "Языковая модель сейчас недоступна. Повторите попытку позже.",
        "uz": "Til modeli hozir mavjud emas. Keyinroq qayta urinib ko‘ring.",
    },
}

TOOL_LABELS = {
    "search_companies": ("Ищу компанию: «{q}»", "Kompaniya qidirilmoqda: «{q}»"),
    "search_brokers": ("Ищу брокера: «{q}»", "Broker qidirilmoqda: «{q}»"),
    "search_products": ("Ищу товар: «{q}»", "Tovar qidirilmoqda: «{q}»"),
    "run_sql": ("Выполняю SQL-запрос", "SQL so‘rov bajarilmoqda"),
}


def _call_event(name: str, args: dict | str | None) -> dict[str, Any]:
    q = args.get("query", "") if isinstance(args, dict) else ""
    ru, uz = TOOL_LABELS.get(name, (name, name))
    return {"type": "tool_call", "tool": name, "label_ru": ru.format(q=q), "label_uz": uz.format(q=q)}


def _result_event(name: str, content: Any) -> dict[str, Any]:
    if isinstance(content, dict) and "row_count" in content:
        n = content["row_count"]
    elif isinstance(content, list):
        n = len(content)
    else:
        return {
            "type": "tool_result",
            "tool": name,
            "label_ru": "Ошибка, повторяю",
            "label_uz": "Xato, qayta urinish",
        }
    return {
        "type": "tool_result",
        "tool": name,
        "label_ru": f"Получено строк: {n}",
        "label_uz": f"Qatorlar soni: {n}",
    }


def _evidence(ev: EvidenceLog) -> tuple[list[EvidenceItem], list[EntityItem]]:
    items = [
        EvidenceItem(**{k: v for k, v in asdict(r).items() if k in EvidenceItem.model_fields}) for r in ev.sql
    ]
    ents = [
        EntityItem(
            kind=e.kind,
            query=e.query,
            matches=[
                EntityMatch(id=str(m["id"]), label=str(m["label"]), score=m.get("score")) for m in e.matches
            ],
        )
        for e in ev.entities
    ]
    return items, ents


async def answer_question(
    question: str,
    session_id: str | None = None,
    channel: str = "api",
    on_event: EventCb | None = None,
) -> AskResult:
    s = get_settings()
    rt = await get_runtime()
    started = time.perf_counter()
    session_id = session_id or str(uuid.uuid4())
    lang = detect_lang(question)
    ev = EvidenceLog()
    deps = AgentDeps(rt.pool, rt.embedder, ev, question)
    history = _sessions.pop(session_id, None)
    model_name = s.llm_model
    kind: Kind = "error"
    text = ""
    error_code = None
    answer_lang: Literal["ru", "uz"] = lang

    with observability.ask_span(session_id, channel, lang, model_name) as trace_id:
        calls: dict[str, str] = {}
        try:
            async with (
                asyncio.timeout(s.agent_timeout_s),
                rt.agent.run_stream_events(
                    question,
                    deps=deps,
                    message_history=history,
                    usage_limits=UsageLimits(request_limit=10, tool_calls_limit=12),
                ) as stream,
            ):
                async for event in stream:
                    if isinstance(event, FunctionToolCallEvent):
                        calls[event.part.tool_call_id] = event.part.tool_name
                        if on_event:
                            await on_event(_call_event(event.part.tool_name, event.part.args_as_dict()))
                    elif isinstance(event, FunctionToolResultEvent):
                        name = calls.get(event.part.tool_call_id, event.part.tool_name)
                        if on_event:
                            await on_event(_result_event(name, event.part.content))
                    elif isinstance(event, AgentRunResultEvent):
                        out = event.result.output
                        kind, text, answer_lang = out.kind, out.text, out.language
                        resp = event.result.all_messages()[-1]
                        model_name = getattr(resp, "model_name", None) or model_name
                        if kind == "clarify":
                            _sessions[session_id] = event.result.all_messages()
                            while len(_sessions) > MAX_SESSIONS:
                                _sessions.popitem(last=False)
        except TimeoutError:
            kind, error_code, text = "error", "timeout", MESSAGES["timeout"][lang]
        except (UnexpectedModelBehavior, UsageLimitExceeded) as e:
            log.warning("agent gave up: %s", e)
            if ev.sql:
                kind, text = "answer", MESSAGES["fallback"][lang]
            else:
                kind, error_code, text = "error", "internal", MESSAGES["internal"][lang]
        except (FallbackExceptionGroup, ModelAPIError) as e:
            log.error("models unavailable: %s", e)
            kind, error_code, text = "error", "unavailable", MESSAGES["unavailable"][lang]

    evidence, entities = _evidence(ev)
    return AskResult(
        id=str(uuid.uuid4()),
        session_id=session_id,
        question=question,
        language=answer_lang,
        kind=kind,
        text=text,
        evidence=evidence,
        entities=entities,
        model=model_name,
        duration_ms=int((time.perf_counter() - started) * 1000),
        trace_id=trace_id,
        error_code=error_code,
    )
