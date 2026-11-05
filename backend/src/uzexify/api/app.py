import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sse_starlette import EventSourceResponse

from uzexify import observability
from uzexify.agent import MESSAGES, AskResult, EvidenceItem, answer_question
from uzexify.agent.runtime import close_runtime, get_runtime
from uzexify.api.limits import AgentGate, Busy, RateLimiter, client_key
from uzexify.charts import ChartRejected, ChartSpec, chart_png, validate_chart
from uzexify.settings import get_settings
from uzexify.sqlguard import SqlResult

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("uzexify.api")
CLIENTS = {"web", "telegram", "eval", "cli"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    await get_runtime()
    yield
    observability.flush()
    await close_runtime()


app = FastAPI(title="UZEXify", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    session_id: str | None = None
    effort: Literal["low", "medium", "high"] | None = None


def _channel(x_client: str | None) -> str:
    return x_client if x_client in CLIENTS else "api"


@app.get("/api/health")
async def health():
    try:
        rt = await get_runtime()
        async with rt.pool.connection() as conn:
            row = await (await conn.execute("SELECT count(*) FROM deals")).fetchone()
        return {"status": "ok", "deals": row[0] if row else 0}
    except Exception as e:  # noqa: BLE001
        log.error("health failed: %s", e)
        return JSONResponse({"status": "unavailable"}, status_code=503)


_settings = get_settings()
ask_limiter = RateLimiter(_settings.asks_per_minute)
chart_limiter = RateLimiter(30)
gate = AgentGate(_settings.max_concurrent_asks, _settings.queue_wait_s)


def _error_payload(code: str) -> dict:
    m = MESSAGES[code]
    return {"code": code, "message_ru": m["ru"], "message_uz": m["uz"]}


def _key(request: Request, body: AskBody, channel: str) -> str:
    peer = request.client.host if request.client else None
    return client_key(request.headers.get("x-forwarded-for"), peer, body.session_id, channel)


@app.post("/api/ask")
async def ask(body: AskBody, request: Request, x_client: Annotated[str | None, Header()] = None) -> AskResult:
    channel = _channel(x_client)
    if not ask_limiter.allow(_key(request, body, channel)):
        raise HTTPException(429, _error_payload("rate_limited"))
    try:
        async with gate.slot():
            return await answer_question(body.question, body.session_id, channel, effort=body.effort)
    except Busy as e:
        raise HTTPException(503, _error_payload("busy")) from e


class ChartPngBody(BaseModel):
    chart: ChartSpec
    evidence: EvidenceItem


@app.post("/api/chart.png")
async def chart_download(body: ChartPngBody, request: Request) -> Response:
    """Infographic PNG for download. The request is client-supplied, so it is re-validated exactly
    like an agent chart (row limits, numeric values, one unit per axis) before rendering."""
    peer = request.client.host if request.client else None
    if not chart_limiter.allow(client_key(request.headers.get("x-forwarded-for"), peer, None, "web")):
        raise HTTPException(429, _error_payload("rate_limited"))
    spec, ev = body.chart, body.evidence
    if spec.sql_id != ev.sql_id:
        raise HTTPException(422, "chart and evidence refer to different queries")
    result = SqlResult(ev.sql_id, ev.sql, ev.columns, ev.rows, ev.row_count, ev.truncated, ev.duration_ms)
    try:
        checked = validate_chart(
            spec.id,
            result,
            spec.type,
            spec.x,
            [s.column for s in spec.series],
            [s.unit for s in spec.series],
            spec.title,
            [s.label for s in spec.series],
        )
    except ChartRejected as e:
        raise HTTPException(422, str(e)) from e
    png = await asyncio.to_thread(chart_png, checked, result)
    return Response(png, media_type="image/png")


@app.post("/api/ask/stream")
async def ask_stream(body: AskBody, request: Request, x_client: Annotated[str | None, Header()] = None):
    channel = _channel(x_client)
    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    def error(code: str) -> dict:
        return {"event": "error", "data": json.dumps(_error_payload(code), ensure_ascii=False)}

    async def on_event(e: dict) -> None:
        await queue.put({"event": "step", "data": json.dumps(e, ensure_ascii=False)})

    async def run() -> None:
        try:
            if not ask_limiter.allow(_key(request, body, channel)):
                await queue.put(error("rate_limited"))
                return
            if not gate.free:
                await on_event({"type": "queued", "label_ru": "В очереди", "label_uz": "Navbatda"})
            try:
                async with gate.slot():
                    res = await answer_question(
                        body.question, body.session_id, channel, on_event, effort=body.effort
                    )
            except Busy:
                await queue.put(error("busy"))
                return
            if res.kind == "error" and res.error_code in ("timeout", "unavailable"):
                await queue.put(error(res.error_code))
            else:
                await queue.put({"event": "answer", "data": res.model_dump_json()})
        except Exception:
            log.exception("ask stream failed")
            await queue.put(error("internal"))
        finally:
            await queue.put(None)

    async def gen():
        task = asyncio.create_task(run())
        try:
            while (item := await queue.get()) is not None:
                yield item
        finally:
            if not task.done():
                task.cancel()

    return EventSourceResponse(gen(), ping=15)
