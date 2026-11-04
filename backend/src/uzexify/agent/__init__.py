"""Agent entry point: `answer_question`."""

import asyncio
import logging
import re
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
    ModelConnectionError,
    ModelServerError,
    ModelUnavailableError,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
)
from pydantic_ai.messages import FunctionToolCallEvent, FunctionToolResultEvent, ModelMessage
from pydantic_ai.run import AgentRunResultEvent

from uzexify import observability
from uzexify.agent.deps import AgentDeps, EvidenceLog
from uzexify.agent.models import Effort, agent_model_for
from uzexify.agent.runtime import get_runtime
from uzexify.charts import ChartSpec
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
    charts: list[ChartSpec] = []
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
        "uz_cyrl": "Текширилган жавобни шакллантириб бўлмади; қуйида базадан олинган сўров натижаси.",
    },
    "internal": {
        "ru": "Не удалось получить проверенный ответ. Попробуйте переформулировать вопрос.",
        "uz": "Tekshirilgan javob olinmadi. Savolni boshqacha yozib ko‘ring.",
        "uz_cyrl": "Текширилган жавоб олинмади. Саволни бошқача ёзиб кўринг.",
    },
    "timeout": {
        "ru": "Превышено время ожидания ответа. Попробуйте упростить вопрос.",
        "uz": "Javob kutish vaqti tugadi. Savolni soddalashtirib ko‘ring.",
        "uz_cyrl": "Жавоб кутиш вақти тугади. Саволни соддалаштириб кўринг.",
    },
    "unavailable": {
        "ru": "Языковая модель сейчас недоступна. Повторите попытку позже.",
        "uz": "Til modeli hozir mavjud emas. Keyinroq qayta urinib ko‘ring.",
        "uz_cyrl": "Тил модели ҳозир мавжуд эмас. Кейинроқ қайта уриниб кўринг.",
    },
}

TOOL_LABELS = {
    "search_companies": ("Ищу компанию: «{q}»", "Kompaniya qidirilmoqda: «{q}»"),
    "search_brokers": ("Ищу брокера: «{q}»", "Broker qidirilmoqda: «{q}»"),
    "search_products": ("Ищу товар: «{q}»", "Tovar qidirilmoqda: «{q}»"),
    "run_sql": ("Выполняю SQL-запрос", "SQL so‘rov bajarilmoqda"),
    "make_chart": ("Строю график", "Grafik chizilmoqda"),
}


def _call_event(call_id: str, name: str, args: dict | str | None) -> dict[str, Any]:
    q = args.get("query", "") if isinstance(args, dict) else ""
    ru, uz = TOOL_LABELS.get(name, (name, name))
    return {
        "type": "tool_call",
        "call_id": call_id,
        "tool": name,
        "label_ru": ru.format(q=q),
        "label_uz": uz.format(q=q),
    }


def _result_event(call_id: str, name: str, content: Any, outcome: str) -> dict[str, Any]:
    """SSE step for a finished tool call; `outcome` is Pydantic AI's ToolReturnPart.outcome."""
    n: int | None = None
    if outcome == "success":
        if isinstance(content, dict) and "chart_id" in content:
            return {
                "type": "tool_result",
                "call_id": call_id,
                "tool": name,
                "ok": True,
                "label_ru": f"Точек на графике: {content['points']}",
                "label_uz": f"Grafikdagi nuqtalar: {content['points']}",
            }
        if isinstance(content, dict) and "row_count" in content:
            n = content["row_count"]
        elif isinstance(content, list):
            n = len(content)
    if n is None:
        return {
            "type": "tool_result",
            "call_id": call_id,
            "tool": name,
            "ok": False,
            "label_ru": "Ошибка, повторяю",
            "label_uz": "Xato, qayta urinish",
        }
    return {
        "type": "tool_result",
        "call_id": call_id,
        "tool": name,
        "ok": True,
        "label_ru": f"Получено строк: {n}",
        "label_uz": f"Qatorlar soni: {n}",
    }


TRANSIENT_ERRORS = (ModelConnectionError, ModelServerError, ModelUnavailableError)


def _leaf_errors(e: BaseException) -> list[BaseException]:
    return (
        [x for sub in e.exceptions for x in _leaf_errors(sub)] if isinstance(e, BaseExceptionGroup) else [e]
    )


def _is_transient(e: BaseException) -> bool:
    """Only transport/server-side failures are worth a rerun; auth, not-found and bad requests are not."""
    return all(isinstance(x, TRANSIENT_ERRORS) for x in _leaf_errors(e))


def _describe_error(e: BaseException) -> str:
    """Class, transport phase / in-stream flag and cause chain of each leaf error, for diagnosis."""
    parts = []
    for leaf in _leaf_errors(e):
        where = f"[in_stream={getattr(leaf, 'in_stream', None)} phase={getattr(leaf, 'phase', None)}]"
        chain, cur = [], leaf
        while cur is not None and len(chain) < 5:
            chain.append(f"{type(cur).__name__}: {str(cur)[:160]}")
            cur = cur.__cause__ or cur.__context__
        parts.append(f"{where} " + " <- ".join(chain))
    return " | ".join(parts)


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
    effort: Effort | None = None,
) -> AskResult:
    s = get_settings()
    rt = await get_runtime()
    started = time.perf_counter()
    session_id = session_id or str(uuid.uuid4())
    lang = detect_lang(question)
    msg_lang = "uz_cyrl" if lang == "uz" and re.search(r"[а-яёўқғҳ]", question, re.IGNORECASE) else lang
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
        deadline = asyncio.get_running_loop().time() + s.agent_timeout_s
        events_seen = 0
        # Mitigation (root cause unconfirmed): transient transport failures surfaced as
        # "Connection error." after client retries; rerun the whole agent once for those only.
        for attempt in range(2):
            events_seen = 0
            try:
                async with (
                    asyncio.timeout_at(deadline),
                    rt.agent.run_stream_events(
                        question,
                        deps=deps,
                        message_history=history,
                        model=agent_model_for(effort) if effort else None,
                        usage_limits=UsageLimits(request_limit=10, tool_calls_limit=12),
                    ) as stream,
                ):
                    async for event in stream:
                        events_seen += 1
                        if isinstance(event, FunctionToolCallEvent):
                            calls[event.part.tool_call_id] = event.part.tool_name
                            if on_event:
                                await on_event(
                                    _call_event(
                                        event.part.tool_call_id,
                                        event.part.tool_name,
                                        event.part.args_as_dict(),
                                    )
                                )
                        elif isinstance(event, FunctionToolResultEvent):
                            name = calls.get(event.part.tool_call_id, event.part.tool_name)
                            if on_event:
                                await on_event(
                                    _result_event(
                                        event.part.tool_call_id, name, event.part.content, event.part.outcome
                                    )
                                )
                        elif isinstance(event, AgentRunResultEvent):
                            out = event.result.output
                            kind, text, answer_lang = out.kind, out.text, out.language
                            resp = event.result.all_messages()[-1]
                            model_name = getattr(resp, "model_name", None) or model_name
                            if kind == "clarify":
                                _sessions[session_id] = event.result.all_messages()
                                while len(_sessions) > MAX_SESSIONS:
                                    _sessions.popitem(last=False)
                break
            except TimeoutError:
                kind, error_code, text = "error", "timeout", MESSAGES["timeout"][msg_lang]
                break
            except (UnexpectedModelBehavior, UsageLimitExceeded) as e:
                log.warning("agent gave up: %s", e)
                if ev.sql:
                    kind, text = "answer", MESSAGES["fallback"][msg_lang]
                else:
                    kind, error_code, text = "error", "internal", MESSAGES["internal"][msg_lang]
                break
            except (FallbackExceptionGroup, ModelAPIError) as e:
                remaining = deadline - asyncio.get_running_loop().time()
                log.error(
                    "model error (attempt %d, %d stream events before failure): %s",
                    attempt + 1,
                    events_seen,
                    _describe_error(e),
                )
                if attempt == 0 and remaining > 20 and _is_transient(e):
                    log.warning("transient model transport error, rerunning agent (%.0fs left)", remaining)
                    ev.sql.clear()
                    ev.entities.clear()
                    ev.charts.clear()
                    continue
                kind, error_code, text = "error", "unavailable", MESSAGES["unavailable"][msg_lang]
                break

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
        # Charts accompany a grounded answer only; no_data/clarify/error never carry one.
        charts=ev.charts if kind == "answer" else [],
        model=model_name,
        duration_ms=int((time.perf_counter() - started) * 1000),
        trace_id=trace_id,
        error_code=error_code,
    )
