# UZEXify Agent

An AI agent that answers questions in Russian and Uzbek (Latin and Cyrillic) over a registry of **500,000** exchange deals (3 January 2022 – 30 October 2026). Built for the [UZEX AI Hackathon 2026 qualifier task](https://hackathon.uzex.uz/saralash/?lang=ru#task): every answer comes from the data, and when the data has no answer, the agent says so.

Demo: <https://uzex.d3d.uz> (no sign-up). Solution write-up and quality numbers (in Russian): [`docs/solution.md`](docs/solution.md).

The data in this repository is synthetic: the format mirrors the public deal registry, and any resemblance to real organisations is coincidental. See [`data/uzex_spot_data/README.md`](data/uzex_spot_data/README.md).

## What it does

- Counts deals and computes totals, volumes, average prices and shares for any period — by product, company, broker, region, trade type and deal status.
- Finds companies and products across scripts and with typos; asks a follow-up question when several match.
- Keeps a short conversation ("and by month?", "show it on a chart").
- Draws charts only from rows of the executed SQL.
- Converts USD deals to UZS at the exchange rate of the deal date.
- Shows the basis of each answer: the SQL and its result rows.

## How an answer is produced

1. The agent (Pydantic AI) resolves the companies, brokers and products mentioned in the question.
2. It writes a single read-only `SELECT` against the registry tables; the SQL is validated before execution (`sqlguard`).
3. Every number in the answer text is checked against the query result. If the check fails, the model must recompute the value with a query, and the user sees a warning.
4. No answer without an executed query. If there is no data, the agent says so.

Company and broker search is lexical (trigrams over a normalised name key, plus tax ID and broker code). Product search is hybrid: lexical + vector embeddings in pgvector, merged with Reciprocal Rank Fusion (RRF).

## Stack

| Part | Technology |
|---|---|
| Agent | Pydantic AI |
| API | FastAPI |
| Database | PostgreSQL + pgvector |
| Web | Next.js, React, shadcn/ui, Bun |
| Telegram | aiogram 3 |
| Observability | Langfuse |
| Deployment | Docker Compose, Caddy, mise (uv + Bun) |

On a 42-question control set (34 answerable, 6 with no data, 2 requiring clarification; see `docs/solution.md`): the chosen model answered 33 of 34 correctly, invented 0 answers where data was missing, and matched the question language in 42 of 42. Run reports: `backend/evals/reports/`.

## Running locally

```sh
cp .env.example .env            # fill in an OpenAI-compatible endpoint and keys
docker compose up -d db
cd backend
uv sync
uv run uzexify ingest --data-dir ../data/uzex_spot_data
uv run uzexify embed            # product embeddings (OpenRouter)
uv run uzexify smoke            # check the configured models
uv run uzexify ask "Сколько сделок было заключено в 2024 году?"
uv run uzexify serve            # API on :8000
cd ../web && bun install && NEXT_PUBLIC_API_BASE=http://localhost:8000 bun dev
```

Bot: `uv run uzexify bot` (requires `TELEGRAM_BOT_TOKEN`). Install Bun and uv with `mise install`.

## Checks

```sh
cd backend
uv run pytest
uv run python -m evals.run --target local --label <name>
uv run python -m evals.retrieval --variants lexical,hybrid-gemini,hybrid-voyage,hybrid-gemini+rerank
```

## Deployment

On a VPS: `docker compose --profile app up -d --build`, then

```sh
docker compose run --rm api uzexify ingest --data-dir /data
docker compose run --rm api uzexify embed
```

Bot: `docker compose --profile app --profile bot up -d bot`.

## Third-party data

`geo/dbip-country-lite.mmdb` is the [DB-IP IP to Country Lite](https://db-ip.com/db/download/ip-to-country-lite) database, licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). IP Geolocation by [DB-IP](https://db-ip.com).
