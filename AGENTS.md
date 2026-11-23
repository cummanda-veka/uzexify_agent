# Repository Guidelines

## Project Overview
UZEXify answers questions about 500 000 UZEX exchange deals (2022-01-03 … 2026-10-30) in Russian and Uzbek (Latin and Cyrillic). Every number must come from SQL run against Postgres; the SQL and its rows ship with the answer as evidence. Interfaces: web chat (https://uzex.d3d.uz) and a Telegram bot. The hackathon write-up is `docs/solution.md`.

## Architecture & Data Flow
```
web (Next.js) ─POST /api/ask/stream (SSE)─┐
Telegram bot (aiogram) ─HTTP SSE──────────┤→ FastAPI api/app.py → agent.answer_question → Pydantic AI agent
                                          │      tools: search_* → run_sql (sqlguard) → make_chart
Caddy: forward_auth /internal/geo → api   │   → output.validate_answer (grounding) → AskResult {text, evidence, charts}
```
- **Request path**: `api/app.py` normalizes `X-Client`, applies `RateLimiter` and `AgentGate.slot()` (`api/limits.py`), then calls `answer_question` (`agent/__init__.py`). The stream sends `step` events (tool call/result), then one `answer` or one `error`.
- **Grounding is the core invariant**:
  - `sqlguard.validate_sql` accepts one SELECT, allowlisted tables and no forbidden functions. `run_readonly` runs it in a read-only transaction with a statement timeout. The real security boundary is the DB role `uzex_agent`.
  - `output.validate_answer` rejects a `kind="answer"` without evidence and any number not found in the evidence rows.
  - Charts (`charts.py`) contain only column references to a `sql_id`, never model-supplied values. `/api/chart.png` re-validates client-sent chart/evidence pairs before rendering.
- **Runtime**: `agent/runtime.get_runtime()` is a lazy, lock-guarded singleton (psycopg async pool + pgvector, embedder, prompt, agent), created in the FastAPI lifespan.
- **Session memory**: in-process in the API, keyed by `session_id`; last 4 turns, at most 200 sessions; prior SQL is kept, tool output is not. The bot mints `tg:{chat_id}:{uuid}` per chat and on `/new` (`bot.ChatSessions`).
- **Errors**: codes in `agent.MESSAGES` (`internal`, `timeout`, `unavailable`, `rate_limited`, `busy`, `fallback`), each with `ru`/`uz`/`uz_cyrl` text. If the model fails after SQL has run, the answer falls back to the grounded evidence.
- **Country gate**: Caddy → `/internal/geo` (`api/geo.py`, DB-IP Lite at `geo/dbip-country-lite.mmdb`).
  - Only `ALLOWED_COUNTRIES` (default `UZ`) passes; private/loopback IPs (the bot) also pass. An empty list disables the gate.
  - Fails closed: missing DB or no client IP → deny.
  - Denied API calls get 403 `{"code":"region"}`; pages redirect to `/blocked`.

## Key Directories
- `backend/src/uzexify/agent/`:
  - `prompt.py` — system prompt, including the `<answer_style>` section;
  - `tools.py` — agent tools;
  - `output.py` — answer schema and validation;
  - `models.py` — model/provider setup;
  - `deps.py` — `AgentDeps`/`EvidenceLog`.
- `backend/src/uzexify/api/` — FastAPI app, load limits, geo gate.
- `backend/src/uzexify/bot/` — Telegram bot: rich messages with an HTML fallback. `profile.py` holds name/descriptions/commands/texts, applied at startup by `apply_profile`.
- `backend/src/uzexify/` — top-level modules:
  - `ingest.py` — CSV → Postgres;
  - `search.py` — entity search (lexical + vectors);
  - `typograph.py` — mechanical formatting of numbers and spaces;
  - `numbers.py`, `text.py` — helpers;
  - `observability.py` — Langfuse.
- `backend/evals/` — golden / dialog / style / retrieval evals and their YAML datasets; reports in `evals/reports/`.
- `web/src/app/page.tsx` — the whole chat client: state, SSE, locale and session in localStorage (`uzexify-language`, `uzexify-session`), visualViewport handling.
- `web/src/components/` — `chat/` (answer, evidence, chart, steps), `bits/` (visual components, JSX + CSS), `ui/` (shadcn).
- `web/src/lib/` — `api.ts` (typed SSE client), `i18n.ts` (RU/UZ copy and examples).
- `data/uzex_spot_data/` — source CSVs; its `README.md` defines fields and formulas.
- `design/bot-banner/` — HyperFrames project for the bot banner; follow its own `AGENTS.md`.
- `docs/` — `solution.md` (write-up, abbreviated GOST 7.32), `style.md` (answer style rules).

## Development Commands
```bash
cp .env.example .env                  # fill secrets; never print .env / pre.env
docker compose up -d db               # Postgres + pgvector (host port: POSTGRES_PORT)
cd backend && uv sync
uv run uzexify ingest --data-dir ../data/uzex_spot_data   # schema, load, count asserts, uzex_agent role
uv run uzexify embed                  # product embeddings
uv run uzexify smoke                  # check LLM gateway models
uv run uzexify ask "Сколько сделок было заключено в 2024 году?" [--json]
uv run uzexify serve --port 8000      # API (bind 127.0.0.1; use 127.0.0.1, not localhost, from httpx)
uv run uzexify bot                    # needs TELEGRAM_BOT_TOKEN
cd ../web && bun install && NEXT_PUBLIC_API_BASE=http://localhost:8000 bun dev
```
- Lint, format, types:
  - backend: `uv run ruff format src tests && uv run ruff check src tests && uv run ty check src`;
  - web: `bun run lint` (Biome), `bun run build`.
- Deploy: push to `main` → GitHub Actions (`.github/workflows/images.yml`) builds `ghcr.io/cummanda-veka/uzexify-{backend,web}` for linux/amd64 (public packages, pulled anonymously). Then `scripts/deploy.sh user@host [--bot]` copies `compose.yaml`/`Caddyfile`/`.env`/`geo/`, pulls and starts the stack, ingests on an empty DB (otherwise refreshes the `uzex_agent` role with `uzexify grant`), embeds products that lack embeddings, and restarts `api` and `caddy` (profiles: `app` = api/web/caddy, `bot` = bot).

## Code Conventions & Common Patterns
- Python 3.14; ruff line length 110; async everywhere (`async def`, async pool contexts). Settings come only through `get_settings()` (cached pydantic-settings; env var = upper-case field name, e.g. `ASKS_PER_MINUTE`).
- New user-facing errors: add a code to `agent.MESSAGES` with `ru`/`uz`/`uz_cyrl` text; the API emits `{code, message_ru, message_uz}`.
- Never let the model emit numbers or chart values that are not in SQL evidence. Extend the validators instead of relaxing them.
- Style: fix formatting in code (`typograph.py`); put content/tone rules in `prompt.py` `<answer_style>`. Don't fit the prompt to individual eval cases.
- Bot user texts live in `bot/profile.py` as `{"ru": …, "uz": …}` dicts; web copy lives in `web/src/lib/i18n.ts`. Write plain text: no slogans, no stacks of em dashes.
- Web: React 19 hooks state in `page.tsx`. `MessageList` memoizes per-exchange components, so pass stable handlers. Markdown components in `AnswerCard` live at module scope so tables don't remount.

## Important Files
- Entry points:
  - `backend/src/uzexify/cli.py` (`uzexify` script);
  - `backend/src/uzexify/api/app.py`;
  - `backend/src/uzexify/bot/__init__.py` (`run_bot`);
  - `web/src/app/page.tsx`.
- Config:
  - `compose.yaml`, `Caddyfile`;
  - `backend/pyproject.toml` (deps pinned);
  - `backend/src/uzexify/settings.py`;
  - `.env.example`;
  - `web/package.json`, `web/biome.json`, `web/Dockerfile` (Bun build → Node 24 standalone).
- DB schema: `backend/src/uzexify/db/schema.sql`, executed by `ingest.py`. `ingest.EXPECTED` row counts must match (deals 500000, contracts 6616, …).

## Runtime/Tooling Preferences
- Backend: Python `>=3.14,<3.15`, **uv** only (`uv run …`, `uv add …`); never use pip or a bare `python` for project code.
- Web: **Bun** (`bun@1.4.2`) to install and build; Next.js 16 (Turbopack); Biome, not ESLint/Prettier; production runtime is Node 24 standalone.
- Banner: `npx hyperframes` (check/snapshot). Write each snapshot to a fresh `-o` dir, otherwise a stale frame is reused.
- Next/Turbopack fails the build on an `.ico` without RGBA. Regenerate favicons with Pillow `convert("RGBA")`.

## Testing & QA
- Unit tests:
  - Command: `cd backend && uv run pytest` (pytest + pytest-asyncio, `asyncio_mode=auto`).
  - Pure tests: no DB or LLM. `test_geo.py` skips its country test when the mmdb file is missing.
  - Write tests for behavior (grounding, limits, sessions, geo), not for wording.
- Evals (run from `backend/`; need DB + LLM; reports land in `backend/evals/reports/`):
  - `uv run python -m evals.run --target local --label NAME`; against a running API: `uv run python -m evals.run --target http --base-url http://127.0.0.1:8000 --label NAME`:
    - golden set; checks kind, grounded numbers, language/script, latency ≤ 90 s, charts;
    - `--target http` hits a running API.
  - `uv run python -m evals.dialog_run [--only id,...] --label NAME` — multi-turn memory (`dialogs.yaml`).
  - `uv run python -m evals.style_run --label NAME [--judge ID]` — `style_lint` + LLM judge, scored 1–10.
  - `uv run python -m evals.retrieval --variants lexical,hybrid-gemini,hybrid-voyage,hybrid-gemini+rerank` — entity search recall/MRR.
- Web has no test suite. Verify UI in a real browser against the API.
- Before claiming a change works, run the changed path: an `ask` question, a curl to the endpoint, or the relevant eval.
