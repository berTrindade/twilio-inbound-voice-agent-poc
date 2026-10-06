"""Tests for the per-turn conversation-trace parent-span helper."""

import json

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from voice_agent.voice_ai.conversation_trace import (
    serialize_messages,
    start_conversation_turn_span,
)

_EXPORTER = InMemorySpanExporter()


@pytest.fixture(scope="module", autouse=True)
def _install_test_tracer_provider():
    current = trace.get_tracer_provider()
    if not isinstance(current, TracerProvider):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
        current = provider
    current.add_span_processor(SimpleSpanProcessor(_EXPORTER))
    yield


@pytest.fixture
def span_exporter():
    _EXPORTER.clear()
    yield _EXPORTER
    _EXPORTER.clear()


def test_serialize_messages_to_genai_format():
    out = serialize_messages(
        [{"role": "user", "text": "hi"}, {"role": "assistant", "text": "hello"}]
    )
    assert json.loads(out) == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]


def test_turn_span_nests_under_the_operation_with_genai_history(span_exporter):
    history = [{"role": "user", "text": "hi"}]
    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("websocket.message.prompt") as op:
        op_trace = op.get_span_context().trace_id
        with start_conversation_turn_span(
            call_sid="CA1",
            session_id="s1",
            correlation_id="c1",
            conversation_history=history,
        ) as turn:
            turn_trace = turn.get_span_context().trace_id

    spans = [
        s
        for s in span_exporter.get_finished_spans()
        if s.attributes.get("gen_ai.operation.name") == "invoke_agent"
    ]
    assert len(spans) == 1
    a = spans[0].attributes
    assert turn_trace == op_trace  # one call is one trace
    assert a["gen_ai.provider.name"] == "ollama"
    assert a["gen_ai.conversation.id"] == "CA1"
    assert json.loads(a["gen_ai.input.messages"]) == [{"role": "user", "content": "hi"}]
    assert a["call_sid"] == "CA1"


def test_llm_span_nests_under_turn_parent(span_exporter):
    from voice_agent.voice_ai.llm_instrumentation import start_voice_llm_span

    with start_conversation_turn_span(
        call_sid="CA1",
        session_id="s1",
        correlation_id="c1",
        conversation_history=[],
    ) as turn:
        turn_trace = turn.get_span_context().trace_id
        with start_voice_llm_span("chat", model="m", call_sid="CA1") as llm:
            llm_trace = llm.get_span_context().trace_id
    assert llm_trace == turn_trace


def test_user_message_span(span_exporter):
    from voice_agent.voice_ai.conversation_trace import emit_user_message_span

    emit_user_message_span(
        text="my name is Jordan", node_id="q_name_v1", call_sid="CA1"
    )
    spans = [
        s
        for s in span_exporter.get_finished_spans()
        if s.attributes.get("voice_survey.message_role") == "user"
    ]
    assert len(spans) == 1
    a = spans[0].attributes
    assert json.loads(a["gen_ai.input.messages"]) == [
        {"role": "user", "content": "my name is Jordan"}
    ]
    assert a["voice_survey.node_id"] == "q_name_v1"
    assert a["voice_survey.contains_user_content"] == "true"
    # Not a model vendor: the caller produced this text.
    assert a["gen_ai.system"] == "voice_survey"
    # No gen_ai.operation.name on purpose, so this never reads as a generation
    # and double-counts the real model spans.
    assert "gen_ai.operation.name" not in a


def test_survey_definition_response_span(span_exporter):
    from voice_agent.voice_ai.conversation_trace import emit_survey_response_span

    emit_survey_response_span(
        text="What is your date of birth?", node_id="q_dob_v1", call_sid="CA1"
    )
    spans = [
        s
        for s in span_exporter.get_finished_spans()
        if s.attributes.get("gen_ai.system") == "survey_definition"
    ]
    assert len(spans) == 1
    a = spans[0].attributes
    assert a["gen_ai.operation.name"] == "generate_content"
    assert json.loads(a["gen_ai.output.messages"]) == [
        {"role": "assistant", "content": "What is your date of birth?"}
    ]
    assert a["voice_survey.node_id"] == "q_dob_v1"
