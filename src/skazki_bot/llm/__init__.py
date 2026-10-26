from __future__ import annotations

from skazki_bot.config import Settings
from skazki_bot.llm.base import ChatLLM, LLMError, ModelRefusal

__all__ = ["ChatLLM", "LLMError", "ModelRefusal", "build_llm"]


def build_llm(settings: Settings) -> ChatLLM:
    if settings.llm_provider == "fake":
        from skazki_bot.llm.fake import FakeLLM

        return FakeLLM()

    from skazki_bot.llm.anthropic_llm import AnthropicLLM

    assert settings.anthropic_api_key is not None  # гарантирует валидатор настроек
    return AnthropicLLM(
        api_key=settings.anthropic_api_key.get_secret_value(),
        model=settings.llm_model,
        guard_model=settings.guard_model,
        timeout=settings.llm_timeout_s,
        effort=settings.llm_effort,
        guard_effort=settings.guard_effort,
        thinking=settings.llm_thinking,
        strict_tools=settings.llm_strict_tools,
    )
