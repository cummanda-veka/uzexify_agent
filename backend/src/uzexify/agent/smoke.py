"""`uzexify smoke`: verify gateway chat models (tool calling + reasoning) and embeddings."""

import asyncio
import json
import math
import time

import httpx
from pydantic_ai import Agent

from uzexify.agent.models import ModelProfile, build_model, profile_for
from uzexify.settings import get_settings

CHAT_CANDIDATES = ["claude-sonnet-5-5", "gemini-4-argon-high", "gpt-6.1-terra"]
QUESTION = "Bug‘doyning narxini top va uni 3 ga ko‘paytir. Javobni o‘zbek tilida yoz."


async def _list_models() -> list[str]:
    s = get_settings()
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{s.llm_base_url}/models", headers={"Authorization": f"Bearer {s.llm_api_key}"})
        r.raise_for_status()
        return [m["id"] for m in r.json()["data"]]


async def _chat_test(model_id: str, prof: ModelProfile) -> dict:
    calls: list[str] = []
    agent = Agent(build_model(model_id, prof))

    @agent.tool_plain
    def lookup_price(product: str) -> str:
        """Return the price of a product."""
        calls.append("lookup_price")
        return "1250.5"

    @agent.tool_plain
    def multiply(a: float, b: float) -> float:
        """Multiply two numbers."""
        calls.append("multiply")
        return a * b

    t = time.perf_counter()
    try:
        res = await asyncio.wait_for(agent.run(QUESTION), 90)
    except Exception as e:  # noqa: BLE001 - smoke reports any failure
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
    text = res.output
    ok = len(calls) >= 2 and ("3751,5" in text or "3751.5" in text or "3 751,5" in text)
    return {"ok": ok, "tool_calls": len(calls), "s": round(time.perf_counter() - t, 1), "text": text[:160]}


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b)) / (math.hypot(*a) * math.hypot(*b))


async def _embed_test() -> dict:
    s = get_settings()
    docs = [
        "title: none | text: Пшеница продовольственная Класс 4 класс",
        "title: none | text: ПОРТЛАНДЦЕМЕНТ",
    ]
    q = "task: search result | query: bug‘doy"
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{s.embedding_base_url}/embeddings",
            headers={"Authorization": f"Bearer {s.embedding_api_key}"},
            json={"model": s.embedding_model, "input": [q, *docs]},
        )
        r.raise_for_status()
        vecs = [d["embedding"] for d in r.json()["data"]]
    if len(vecs) < 3:
        return {"ok": False, "batch": False, "n": len(vecs)}
    wheat, cement = _cos(vecs[0], vecs[1]), _cos(vecs[0], vecs[2])
    return {
        "ok": wheat > cement,
        "batch": True,
        "dim": len(vecs[0]),
        "cos_wheat": wheat,
        "cos_cement": cement,
    }


async def smoke() -> int:
    ids = await _list_models()
    out: dict = {"chat": {}, "embedding": None}
    for suffix in CHAT_CANDIDATES:
        matches = [i for i in ids if i.endswith("/" + suffix)]
        for mid in matches:
            base = profile_for(mid)
            variants = [
                ("a_setting", ModelProfile("chat", "setting", base.effort)),
                ("b_extra_body", ModelProfile("chat", "extra_body", base.effort)),
                ("c_none", ModelProfile("chat", "none", base.effort)),
            ]
            if "terra" in mid:
                variants.append(("d_responses", ModelProfile("responses", "setting", base.effort)))
            tried = {}
            for name, prof in variants:
                r = await _chat_test(mid, prof)
                tried[name] = r
                if r["ok"]:
                    break
            out["chat"][mid] = tried
        if not matches:
            out["chat"][suffix] = "not listed"
    try:
        out["embedding"] = await _embed_test()
    except Exception as e:  # noqa: BLE001
        out["embedding"] = {"ok": False, "error": str(e)[:200]}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    passed = any(isinstance(v, dict) and any(r["ok"] for r in v.values()) for v in out["chat"].values())
    return 0 if passed else 1
