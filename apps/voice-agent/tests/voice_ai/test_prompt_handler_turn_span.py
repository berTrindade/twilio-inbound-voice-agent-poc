"""Tests: per-turn conversation parent span + user-message child span in handle_prompt_message."""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from voice_agent.api.session_context import SessionContext
from voice_agent.api.websocket_handlers.prompt_handler import handle_prompt_message
from voice_agent.api.websocket_types import PromptEndMode

# ---------------------------------------------------------------------------
# Module-scoped OTel provider — shared with test_conversation_trace.py
# ---------------------------------------------------------------------------

_EXPORTER = InMemorySpanExporter()


@pytest.fixture(scope="module", autouse=True)
def _install_tracer_provider():
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


# ---------------------------------------------------------------------------
# SessionContext factory
# ---------------------------------------------------------------------------


def make_msg_span():
    span = Mock()
    span.set_attribute = Mock()
    return span


def make_ctx(
    node_id: str = "Q_NAME_V1",
    question_prompt: str = "What is your name?",
):
    node = {"id": node_id, "text": question_prompt, "type": "free_text"}

    websocket = AsyncMock()
    metrics_collector = Mock()

    llm_handler = Mock()
    llm_handler.call_small_model_async = AsyncMock()
    llm_handler.call_big_model_async = AsyncMock()

    engine = Mock()
    engine.get_node.return_value = node

    adapter = Mock()
    adapter.engine = engine
    adapter.current.return_value = {
        "node_id": node_id,
        "question_prompt": question_prompt,
        "finished": False,
        "interruptible": True,
        "preemptible": True,
    }
    adapter.snapshot.return_value = {"answers": {}}
    adapter.merge_user_utterance.side_effect = lambda nid, text: text
    adapter.validate.return_value = {"valid": False, "normalized": None, "reason": ""}
    adapter.should_escalate.return_value = False

    call_state_manager = Mock()
    call_state_manager.get_current_question_id.return_value = node_id

    ctx = SessionContext(
        websocket=websocket,
        adapter=adapter,
        llm_handler=llm_handler,
        conversation_log=[],
        correlation_id="corr-test",
        session_id="sess-test",
        metrics_collector=metrics_collector,
        call_state_manager=call_state_manager,
        call_sid="CA-test-123",
    )
    return ctx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_span_wraps_small_model_turn(span_exporter):
    """
    A complete small-model turn must produce:
      1. A parent span named "invoke_agent voice_survey" with gen_ai.input.messages
         containing the user text.
      2. A child "voice_ai.llm.small_model" span sharing the parent's trace_id.
      3. A child "user_message" span with voice_survey.message_role == "user".
    """
    ctx = make_ctx()
    msg_span = make_msg_span()

    small_resp = {
        "interpretation": "other",
        "answer": {"type": "free_text", "value": "Jordan"},
        "reply": "Got it, thank you!",
        "confidence": 0.95,
        "guardrail_topic": "none",
    }

    # Patch the small model call to return our fake response without hitting Bedrock.
    # We also need to emit a real llm span so we can assert trace_id nesting.
    from voice_agent.voice_ai.llm_instrumentation import start_voice_llm_span

    async def fake_small_model_async(**kwargs):
        with start_voice_llm_span(
            "voice_ai.llm.small_model",
            model="test-model",
            call_sid=kwargs.get("call_sid", ""),
        ):
            pass
        return small_resp

    ctx.llm_handler.call_small_model_async = fake_small_model_async

    with patch(
        "voice_agent.api.websocket_handlers.prompt_handler._route_small_model_result",
        new_callable=AsyncMock,
    ) as route_result:
        route_result.return_value = Mock(
            end_mode=PromptEndMode.CONTINUE,
            active_big_model_node=None,
        )

        await handle_prompt_message(
            ctx,
            {
                "type": "prompt",
                "voicePrompt": "My name is Jordan",
                "last": True,
            },
            msg_span,
        )

    spans = span_exporter.get_finished_spans()
    span_names = [s.name for s in spans]

    # 1. Parent turn span exists.
    turn_spans = [s for s in spans if s.name == "invoke_agent voice_survey"]
    assert len(turn_spans) == 1, f"Expected 1 turn span, got: {span_names}"
    turn_span = turn_spans[0]
    turn_trace_id = turn_span.get_span_context().trace_id

    # Parent carries the user text in gen_ai.input.messages.
    messages_json = turn_span.attributes.get("gen_ai.input.messages", "[]")
    messages = json.loads(messages_json)
    user_contents = [m["content"] for m in messages if m.get("role") == "user"]
    assert any(
        "Jordan" in c for c in user_contents
    ), f"User text not found in turn span messages: {messages}"

    # 2. LLM small-model span shares the parent trace_id (nesting).
    llm_spans = [s for s in spans if s.name == "voice_ai.llm.small_model"]
    assert len(llm_spans) == 1, f"Expected 1 LLM span, got: {span_names}"
    assert (
        llm_spans[0].get_span_context().trace_id == turn_trace_id
    ), "LLM span must share trace_id with the turn parent"

    # 3. user_message child span exists with correct attributes.
    user_msg_spans = [
        s for s in spans if s.attributes.get("voice_survey.message_role") == "user"
    ]
    assert len(user_msg_spans) == 1, f"Expected 1 user_message span, got: {span_names}"
    um = user_msg_spans[0]
    assert (
        um.get_span_context().trace_id == turn_trace_id
    ), "user_message span must share trace_id with the turn parent"
    um_messages = json.loads(um.attributes.get("gen_ai.input.messages", "[]"))
    assert any(
        "Jordan" in m.get("content", "") for m in um_messages
    ), f"User text not in user_message span: {um_messages}"


@pytest.mark.asyncio
async def test_no_turn_span_for_partial_stt(span_exporter):
    """When last=False (partial STT), the function returns early with no turn span."""
    ctx = make_ctx()
    msg_span = make_msg_span()

    await handle_prompt_message(
        ctx,
        {
            "type": "prompt",
            "voicePrompt": "partial...",
            "last": False,
        },
        msg_span,
    )

    turn_spans = [
        s
        for s in span_exporter.get_finished_spans()
        if s.name == "invoke_agent voice_survey"
    ]
    assert len(turn_spans) == 0, "No turn span expected for partial STT (last=False)"


@pytest.mark.asyncio
async def test_turn_span_carries_call_sid(span_exporter):
    """The turn span must carry call_sid and the participant id from the context."""
    ctx = make_ctx()
    msg_span = make_msg_span()

    small_resp = {
        "interpretation": "other",
        "answer": None,
        "reply": "ok",
        "confidence": 0.9,
        "guardrail_topic": "none",
    }

    async def fake_small(*, call_sid="", **kwargs):
        return small_resp

    ctx.llm_handler.call_small_model_async = fake_small

    with patch(
        "voice_agent.api.websocket_handlers.prompt_handler._route_small_model_result",
        new_callable=AsyncMock,
        return_value=Mock(end_mode=PromptEndMode.CONTINUE, active_big_model_node=None),
    ):
        await handle_prompt_message(
            ctx,
            {"type": "prompt", "voicePrompt": "hello", "last": True},
            msg_span,
        )

    turn_spans = [
        s
        for s in span_exporter.get_finished_spans()
        if s.name == "invoke_agent voice_survey"
    ]
    assert len(turn_spans) == 1
    attrs = turn_spans[0].attributes
    assert attrs["call_sid"] == "CA-test-123"
    assert attrs["session_id"] == "sess-test"
    assert attrs["correlation_id"] == "corr-test"
