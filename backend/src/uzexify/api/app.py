import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sse_starlette import EventSourceResponse

from uzexify import observability
from uzexify.agent import MESSAGES, AskResult, EvidenceItem, answer_question
from uzexify.agent.runtime import close_runtime, get_runtime
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


@app.post("/api/ask")
async def ask(body: AskBody, x_client: Annotated[str | None, Header()] = None) -> AskResult:
    return await answer_question(body.question, body.session_id, _channel(x_client))


class ChartPngBody(BaseModel):
    chart: ChartSpec
    evidence: EvidenceItem


@app.post("/api/chart.png")
async def chart_download(body: ChartPngBody) -> Response:
    """Infographic PNG for download. The request is client-supplied, so it is re-validated exactly
    like an agent chart (row limits, numeric values, one unit per axis) before rendering."""
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
async def ask_stream(body: AskBody, x_client: Annotated[str | None, Header()] = None):
    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def on_event(e: dict) -> None:
        await queue.put({"event": "step", "data": json.dumps(e, ensure_ascii=False)})

    async def run() -> None:
        try:
            res = await answer_question(body.question, body.session_id, _channel(x_client), on_event)
            if res.kind == "error" and res.error_code in ("timeout", "unavailable"):
                code = res.error_code
                await queue.put(
                    {
                        "event": "error",
                        "data": json.dumps(
                            {
                                "code": code,
                                "message_ru": MESSAGES[code]["ru"],
                                "message_uz": MESSAGES[code]["uz"],
                            },
                            ensure_ascii=False,
                        ),
                    }
                )
            else:
                await queue.put({"event": "answer", "data": res.model_dump_json()})
        except Exception:
            log.exception("ask stream failed")
            m = MESSAGES["internal"]
            await queue.put(
                {
                    "event": "error",
                    "data": json.dumps(
                        {"code": "internal", "message_ru": m["ru"], "message_uz": m["uz"]}, ensure_ascii=False
                    ),
                }
            )
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
