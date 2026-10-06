"""Hierarchical conversation-trace helpers for voice-ai.

A per-turn parent span (gen_ai `invoke_agent`) carries the conversation history;
the model spans + a survey-definition response span nest under it. The turn
span itself nests under the websocket session span, so one call is one trace.
"""

import json
from contextlib import contextmanager
from typing import Dict, List, Optional

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from .llm_instrumentation import gen_ai_provider_attrs

_tracer = trace.get_tracer("voice_agent.voice_ai.conversation")


def serialize_messages(messages: List[Dict[str, str]]) -> str:
    """voice-ai conversation_log [{role,text}] -> gen_ai.*.messages JSON [{role,content}]."""
    return json.dumps(
        [{"role": m.get("role", ""), "content": m.get("text", "")} for m in messages]
    )


@contextmanager
def start_conversation_turn_span(
    *,
    call_sid: str = "",
    session_id: str = "",
    correlation_id: str = "",
    conversation_history: Optional[List[Dict[str, str]]] = None,
):
    """Open the per-turn parent span, nested under the websocket session span."""
    with _tracer.start_as_current_span(
        "invoke_agent voice_survey",
        kind=SpanKind.CLIENT,
        attributes={
            "gen_ai.operation.name": "invoke_agent",
            **gen_ai_provider_attrs(),
            "gen_ai.conversation.id": call_sid,
            "gen_ai.input.messages": serialize_messages(conversation_history or []),
            "call_sid": call_sid,
            "session_id": session_id,
            "correlation_id": correlation_id,
            "voice_survey.contains_user_content": "true",
        },
    ) as span:
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


@contextmanager
def _child_span(name: str):
    """Nest a span under the active turn parent (inherits current context)."""
    with _tracer.start_as_current_span(name) as span:
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


def emit_user_message_span(*, text: str, node_id: str, call_sid: str = "") -> None:
    """Child span for the incoming user utterance (single message — NOT the history)."""
    with _child_span("user_message") as span:
        # gen_ai.system is "voice_survey", not a model vendor, because the caller
        # produced this text and no model was involved. gen_ai.operation.name is
        # deliberately unset for the same reason: naming an operation here would
        # make this read as a generation and double-count the real model spans.
        span.set_attribute("gen_ai.system", "voice_survey")
        span.set_attribute("voice_survey.message_role", "user")
        span.set_attribute(
            "gen_ai.input.messages",
            serialize_messages([{"role": "user", "text": text}]),
        )
        span.set_attribute("voice_survey.node_id", node_id)
        span.set_attribute("call_sid", call_sid)
        span.set_attribute("voice_survey.contains_user_content", "true")


def emit_survey_response_span(*, text: str, node_id: str, call_sid: str = "") -> None:
    """Child span marking a response that came from the survey definition (no model)."""
    with _child_span("generate_content survey_definition") as span:
        span.set_attribute("gen_ai.operation.name", "generate_content")
        span.set_attribute("gen_ai.system", "survey_definition")
        span.set_attribute(
            "gen_ai.output.messages",
            serialize_messages([{"role": "assistant", "text": text}]),
        )
        span.set_attribute("voice_survey.node_id", node_id)
        span.set_attribute("call_sid", call_sid)
        span.set_attribute("voice_survey.contains_user_content", "true")
