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
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.methods import SendRichMessage, SendRichMessageDraft
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    Chat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputRichMessage,
    InputRichMessageMedia,
    Message,
)

from uzexify.bot.profile import EXAMPLES, EXAMPLES_TITLE, HELP, NEW_CHAT, START, apply_profile, ui_language
from uzexify.charts import ChartSpec, chart_png
from uzexify.settings import get_settings
from uzexify.sqlguard import SqlResult

log = logging.getLogger(__name__)


def _duration(answer: dict[str, Any]) -> str:
    """Answer time as "⏱ 15,5 с" (decimal comma, one digit, NBSP before the unit)."""
    seconds = f"{answer.get('duration_ms', 0) / 1000:.1f}".replace(".", ",")
    return f"⏱ {seconds}\u00a0с"


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
    footer = _duration(answer)
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


def chart_images(answer: dict[str, Any]) -> list[tuple[ChartSpec, bytes]]:
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
            images.append((spec, chart_png(spec, result)))
        except Exception:  # a failed render must not lose the text answer
            log.exception("chart render failed: %s", spec.id)
    return images


RICH_LIMIT = 32_000  # Bot API: 32768 characters per rich message; keep a margin
EVIDENCE_ROWS = 10


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def rich_answer(answer: dict[str, Any], images: list[tuple[ChartSpec, bytes]]) -> InputRichMessage:
    """Bot API 10.1+ rich message: the agent's Markdown as is (real tables), charts embedded in the
    body via tg://photo links, the evidence (SQL and rows) in a collapsible block."""
    language = answer.get("language", "ru")
    parts = [str(answer.get("text", ""))]
    media = []
    for spec, png in images:
        title = spec.title.replace('"', "'")
        parts.append(f'![](tg://photo?id={spec.id} "{title}")')
        media.append(
            InputRichMessageMedia(
                id=spec.id, media=InputMediaPhoto(media=BufferedInputFile(png, filename=f"{spec.id}.png"))
            )
        )
    evidence = answer.get("evidence") or []
    footer = _duration(answer)

    def details(rows_per_query: int) -> str:
        if not evidence:
            return ""
        blocks = []
        for item in evidence:
            block = f"**{item.get('sql_id', '')}** {item.get('purpose', '')}\n\n```sql\n{item.get('sql', '')}\n```"
            columns = item.get("columns") or []
            rows = (item.get("rows") or [])[:rows_per_query]
            if columns and rows:
                block += "\n\n| " + " | ".join(_cell(c) for c in columns) + " |\n|"
                block += "---|" * len(columns) + "\n"
                block += "\n".join("| " + " | ".join(_cell(v) for v in row) + " |" for row in rows)
            blocks.append(block)
        summary = "Asos" if language == "uz" else "Основание ответа"
        return f"<details><summary>{summary}</summary>\n\n" + "\n\n".join(blocks) + "\n\n</details>"

    for rows_per_query in (EVIDENCE_ROWS, 3, 0):
        markdown = "\n\n".join([*parts, details(rows_per_query), footer])
        if len(markdown) <= RICH_LIMIT:
            break
    else:
        markdown = "\n\n".join([*parts, footer])[:RICH_LIMIT]
    return InputRichMessage(markdown=markdown, media=media or None)


def rich_progress(done: list[str], current: str) -> InputRichMessage:
    """Streaming draft while the agent works: finished steps, then a 'Thinking…' block with the
    current one. Drafts are previews only; the answer itself is sent with sendRichMessage."""
    lines = [f"- ✓ {step}" for step in done]
    body = "\n".join(lines)
    thinking = f"<tg-thinking>{html.escape(current, quote=False)}</tg-thinking>"
    return InputRichMessage(markdown=f"{body}\n\n{thinking}" if body else thinking)


async def run_bot() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token.strip():
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to run the Telegram bot")
    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher()
    timeout = httpx.Timeout(settings.agent_timeout_s + 15, connect=10)
    # Conversation memory lives in the API, keyed by session id. /new switches the chat to a fresh
    # session; the counter is per process, so a restart also starts clean conversations.
    generation: dict[int, int] = {}

    def session(chat_id: int) -> str:
        return f"tg:{chat_id}:{generation.get(chat_id, 0)}"

    async def send_rich(chat_id: int, markdown: str, reply_markup=None) -> None:
        try:
            await bot(
                SendRichMessage(
                    chat_id=chat_id,
                    rich_message=InputRichMessage(markdown=markdown),
                    reply_markup=reply_markup,
                )
            )
        except TelegramBadRequest:
            await bot.send_message(
                chat_id, markdown.replace("**", "").replace("## ", ""), reply_markup=reply_markup
            )

    def examples_keyboard(lang: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=q, callback_data=f"ex:{lang}:{i}")]
                for i, q in enumerate(EXAMPLES[lang])
            ]
        )

    async with httpx.AsyncClient(timeout=timeout) as client:

        async def answer(chat: Chat, question: str) -> None:
            language = _language(question)
            private = chat.type == ChatType.PRIVATE
            draft_id = secrets.randbelow(2**31 - 1) + 1
            typing = None if private else asyncio.create_task(_typing(bot, chat.id))
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
                    json={"question": question, "session_id": session(chat.id)},
                ) as response:
                    response.raise_for_status()
                    done: list[str] = []
                    calling = ""
                    working = "Ищу в данных" if language == "ru" else "Ma’lumotlar qidirilmoqda"
                    async for event, payload in _events(response):
                        if event == "step" and private:
                            label = payload.get(f"label_{language}") or ""
                            if payload.get("type") == "tool_call":
                                calling = label
                            elif label:
                                done.append(f"{calling} · {label}" if calling else label)
                                calling = ""
                            # A failed draft only costs the progress preview, never the answer.
                            with suppress(TelegramBadRequest):
                                await bot(
                                    SendRichMessageDraft(
                                        chat_id=chat.id,
                                        draft_id=draft_id,
                                        rich_message=rich_progress(done, calling or working),
                                    )
                                )
                        elif event == "answer":
                            images = await asyncio.to_thread(chart_images, payload)
                            try:
                                await bot(
                                    SendRichMessage(
                                        chat_id=chat.id, rich_message=rich_answer(payload, images)
                                    )
                                )
                            except TelegramBadRequest:
                                # Content Telegram cannot render as a rich message: classic HTML answer
                                # and the charts as photos.
                                log.exception("rich message rejected; sending HTML")
                                await bot.send_message(chat.id, format_answer(payload), parse_mode="HTML")
                                for spec, png in images:
                                    await bot.send_photo(
                                        chat.id,
                                        BufferedInputFile(png, filename=f"{spec.id}.png"),
                                        caption=spec.title,
                                    )
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
            await bot.send_message(chat.id, error)

        def lang_of(message: Message) -> str:
            return ui_language(message.from_user.language_code if message.from_user else None)

        @dispatcher.message(CommandStart())
        async def start(message: Message) -> None:
            lang = lang_of(message)
            await send_rich(message.chat.id, START[lang], examples_keyboard(lang))

        @dispatcher.message(Command("help"))
        async def help_(message: Message) -> None:
            await send_rich(message.chat.id, HELP[lang_of(message)])

        @dispatcher.message(Command("examples"))
        async def examples(message: Message) -> None:
            lang = lang_of(message)
            await message.answer(EXAMPLES_TITLE[lang], reply_markup=examples_keyboard(lang))

        @dispatcher.message(Command("new"))
        async def new_chat(message: Message) -> None:
            generation[message.chat.id] = generation.get(message.chat.id, 0) + 1
            lang = lang_of(message)
            await message.answer(NEW_CHAT[lang], reply_markup=examples_keyboard(lang))

        @dispatcher.callback_query(F.data.startswith("ex:"))
        async def pick_example(query: CallbackQuery) -> None:
            _, lang, index = (query.data or "").split(":")
            question = EXAMPLES[lang][int(index)]
            await query.answer()
            if isinstance(query.message, Message):
                await query.message.answer(f"❓ {question}")
                await answer(query.message.chat, question)

        @dispatcher.message(F.text)
        async def ask(message: Message) -> None:
            await answer(message.chat, message.text or "")

        await apply_profile(bot)
        try:
            await dispatcher.start_polling(bot)
        finally:
            await bot.session.close()
