"""Factory that returns the right LLM handler for the current environment."""

import logging
from typing import Union

from ..config import Settings
from .ollama_llm_handler import OllamaLLMHandler
from .openai_compat_llm_handler import OpenAICompatLLMHandler

logger = logging.getLogger(__name__)

LLMHandler = Union[OllamaLLMHandler, OpenAICompatLLMHandler]


def create_llm_handler(app_settings: Settings) -> LLMHandler:
    provider = app_settings.llm_provider.lower()
    if provider == "ollama":
        return OllamaLLMHandler(app_settings)
    if provider in ("groq", "openai"):
        return OpenAICompatLLMHandler(app_settings)

    logger.warning(
        "Unknown LLM_PROVIDER %r - falling back to ollama", app_settings.llm_provider
    )
    return OllamaLLMHandler(app_settings)
