"""Model construction for the Bifrost OpenAI-compatible gateway.

MODEL_PROFILES maps a model-id suffix to how that model is called. Values were
recorded by `uzexify smoke` (see agent/smoke.py).
"""

from dataclasses import dataclass
from typing import Literal

from openai import AsyncOpenAI
from pydantic_ai.models import Model
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import (
    OpenAIChatModel,
    OpenAIChatModelSettings,
    OpenAIResponsesModel,
    OpenAIResponsesModelSettings,
)
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from uzexify.settings import get_settings

Effort = Literal["low", "medium", "high"]
ReasoningMode = Literal["setting", "extra_body", "none"]


@dataclass(frozen=True)
class ModelProfile:
    api: Literal["chat", "responses"] = "chat"
    reasoning: ReasoningMode = "setting"
    effort: Effort = "low"


MODEL_PROFILES: dict[str, ModelProfile] = {
    "claude-sonnet-5-5": ModelProfile("chat", "setting", "medium"),
    "gemini-4-argon-high": ModelProfile("chat", "setting", "low"),
    "gpt-6.1-terra": ModelProfile("chat", "setting", "low"),
}


def profile_for(model_id: str) -> ModelProfile:
    for suffix, prof in MODEL_PROFILES.items():
        if model_id.endswith(suffix):
            return prof
    return ModelProfile()


def _provider() -> OpenAIProvider:
    s = get_settings()
    client = AsyncOpenAI(base_url=s.llm_base_url, api_key=s.llm_api_key, max_retries=3, timeout=60)
    return OpenAIProvider(openai_client=client)


def build_model(model_id: str, profile: ModelProfile | None = None, effort: str | None = None) -> Model:
    prof = profile or profile_for(model_id)
    level: Effort = effort if effort in ("low", "medium", "high") else prof.effort
    settings: ModelSettings
    if prof.api == "responses":
        settings = OpenAIResponsesModelSettings(openai_reasoning_effort=level)
        return OpenAIResponsesModel(model_id, provider=_provider(), settings=settings)
    if prof.reasoning == "setting":
        settings = OpenAIChatModelSettings(openai_reasoning_effort=level)
    elif prof.reasoning == "extra_body":
        settings = OpenAIChatModelSettings(extra_body={"reasoning": {"effort": level}})
    else:
        settings = OpenAIChatModelSettings()
    return OpenAIChatModel(model_id, provider=_provider(), settings=settings)


def build_agent_model(effort: Effort | None = None) -> Model:
    """Primary with fallback. `effort` (a user's thinking level) applies to both; without it the
    primary uses LLM_REASONING_EFFORT or its profile level and the fallback its profile level."""
    s = get_settings()
    primary = build_model(s.llm_model, effort=effort or s.llm_reasoning_effort or None)
    if not s.llm_fallback_model or s.llm_fallback_model == s.llm_model:
        return primary
    return FallbackModel(primary, build_model(s.llm_fallback_model, effort=effort))


_by_effort: dict[Effort, Model] = {}


def agent_model_for(effort: Effort) -> Model:
    """Cached model per thinking level, so each request does not rebuild clients."""
    if effort not in _by_effort:
        _by_effort[effort] = build_agent_model(effort)
    return _by_effort[effort]
