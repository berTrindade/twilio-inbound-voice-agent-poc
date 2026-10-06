"""Live test against the real local Ollama (the default LLM provider).

Excluded from the default suite. Run with the Ollama server up + the configured
models pulled:
    SMALL_MODEL_ID=qwen2.5:7b-instruct OLLAMA_BASE_URL=http://localhost:11434 \
        poetry run pytest -m live tests/voice_ai/test_ollama_live.py -v
"""

import pytest

from voice_agent.config import Settings
from voice_agent.voice_ai.ollama_llm_handler import OllamaLLMHandler

pytestmark = pytest.mark.live


def test_small_model_real_call_succeeds():
    handler = OllamaLLMHandler(Settings())
    resp = handler.call_small_model(
        "You classify a survey answer and reply with strict JSON containing an "
        "'interpretation' field.",
        "Question: Are you ready to begin? Options: yes, no.\nUser said: yes",
    )
    # A real (non-exception) Ollama call sets a model stop reason, not "error".
    assert resp["_stop_reason"] != "error"
    assert isinstance(resp["interpretation"], str) and resp["interpretation"]
    assert isinstance(resp["confidence"], float)
    assert "reply" in resp


def test_big_model_real_call_succeeds():
    handler = OllamaLLMHandler(Settings())
    resp = handler.call_big_model(
        "You are a survey assistant. Reply with strict JSON containing an "
        "'action' field.",
        "The user asked a clarifying question about the survey.",
    )
    assert resp["_stop_reason"] != "error"
    assert "action" in resp
