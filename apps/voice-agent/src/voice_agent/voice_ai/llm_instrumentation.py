"""OpenTelemetry instrumentation helper for voice-ai LLM calls.

Wraps LLM invocations in spans that follow the OTel GenAI semantic
conventions (`gen_ai.*`). Spans nest under the active context (the per-turn
conversation parent created by `start_conversation_turn_span`) so one trace
carries the whole call: session, turn, and the model calls inside it.
"""

from contextlib import contextmanager
from typing import Any, Dict

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from ..config import settings
from ..metrics import sanitize_for_log


def gen_ai_provider_attrs() -> Dict[str, str]:
    """Provider attributes for a GenAI span.

    Mirrors create_llm_handler, including its fallback to ollama, so a trace
    never claims a provider the call did not actually use.

    semconv v1.37.0 renamed `gen_ai.system` to `gen_ai.provider.name`. Both are
    emitted: the new name is correct, the old one is what most backends still
    read. Drop `gen_ai.system` once they catch up. "ollama" is outside the
    spec's provider enum, which has no entry for a local runtime.
    """
    provider = {"groq": "groq", "openai": "openai"}.get(
        settings.llm_provider.lower(), "ollama"
    )
    return {"gen_ai.provider.name": provider, "gen_ai.system": provider}


_tracer = trace.get_tracer("voice_agent.voice_ai.llm")


@contextmanager
def start_voice_llm_span(
    span_name: str,
    *,
    model: str,
    call_sid: str = "",
    correlation_id: str = "",
    session_id: str = "",
):
    """Open an LLM span nested under the current context with `gen_ai.*` attributes.

    Inherits the active trace context so that LLM spans become children of the
    per-turn conversation parent. The caller is expected to set
    request/response payload attributes (`input.value`, `output.value`,
    `gen_ai.usage.*`, `gen_ai.response.finish_reasons`) on the yielded span
    after the model returns.
    """
    with _tracer.start_as_current_span(
        span_name,
        attributes={
            "gen_ai.operation.name": "chat",
            **gen_ai_provider_attrs(),
            "gen_ai.request.model": model or "",
            "call_sid": call_sid,
            "correlation_id": correlation_id,
            "session_id": session_id,
            "voice_survey.contains_user_content": "true",
        },
    ) as span:
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


def _set_llm_response_attrs(span, result: Dict[str, Any], *, output_key: str) -> None:
    """Pull `_usage` / `_stop_reason` out of a sync-method result and onto the span."""
    if not isinstance(result, dict):
        return
    usage = result.get("_usage") or {}
    span.set_attribute("gen_ai.usage.input_tokens", int(usage.get("inputTokens", 0)))
    span.set_attribute("gen_ai.usage.output_tokens", int(usage.get("outputTokens", 0)))
    stop_reason = result.get("_stop_reason") or ""
    if stop_reason:
        span.set_attribute("gen_ai.response.finish_reasons", [stop_reason])
    output_text = result.get(output_key) or ""
    span.set_attribute("output.value", sanitize_for_log(output_text))
