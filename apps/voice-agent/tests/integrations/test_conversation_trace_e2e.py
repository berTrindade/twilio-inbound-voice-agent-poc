"""E2E integration test: per-turn conversation-trace HIERARCHY.

Drives a real `handle_prompt_message` call through the HAPPY_PATH branch and
asserts that ALL four span kinds share a single trace_id:

  1. Parent: ``invoke_agent voice_survey``  (gen_ai.input.messages carries user text)
  2. Child:  ``user_message``               (voice_survey.message_role == "user")
  3. Child:  ``voice_ai.llm.small_model``   (LLM span from call_small_model_async)
  4. Child:  ``generate_content survey_definition``  (survey-response span from happy_path)

Mocked:
- ``call_small_model_async`` → returns a valid HAPPY_PATH "answer" response AND
  emits a real ``start_voice_llm_span`` so the LLM child span appears in the tree.
- ``speak_next_or_finish`` and ``send_and_log`` (AsyncMock) → no real WebSocket I/O.
- ``_emit_milestone_events`` (AsyncMock) → no external side-effects.
- ``ctx.adapter.advance()`` → returns a ``nxt`` dict with ``question_prompt`` and
  ``node_id`` so the survey-response span fires.
- ``ctx.adapter.record()`` → no-op (Mock).
- ``ctx.adapter.validate()`` → returns ``{valid: True, normalized: "Jordan"}``.
- ``ctx.adapter.should_escalate()`` → returns False.
- ``call_state_manager.complete_question()`` → returns None (no persist task).

NOT mocked (real code exercised):
- ``handle_prompt_message`` — full CASE 1 flow up to ``_route_small_model_result``.
- ``classify_prompt_outcome`` — routes to HAPPY_PATH.
- ``handle_happy_path`` — calls record/advance, emits survey-response span.
- ``start_conversation_turn_span`` → ``emit_user_message_span`` → ``start_voice_llm_span``
  → ``emit_survey_response_span`` — all real instrumentation.
"""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from voice_agent.api.session_context import SessionContext
from voice_agent.api.websocket_handlers.prompt_handler import handle_prompt_message
from voice_agent.voice_ai.llm_instrumentation import start_voice_llm_span

# ---------------------------------------------------------------------------
# Module-scoped OTel provider — isolated exporter for this module
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


def _make_ctx(
    node_id: str = "Q_NAME_V1",
    question_prompt: str = "What is your name?",
) -> SessionContext:
    """Build a minimal SessionContext with all dependencies mocked."""
    node = {"id": node_id, "text": question_prompt, "type": "free_text"}

    websocket = AsyncMock()

    adapter = Mock()
    adapter.engine = Mock()
    adapter.engine.get_node = Mock(return_value=node)
    adapter.engine.answers = {}
    adapter.current.return_value = {
        "node_id": node_id,
        "question_prompt": question_prompt,
        "finished": False,
        "interruptible": True,
        "preemptible": True,
    }
    adapter.snapshot.return_value = {"answers": {}}
    adapter.merge_user_utterance.side_effect = lambda nid, text: text
    adapter.validate.return_value = {"valid": True, "normalized": "Jordan"}
    adapter.should_escalate.return_value = False
    adapter.record = Mock()

    # advance() returns the next node so happy_path emits the survey-response span
    adapter.advance.return_value = {
        "node_id": "Q_DOB_V1",
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

    llm_handler = Mock()
    # call_small_model_async is replaced per-test

    call_state_manager = Mock()
    call_state_manager.get_current_question_id.return_value = node_id
    call_state_manager.complete_question.return_value = None  # no persist task

    return SessionContext(
        websocket=websocket,
        adapter=adapter,
        llm_handler=llm_handler,
        conversation_log=[{"role": "assistant", "text": question_prompt}],
        correlation_id="corr-e2e",
        session_id="sess-e2e",
        metrics_collector=Mock(),
        call_state_manager=call_state_manager,
        call_sid="CA-e2e-123",
    )


# ---------------------------------------------------------------------------
# The e2e test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_turn_span_hierarchy_all_share_trace_id(span_exporter):
    """
    Full 4-node span tree from a real handle_prompt_message HAPPY_PATH turn:

      invoke_agent voice_survey  (parent, new trace root)
      ├── user_message           (voice_survey.message_role == "user")
      ├── voice_ai.llm.small_model  (LLM span emitted inside call_small_model_async)
      └── generate_content survey_definition  (survey-response from happy_path)

    All four spans must share the same trace_id (true nesting).
    """
    ctx = _make_ctx()

    # call_small_model_async: returns a HAPPY_PATH "answer" response
    # and ALSO emits a real LLM span so it appears in the trace.
    async def fake_small_model_async(**kwargs):
        with start_voice_llm_span(
            "voice_ai.llm.small_model",
            model="test-model",
            call_sid=kwargs.get("call_sid", ""),
        ):
            pass
        return {
            "interpretation": "answer",
            "answer": {"type": "free_text", "value": "Jordan"},
            "reply": "Thank you!",
            "confidence": 0.97,
            "guardrail_topic": "none",
        }

    ctx.llm_handler.call_small_model_async = fake_small_model_async

    # Patch speak_next_or_finish and _emit_milestone_events so no real I/O occurs
    with (
        patch(
            "voice_agent.api.websocket_handlers.outcomes.happy_path.speak_next_or_finish",
            new_callable=AsyncMock,
            return_value=False,  # not finished — survey continues
        ),
        patch(
            "voice_agent.api.websocket_handlers.outcomes.happy_path._emit_milestone_events",
            new_callable=AsyncMock,
        ),
    ):
        msg_span = Mock()
        msg_span.set_attribute = Mock()

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

    # ------------------------------------------------------------------
    # 1. Parent span: invoke_agent voice_survey
    # ------------------------------------------------------------------
    parent_spans = [s for s in spans if s.name == "invoke_agent voice_survey"]
    assert (
        len(parent_spans) == 1
    ), f"Expected exactly 1 'invoke_agent voice_survey' span, got: {span_names}"
    parent = parent_spans[0]
    parent_trace_id = parent.get_span_context().trace_id
    parent_span_id = parent.get_span_context().span_id

    # Parent must carry the user text in gen_ai.input.messages
    messages_json = parent.attributes.get("gen_ai.input.messages", "[]")
    messages = json.loads(messages_json)
    user_contents = [m["content"] for m in messages if m.get("role") == "user"]
    assert any(
        "Jordan" in c for c in user_contents
    ), f"User text 'Jordan' not found in turn-parent gen_ai.input.messages: {messages}"

    # ------------------------------------------------------------------
    # 2. user_message child span
    # ------------------------------------------------------------------
    user_msg_spans = [
        s for s in spans if s.attributes.get("voice_survey.message_role") == "user"
    ]
    assert (
        len(user_msg_spans) == 1
    ), f"Expected exactly 1 user_message span, got: {span_names}"
    um = user_msg_spans[0]
    assert (
        um.get_span_context().trace_id == parent_trace_id
    ), "user_message span must share trace_id with the turn parent (true nesting)"
    assert (
        um.parent is not None and um.parent.span_id == parent_span_id
    ), "user_message span must be a DIRECT child of the turn parent (parent.span_id)"
    um_messages = json.loads(um.attributes.get("gen_ai.input.messages", "[]"))
    assert any(
        "Jordan" in m.get("content", "") for m in um_messages
    ), f"User text not found in user_message span messages: {um_messages}"

    # ------------------------------------------------------------------
    # 3. LLM small-model child span
    # ------------------------------------------------------------------
    llm_spans = [s for s in spans if s.name == "voice_ai.llm.small_model"]
    assert (
        len(llm_spans) == 1
    ), f"Expected exactly 1 'voice_ai.llm.small_model' span, got: {span_names}"
    assert (
        llm_spans[0].get_span_context().trace_id == parent_trace_id
    ), "LLM small-model span must share trace_id with the turn parent (true nesting)"
    assert (
        llm_spans[0].parent is not None
        and llm_spans[0].parent.span_id == parent_span_id
    ), "LLM small-model span must be a DIRECT child of the turn parent (parent.span_id)"

    # ------------------------------------------------------------------
    # 4. survey_definition response child span
    # ------------------------------------------------------------------
    survey_resp_spans = [
        s for s in spans if s.attributes.get("gen_ai.system") == "survey_definition"
    ]
    assert (
        len(survey_resp_spans) == 1
    ), f"Expected exactly 1 survey_definition span, got: {span_names}"
    sr = survey_resp_spans[0]
    assert (
        sr.get_span_context().trace_id == parent_trace_id
    ), "survey_definition span must share trace_id with the turn parent (true nesting)"
    assert (
        sr.parent is not None and sr.parent.span_id == parent_span_id
    ), "survey_definition span must be a DIRECT child of the turn parent (parent.span_id)"

    # survey_definition span must carry the next question text
    output_json = sr.attributes.get("gen_ai.output.messages", "[]")
    output_msgs = json.loads(output_json)
    assert any(
        "date of birth" in m.get("content", "").lower() for m in output_msgs
    ), f"Next question text not found in survey_definition span: {output_msgs}"

    # ------------------------------------------------------------------
    # Confirm all four trace_ids are literally the same integer
    # ------------------------------------------------------------------
    all_target_spans = parent_spans + user_msg_spans + llm_spans + survey_resp_spans
    trace_ids = {s.get_span_context().trace_id for s in all_target_spans}
    assert len(trace_ids) == 1, (
        f"All 4 span kinds must share ONE trace_id — found {len(trace_ids)} distinct "
        f"trace_ids across spans: {span_names}"
    )
