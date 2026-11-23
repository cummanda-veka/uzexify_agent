import argparse
import asyncio
import sys


def main() -> None:
    p = argparse.ArgumentParser(prog="uzexify")
    sub = p.add_subparsers(dest="cmd", required=True)
    ing = sub.add_parser("ingest", help="load CSV data into Postgres")
    ing.add_argument("--data-dir", default="../data/uzex_spot_data")
    sub.add_parser("grant", help="create or refresh the read-only agent DB role")
    sub.add_parser("embed", help="compute product embeddings")
    sub.add_parser("smoke", help="check LLM gateway models")
    ask = sub.add_parser("ask", help="ask the agent a question")
    ask.add_argument("question")
    ask.add_argument("--json", action="store_true")
    srv = sub.add_parser("serve", help="run HTTP API")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8000)
    sub.add_parser("bot", help="run Telegram bot")
    a = p.parse_args()

    if a.cmd == "ingest":
        from uzexify.ingest import ingest

        ingest(a.data_dir)
    elif a.cmd == "grant":
        from uzexify.ingest import grant

        grant()
    elif a.cmd == "embed":
        from uzexify.embeddings import embed_products

        asyncio.run(embed_products())
    elif a.cmd == "smoke":
        from uzexify.agent.smoke import smoke

        sys.exit(asyncio.run(smoke()))
    elif a.cmd == "ask":
        from uzexify.agent.cli_ask import ask_cli

        asyncio.run(ask_cli(a.question, as_json=a.json))
    elif a.cmd == "serve":
        import uvicorn

        uvicorn.run("uzexify.api.app:app", host=a.host, port=a.port)
    elif a.cmd == "bot":
        from uzexify.bot import run_bot

        asyncio.run(run_bot())
