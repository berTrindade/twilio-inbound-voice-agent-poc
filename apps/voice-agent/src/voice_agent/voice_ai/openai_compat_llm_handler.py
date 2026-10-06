"""LLM handler for any OpenAI-compatible chat API (e.g. Groq's free tier).

Selected via LLM_PROVIDER=groq (or "openai"). Groq is the recommended backend for
hosted demos: it's OpenAI-compatible, low-latency, and needs no GPU, so the runner
can live on a small free/cheap host instead of a machine big enough to run Ollama.

Implementation note: this subclasses OllamaLLMHandler and overrides ONLY the
transport. It POSTs to /chat/completions with a Bearer key and normalizes the
OpenAI response into the same Ollama-shaped payload the inherited small/big-model
mappers, token accounting, and async/instrumentation wrappers already expect.
"""

import logging
from typing import Any, Dict

import requests

from .ollama_llm_handler import OllamaLLMHandler
from ..config import Settings

log = logging.getLogger("openai_compat_llm_handler")


class OpenAICompatLLMHandler(OllamaLLMHandler):
    """Ollama-free handler that calls an OpenAI-compatible chat API."""

    def __init__(self, app_settings: Settings):
        self.base_url = app_settings.llm_base_url.rstrip("/")
        self.api_key = app_settings.llm_api_key
        self.small_model_id = app_settings.small_model_id
        self.big_model_id = app_settings.big_model_id
        self.timeout = app_settings.ollama_timeout_seconds
        if not self.api_key:
            log.warning(
                "LLM_API_KEY/GROQ_API_KEY not set - OpenAI-compatible calls will be "
                "rejected with 401."
            )

    def _chat(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model_id: str,
        max_tokens: int,
        temperature: float,
        force_json: bool,
    ) -> Dict[str, Any]:
        """POST to /chat/completions and normalize to the Ollama payload shape."""
        body: Dict[str, Any] = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if force_json:
            # Note: OpenAI-compatible JSON mode requires the word "json" somewhere
            # in the prompt; the small-interpreter prompt already instructs JSON.
            body["response_format"] = {"type": "json_object"}

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        resp = requests.post(
            f"{self.base_url}/chat/completions",
            json=body,
            headers=headers,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        choice = (data.get("choices") or [{}])[0]
        content = ((choice.get("message") or {}).get("content")) or ""
        usage = data.get("usage") or {}
        return {
            "message": {"content": content},
            "prompt_eval_count": usage.get("prompt_tokens", 0),
            "eval_count": usage.get("completion_tokens", 0),
            "done_reason": choice.get("finish_reason") or "",
        }
