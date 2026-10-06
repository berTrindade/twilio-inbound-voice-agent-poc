"""Wiring tests: emit_survey_response_span fires at the speak_next_or_finish call sites.

These tests verify that handle_happy_path and handle_big_model_response each
emit a gen_ai.system="survey_definition" span when nxt carries prompt text.
They do NOT test emit_survey_response_span itself (covered in test_conversation_trace.py).
"""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from voice_agent.api.session_context import SessionContext
from voice_agent.voice_ai.conversation_trace import start_conversation_turn_span

# ---------------------------------------------------------------------------
# Module-scoped OTel provider — shared with other voice_ai test modules
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
# Shared helpers
# ---------------------------------------------------------------------------


def _make_ctx(call_sid: str = "CA-wiring-test") -> SessionContext:
    """Minimal SessionContext with a fake adapter and async websocket."""
    websocket = AsyncMock()
    metrics_collector = Mock()

    adapter = Mock()
    adapter.engine = Mock()
    adapter.engine.answers = {}
    adapter.current.return_value = {
        "node_id": "q1",
        "question_prompt": "What is your name?",
        "finished": False,
        "interruptible": True,
        "preemptible": True,
    }
    adapter.snapshot.return_value = {"answers": {}}
    adapter.validate.return_value = {"valid": True, "normalized": "Jordan"}
    adapter.should_escalate.return_value = False

    # advance() returns the next node with a question_prompt
    adapter.advance.return_value = {
        "node_id": "q2",
        "question_prompt": "What is your date of birth?",
        "spoken_intro": "",
        "spoken_intro_interruptible": None,
        "spoken_intro_preemptible": None,
        "finished": False,
        "handover_to_coach": False,
        "handover_context": None,
        "interruptible": None,
        "preemptible": None,
    }

    call_state_manager = Mock()
    call_state_manager.get_current_question_id.return_value = "q1"
    call_state_manager.complete_question.return_value = None

    return SessionContext(
        websocket=websocket,
        adapter=adapter,
        llm_handler=Mock(),
        conversation_log=[],
        correlation_id="corr-wiring",
        session_id="sess-wiring",
        metrics_collector=metrics_collector,
        call_state_manager=call_state_manager,
        milestone_dispatcher=None,
        call_sid=call_sid,
    )


def _make_turn(node_id: str = "q1") -> object:
    from voice_agent.api.websocket_handlers.outcomes.base import TurnContext

    return TurnContext(
        cur={
            "node_id": node_id,
            "question_prompt": "What is your name?",
            "interruptible": True,
            "preemptible": True,
        },
        node={"id": node_id, "type": "free_text"},
        node_id=node_id,
        combined_user_text="Jordan",
        user_text="Jordan",
        interpretation="answer",
        reply="Got it.",
        small_conf=0.95,
        val_res={"valid": True, "normalized": "Jordan"},
        small_resp={
            "interpretation": "answer",
            "answer": {"type": "free_text", "value": "Jordan"},
            "reply": "Got it.",
            "confidence": 0.95,
            "guardrail_topic": "none",
        },
    )


def _survey_definition_spans(exporter: InMemorySpanExporter):
    return [
        s
        for s in exporter.get_finished_spans()
        if s.attributes.get("gen_ai.system") == "survey_definition"
    ]


# ---------------------------------------------------------------------------
# happy_path wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_emits_survey_response_span(span_exporter):
    """handle_happy_path must emit a survey_definition span for the next prompt."""
    from voice_agent.api.websocket_handlers.outcomes.happy_path import (
        handle_happy_path,
    )

    ctx = _make_ctx(call_sid="CA-hp-1")
    turn = _make_turn()

    # Patch speak_next_or_finish so no real websocket I/O happens
    with (
        patch(
            "voice_agent.api.websocket_handlers.outcomes.happy_path.speak_next_or_finish",
            new_callable=AsyncMock,
            return_value=False,  # not finished
        ),
        patch(
            "voice_agent.api.websocket_handlers.outcomes.happy_path._emit_milestone_events",
            new_callable=AsyncMock,
        ),
    ):
        # Run inside a turn span so emit_survey_response_span nests correctly
        with start_conversation_turn_span(
            call_sid="CA-hp-1", session_id="s", correlation_id="c"
        ):
            await handle_happy_path(ctx, turn)

    spans = _survey_definition_spans(span_exporter)
    assert len(spans) == 1, f"Expected 1 survey_definition span, got {len(spans)}"

    a = spans[0].attributes
    assert a["gen_ai.operation.name"] == "generate_content"
    assert a["gen_ai.system"] == "survey_definition"
    assert a["voice_survey.node_id"] == "q2"
    assert a["call_sid"] == "CA-hp-1"

    output = json.loads(a["gen_ai.output.messages"])
    assert any(
        "date of birth" in m.get("content", "").lower() for m in output
    ), f"Expected next question text in gen_ai.output.messages: {output}"


@pytest.mark.asyncio
async def test_happy_path_skips_span_when_no_nxt(span_exporter):
    """When adapter.advance() returns None, no survey_definition span is emitted."""
    from voice_agent.api.websocket_handlers.outcomes.happy_path import (
        handle_happy_path,
    )

    ctx = _make_ctx()
    ctx.adapter.advance.return_value = None  # terminal — no next node
    turn = _make_turn()

    with (
        patch(
            "voice_agent.api.websocket_handlers.outcomes.happy_path.speak_next_or_finish",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "voice_agent.api.websocket_handlers.outcomes.happy_path._emit_milestone_events",
            new_callable=AsyncMock,
        ),
    ):
        with start_conversation_turn_span(
            call_sid="CA-hp-2", session_id="s", correlation_id="c"
        ):
            await handle_happy_path(ctx, turn)

    spans = _survey_definition_spans(span_exporter)
    assert len(spans) == 0, "No survey_definition span expected when nxt is None"


# ---------------------------------------------------------------------------
# big_model_response wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_big_model_response_emits_survey_response_span(span_exporter):
    """handle_big_model_response (action=record) must emit a survey_definition span."""
    from voice_agent.api.websocket_handlers.outcomes.big_model_response import (
        handle_big_model_response,
    )

    ctx = _make_ctx(call_sid="CA-bmr-1")
    cur = {
        "node_id": "q1",
        "question_prompt": "What is your name?",
        "interruptible": True,
        "preemptible": True,
    }
    big_model_resp = {"action": "record", "question_id": "q1", "value": "Jordan"}

    with (
        patch(
            "voice_agent.api.websocket_handlers.outcomes.big_model_response.speak_next_or_finish",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "voice_agent.api.websocket_handlers.outcomes.big_model_response._emit_milestone_events",
            new_callable=AsyncMock,
        ),
    ):
        with start_conversation_turn_span(
            call_sid="CA-bmr-1", session_id="s", correlation_id="c"
        ):
            await handle_big_model_response(ctx, cur, big_model_resp)

    spans = _survey_definition_spans(span_exporter)
    assert len(spans) == 1, f"Expected 1 survey_definition span, got {len(spans)}"

    a = spans[0].attributes
    assert a["gen_ai.operation.name"] == "generate_content"
    assert a["gen_ai.system"] == "survey_definition"
    assert a["voice_survey.node_id"] == "q2"
    assert a["call_sid"] == "CA-bmr-1"

    output = json.loads(a["gen_ai.output.messages"])
    assert any(
        "date of birth" in m.get("content", "").lower() for m in output
    ), f"Expected next question text in gen_ai.output.messages: {output}"


# ---------------------------------------------------------------------------
# node-driven handoff trigger comes from the handover NODE
# (handover_context.node_id), not the (empty) nxt["node_id"].
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_handover_uses_node_specific_trigger(span_exporter):
    """A survey-routed handover must attribute voice_survey.trigger from the
    handover node id, not the SURVEY_ROUTED fallback (nxt['node_id'] is '' here)."""
    import types as _types
    from voice_agent.api.websocket_handlers.outcomes import happy_path as hp
    from voice_agent.voice_ai import handoff_reasons as hr
    from voice_agent.voice_ai.handoff_reasons import HandoffReason, HandoffSource

    ctx = _make_ctx(call_sid="CA-hp-handover")
    turn = _make_turn()

    # Engine nulls current_id at a handover node → nxt["node_id"] == "".
    # The real node id lives on handover_context.
    ctx.adapter.advance.return_value = {
        "node_id": "",
        "question_prompt": "",
        "spoken_intro": "Connecting you to a coach.",
        "spoken_intro_interruptible": None,
        "spoken_intro_preemptible": None,
        "finished": False,
        "handover_to_coach": True,
        "handover_context": _types.SimpleNamespace(
            node_id="HANDOVER_NODE_V1",
            whisper_text="coach whisper",
        ),
        "interruptible": None,
        "preemptible": None,
    }

    # The shipped demo survey maps no handover nodes, so stand one up here:
    # without a mapping both the real node id and the empty one resolve to
    # SURVEY_ROUTED and the assertion below could not tell them apart.
    with (
        patch.dict(
            hr.HANDOVER_NODE_REASONS,
            {"HANDOVER_NODE_V1": HandoffReason.SYSTEM_ERROR},
        ),
        patch.object(hp.settings, "coach_handoff_enabled", True),
        patch.object(hp, "send_and_log", new_callable=AsyncMock),
        patch.object(hp, "_persist_coach_handoff", new_callable=AsyncMock),
        patch.object(hp, "_emit_milestone_events", new_callable=AsyncMock),
        patch.object(hp, "initiate_coach_handoff", new_callable=AsyncMock) as mock_init,
    ):
        await hp.handle_happy_path(ctx, turn)

    mock_init.assert_awaited_once()
    kwargs = mock_init.await_args.kwargs
    assert kwargs["trigger"] == HandoffReason.SYSTEM_ERROR  # NOT survey_routed
    assert kwargs["handoff_source"] == HandoffSource.SURVEY
