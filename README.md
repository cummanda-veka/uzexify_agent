# UZEXify Agent

ИИ-агент для ответов на русском и узбекском языках по реестру биржевых сделок. [Задание UZEX AI Hackathon](https://hackathon.uzex.uz/saralash/?lang=ru#task): ответы должны опираться на данные; если ответа в них нет, агент должен сообщить об этом.

## Стек

- Веб: Next.js, React, shadcn/ui, Bun, Biome.
- Telegram: aiogram.
- Бэкенд: Python, FastAPI, uv, Ruff, ty.
- База: PostgreSQL для данных и эмбеддингов (pgvector).
- Запуск приложения: Docker Compose.

Bun и uv настраиваются через `mise` (`mise install`).

## Данные и план

Исходные CSV находятся в [`data/uzex_spot_data/`](data/uzex_spot_data/); описание полей и правил расчёта — в [README набора данных](data/uzex_spot_data/README.md). Данные вымышленные.

[План реализации](PLAN.md). Приложение и Docker Compose пока не реализованы.
