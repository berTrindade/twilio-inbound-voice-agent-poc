"""LLM handler backed by a local Ollama server (OpenAI-free, zero-cost).

Implements the shared LLM handler interface so it is a drop-in replacement
selected via LLM_PROVIDER=ollama. Talks to Ollama's native /api/chat endpoint:

  - small model: forced JSON output (format="json"), temperature 0.0
  - big model:   free-form text the prompt instructs to be JSON, temperature 0.3

Both calls are synchronous (requests) and wrapped with asyncio.to_thread by the
async methods, so the instrumentation spans are identical across handlers.
"""

import asyncio
import logging
from typing import Any, Dict

import requests

from .voice_utils import safe_json_loads
from .predefined_responses import PredefinedResponses
from .llm_instrumentation import start_voice_llm_span, _set_llm_response_attrs
from ..metrics import sanitize_for_log
from ..config import Settings

log = logging.getLogger("ollama_llm_handler")


class OllamaLLMHandler:
    """Bedrock-free LLM handler that calls a local Ollama server."""

    def __init__(self, app_settings: Settings):
        self.base_url = app_settings.ollama_base_url.rstrip("/")
        self.small_model_id = app_settings.small_model_id
        self.big_model_id = app_settings.big_model_id
        self.timeout = app_settings.ollama_timeout_seconds

    # -- low-level HTTP -------------------------------------------------------

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
        """POST to /api/chat and return the parsed Ollama response payload."""
        body: Dict[str, Any] = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if force_json:
            body["format"] = "json"

        resp = requests.post(
            f"{self.base_url}/api/chat", json=body, timeout=self.timeout
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _usage(payload: Dict[str, Any]) -> Dict[str, int]:
        """Map Ollama token counts onto the Bedrock-style keys the spans expect."""
        return {
            "inputTokens": int(payload.get("prompt_eval_count", 0) or 0),
            "outputTokens": int(payload.get("eval_count", 0) or 0),
        }

    # -- small interpreter model ---------------------------------------------

    def call_small_model(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> Dict[str, Any]:
        try:
            payload = self._chat(
                system_prompt,
                user_prompt,
                model_id=self.small_model_id,
                max_tokens=300,
                temperature=0.0,
                force_json=True,
            )
            text = (payload.get("message") or {}).get("content") or ""
            obj = safe_json_loads(text)
            if obj is None:
                log.warning("Small model returned invalid JSON: %r", text)
                obj = {}

            return {
                "interpretation": obj.get("interpretation", "other"),
                "answer": obj.get("answer"),
                "reply": (
                    obj["reply"] if "reply" in obj else PredefinedResponses.TRY_AGAIN
                ),
                "confidence": float(obj.get("confidence", 0.0)),
                "whisper_text": obj.get("whisper_text"),
                "handover_reason": obj.get("handover_reason") or "none",
                "guardrail_topic": obj.get("guardrail_topic"),
                "_usage": self._usage(payload),
                "_stop_reason": payload.get("done_reason") or "",
            }
        except Exception:
            log.exception("Small model call failed (model_id=%s)", self.small_model_id)
            return {
                "interpretation": "other",
                "answer": None,
                "reply": PredefinedResponses.TRY_AGAIN_AFTER_LLM_EXCEPTION,
                "confidence": 0.0,
                "whisper_text": None,
                "handover_reason": "none",
                "guardrail_topic": None,
                "_usage": {},
                "_stop_reason": "error",
            }

    # -- big escalation model -------------------------------------------------

    def call_big_model(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> Dict[str, Any]:
        try:
            payload = self._chat(
                system_prompt,
                user_prompt,
                model_id=self.big_model_id,
                max_tokens=400,
                temperature=0.3,
                force_json=False,
            )
            txt = ((payload.get("message") or {}).get("content") or "").strip()
            obj = safe_json_loads(txt) or {}
            return {
                "action": obj.get("action", "clarify"),
                "question_id": obj.get("question_id"),
                "value": obj.get("value"),
                "text": obj.get("text"),
                "whisper_text": obj.get("whisper_text"),
                "handover_reason": obj.get("handover_reason") or "none",
                "_usage": self._usage(payload),
                "_stop_reason": payload.get("done_reason") or "",
            }
        except Exception:
            log.exception(
                "Big model escalation failed (model_id=%s)", self.big_model_id
            )
            return {
                "action": "clarify",
                "text": PredefinedResponses.TRY_AGAIN_AFTER_LLM_EXCEPTION,
                "whisper_text": None,
                "handover_reason": "none",
                "_usage": {},
                "_stop_reason": "error",
            }

    # -- async wrappers -------------------------------------------------------

    async def call_small_model_async(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        call_sid: str = "",
        correlation_id: str = "",
        session_id: str = "",
    ) -> Dict[str, Any]:
        with start_voice_llm_span(
            "voice_ai.llm.small_model",
            model=self.small_model_id or "",
            call_sid=call_sid,
            correlation_id=correlation_id,
            session_id=session_id,
        ) as span:
            span.set_attribute("input.value", sanitize_for_log(user_prompt))
            result = await asyncio.to_thread(
                self.call_small_model,
                system_prompt,
                user_prompt,
            )
            _set_llm_response_attrs(span, result, output_key="reply")
            return result

    async def call_big_model_async(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        call_sid: str = "",
        correlation_id: str = "",
        session_id: str = "",
    ) -> Dict[str, Any]:
        with start_voice_llm_span(
            "voice_ai.llm.big_model",
            model=self.big_model_id or "",
            call_sid=call_sid,
            correlation_id=correlation_id,
            session_id=session_id,
        ) as span:
            span.set_attribute("input.value", sanitize_for_log(user_prompt))
            result = await asyncio.to_thread(
                self.call_big_model,
                system_prompt,
                user_prompt,
            )
            _set_llm_response_attrs(span, result, output_key="text")
            return result
