import asyncio
import html
import json
import logging
import re
import secrets
from contextlib import suppress
from typing import Any

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatAction, ChatType
from aiogram.filters import CommandStart
from aiogram.types import BufferedInputFile, Message

from uzexify.charts import ChartSpec, chart_png
from uzexify.settings import get_settings
from uzexify.sqlguard import SqlResult

log = logging.getLogger(__name__)

START = (
    "Задайте вопрос о сделках UZEX / UZEX bitimlari haqida savol bering.\n\n"
    "• Сколько сделок было заключено в 2024 году?\n"
    "• Какой брокер провёл больше всего сделок на стороне покупателя в 2023 году?\n"
    "• 2023-yilda nechta bitim tuzilgan?\n"
    "• bug‘doy 2025-yilda jami qancha sotilgan?"
)


def _escaped_prefix(text: str, limit: int) -> str:
    """Escape a prefix without cutting an HTML entity."""
    result = []
    used = 0
    for char in text:
        escaped = html.escape(char, quote=False)
        if used + len(escaped) > limit:
            break
        result.append(escaped)
        used += len(escaped)
    return "".join(result)


def _table_to_pre(lines: list[str]) -> str:
    """Render a GFM table as an aligned monospace block (Telegram has no table markup)."""
    rows = [
        [cell.strip().replace("**", "") for cell in line.strip().strip("|").split("|")]
        for line in lines
        if not re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?", line.strip())
    ]
    widths = [max(len(r[i]) if i < len(r) else 0 for r in rows) for i in range(max(map(len, rows)))]
    text = "\n".join(
        "  ".join((c.ljust(widths[i]) if i == 0 else c.rjust(widths[i])) for i, c in enumerate(r)).rstrip()
        for r in rows
    )
    return f"<pre>{html.escape(text, quote=False)}</pre>"


def markdown_to_html(text: str) -> str:
    """Convert the agent's light Markdown (bold, '- ' bullets, tables) to Telegram HTML."""
    out: list[str] = []
    table: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("|"):
            table.append(line)
            continue
        if table:
            out.append(_table_to_pre(table))
            table = []
        escaped = html.escape(line, quote=False)
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
        out.append(re.sub(r"^(\s*)[-*] ", r"\1• ", escaped))
    if table:
        out.append(_table_to_pre(table))
    return "\n".join(out)


def format_answer(answer: dict[str, Any]) -> str:
    """Render a Telegram HTML response, dropping rows before truncating SQL."""
    language = answer.get("language", "ru")
    title = "Asos" if language == "uz" else "Основание"
    footer = f"⏱ {answer.get('duration_ms', 0) / 1000:g} с · {answer.get('model', '')}"
    footer_html = html.escape(footer, quote=False)
    evidence = answer.get("evidence") or []
    sql = "\n\n".join(str(item.get("sql", "")) for item in evidence)[:1500]
    rows = []
    for item in evidence:
        columns = item.get("columns") or []
        if columns:
            rows.append(" | ".join(map(str, columns)))
        rows.extend(" | ".join(map(str, row)) for row in (item.get("rows") or [])[:10])
    rows = rows[: 10 + len(evidence)]
    text = str(answer.get("text", ""))

    def render(body: str, query: str, lines: list[str]) -> str:
        block = ""
        if evidence:
            content = html.escape(query, quote=False)
            if lines:
                content += ("\n\n" if content else "") + html.escape("\n".join(lines), quote=False)
            block = f"\n\n<blockquote expandable>{title}\n<pre>{content}</pre></blockquote>"
        return f"{body}{block}\n\n{footer_html}"

    body = markdown_to_html(text)
    while rows and len(render(body, sql, rows)) > 4096:
        rows.pop()
    remaining = 4096 - len(render(body, "", []))
    if len(html.escape(sql, quote=False)) > max(0, remaining):
        escaped_sql = _escaped_prefix(sql, max(0, remaining))
        # Already escaped; render the fixed structure without escaping a second time.
        block = (
            f"\n\n<blockquote expandable>{title}\n<pre>{escaped_sql}</pre></blockquote>" if evidence else ""
        )
        result = f"{body}{block}\n\n{footer_html}"
    else:
        result = render(body, sql, rows)
    if len(result) > 4096:
        suffix = render("", "", [])
        # The response text itself can exceed Telegram's limit.
        if len(suffix) > 4096:
            suffix = "\n\n" + _escaped_prefix(footer, 4094)
        result = _escaped_prefix(text, 4096 - len(suffix)) + suffix
    return result


def _language(text: str) -> str:
    from uzexify.text import detect_lang

    return detect_lang(text)


async def _events(response: httpx.Response):
    event = "message"
    data = []
    async for line in response.aiter_lines():
        if not line:
            if data:
                yield event, json.loads("\n".join(data))
            event, data = "message", []
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip())
    if data:
        yield event, json.loads("\n".join(data))


async def _typing(bot: Bot, chat_id: int) -> None:
    while True:
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        await asyncio.sleep(4)


def chart_images(answer: dict[str, Any]) -> list[tuple[str, bytes]]:
    """PNG for each chart of the answer, rendered from the answer's own SQL evidence rows."""
    results = {
        item["sql_id"]: SqlResult(
            item["sql_id"],
            item["sql"],
            item["columns"],
            item["rows"],
            item["row_count"],
            item["truncated"],
            item["duration_ms"],
        )
        for item in answer.get("evidence") or []
    }
    images = []
    for raw in answer.get("charts") or []:
        spec = ChartSpec.model_validate(raw)
        result = results.get(spec.sql_id)
        if result is None:
            continue
        try:
            images.append((f"{spec.id}.png", chart_png(spec, result)))
        except Exception:  # a failed render must not lose the text answer that was already sent
            log.exception("chart render failed: %s", spec.id)
    return images


async def run_bot() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token.strip():
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to run the Telegram bot")
    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher()
    timeout = httpx.Timeout(settings.agent_timeout_s + 15, connect=10)
    async with httpx.AsyncClient(timeout=timeout) as client:

        @dispatcher.message(CommandStart())
        async def start(message: Message) -> None:
            await message.answer(START)

        @dispatcher.message(F.text)
        async def ask(message: Message) -> None:
            question = message.text or ""
            language = _language(question)
            private = message.chat.type == ChatType.PRIVATE
            draft_id = secrets.randbelow(2**31 - 1) + 1
            typing = None if private else asyncio.create_task(_typing(bot, message.chat.id))
            error = (
                "Не удалось получить ответ сервиса. Попробуйте ещё раз."
                if language == "ru"
                else "Xizmatdan javob olib bo‘lmadi. Qayta urinib ko‘ring."
            )
            try:
                async with client.stream(
                    "POST",
                    f"{settings.api_base_url.rstrip('/')}/api/ask/stream",
                    headers={"X-Client": "telegram"},
                    json={"question": question, "session_id": f"tg:{message.chat.id}"},
                ) as response:
                    response.raise_for_status()
                    async for event, payload in _events(response):
                        if event == "step" and private:
                            label = payload.get(f"label_{language}")
                            if label:
                                await bot.send_message_draft(
                                    chat_id=message.chat.id, draft_id=draft_id, text=label
                                )
                        elif event == "answer":
                            await message.answer(format_answer(payload), parse_mode="HTML")
                            for name, png in await asyncio.to_thread(chart_images, payload):
                                await message.answer_photo(BufferedInputFile(png, filename=name))
                            return
                        elif event == "error":
                            error = payload.get(f"message_{language}") or error
                            break
            except httpx.HTTPError, ValueError, KeyError:
                pass
            finally:
                if typing:
                    typing.cancel()
                    with suppress(asyncio.CancelledError):
                        await typing
            await message.answer(error)

        try:
            await dispatcher.start_polling(bot)
        finally:
            await bot.session.close()
