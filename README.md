# UZEXify Agent

ИИ-агент для ответов на русском и узбекском языках по реестру биржевых сделок. [Задание UZEX AI Hackathon](https://hackathon.uzex.uz/saralash/?lang=ru#task): ответы должны опираться на данные; если ответа в них нет, агент должен сообщить об этом.

## Стек

- Веб: Next.js, React, shadcn/ui, Bun, Biome.
- Telegram: aiogram.
- Бэкенд: Python, FastAPI, uv, Ruff, ty.
- База: PostgreSQL для данных и эмбеддингов (pgvector).
- Запуск приложения: Docker Compose.

Bun и uv настраиваются через `mise` (`mise install`).

Прод: <https://uzex.d3d.uz>. Описание решения и результаты проверки — [`docs/solution.md`](docs/solution.md).

## Запуск локально

```sh
cp .env.example .env            # заполнить секреты
docker compose up -d db
cd backend
uv sync
uv run uzexify ingest --data-dir ../data/uzex_spot_data
uv run uzexify embed            # векторы товаров (OpenRouter)
uv run uzexify smoke            # проверка моделей шлюза
uv run uzexify ask "Сколько сделок было заключено в 2024 году?"
uv run uzexify serve            # API на :8000
cd ../web && bun install && NEXT_PUBLIC_API_BASE=http://localhost:8000 bun dev
```

Бот: `uv run uzexify bot` (нужен `TELEGRAM_BOT_TOKEN`).

## Проверки

```sh
cd backend
uv run pytest
uv run python -m evals.run --target local --label <имя>
uv run python -m evals.retrieval --variants lexical,hybrid-gemini,hybrid-voyage,hybrid-gemini+rerank
```

## Деплой

На VPS: `docker compose --profile app up -d --build`, затем
`docker compose run --rm api uzexify ingest --data-dir /data && docker compose run --rm api uzexify embed`.
Бот: `docker compose --profile app --profile bot up -d bot`.

## Данные

Исходные CSV находятся в [`data/uzex_spot_data/`](data/uzex_spot_data/); описание полей и правил расчёта — в [README набора данных](data/uzex_spot_data/README.md). Данные вымышленные.
