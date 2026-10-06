import types
from unittest.mock import AsyncMock, patch

from voice_agent.api.websocket_handlers.handoff_initiation import (
    initiate_coach_handoff,
)
from voice_agent.voice_ai.handoff_reasons import HandoffReason, HandoffSource
from voice_agent.voice_ai.handoff_state import pop_handoff


def _fake_ctx(call_sid="CA1"):
    return types.SimpleNamespace(
        call_sid=call_sid,
        session_id="s1",
        correlation_id="c1",
        active_big_model_node="node_42",
        participant_phone="+1555",
        adapter=types.SimpleNamespace(snapshot=lambda: {"snap": True}),
        call_state_manager=types.SimpleNamespace(response_id="resp-1"),
        websocket=object(),
    )


def _started(exp):
    return [
        s
        for s in exp.get_finished_spans()
        if s.attributes.get("voice_survey.event") == "handoff_started"
    ]


async def test_emits_started_and_stores_context(business_span_exporter, handoff_store):
    handoff_store("CA1")
    ctx = _fake_ctx()
    with patch(
        "voice_agent.api.websocket_handlers.handoff_initiation.send_end",
        new=AsyncMock(),
    ) as send_end:
        await initiate_coach_handoff(
            ctx,
            path="escalation",
            trigger=HandoffReason.COACH_REQUESTED,
            handoff_source=HandoffSource.CALLER,
            whisper_text="hi coach",
        )
        send_end.assert_awaited_once()
    a = _started(business_span_exporter)[0].attributes
    assert a["voice_survey.path"] == "escalation"
    assert a["voice_survey.trigger"] == "coach_requested"
    assert a["voice_survey.handoff_source"] == "caller"
    assert a["voice_survey.last_node_id"] == "node_42"
    assert a["voice_survey.handoff_whisper_text"] == "hi coach"
    assert a["voice_survey.contains_user_content"] == "true"
    assert a["call_sid"] == "CA1" and a["response_id"] == "resp-1"
    stored = pop_handoff("CA1")
    assert stored.path == "escalation" and stored.response_id == "resp-1"
    assert stored.whisper_text == "hi coach"
    # trigger is carried in HandoffContext so the resolved span is self-contained
    assert stored.trigger == "coach_requested"


async def test_empty_call_sid_still_emits_span_and_sends_end(
    business_span_exporter, handoff_store
):
    """If the call_sid is empty (e.g. setup never completed), we skip storing
    HandoffContext but still emit the marker and signal Twilio to end. Without
    this, the started/resolved funnel could lose events on edge cases."""
    ctx = _fake_ctx(call_sid="")
    with patch(
        "voice_agent.api.websocket_handlers.handoff_initiation.send_end",
        new=AsyncMock(),
    ) as send_end:
        await initiate_coach_handoff(
            ctx,
            path="escalation",
            trigger=HandoffReason.COACH_REQUESTED,
            handoff_source=HandoffSource.CALLER,
            whisper_text="hi coach",
        )
        send_end.assert_awaited_once()
    started = [
        s
        for s in _started(business_span_exporter)
        if s.attributes.get("call_sid") == ""
    ]
    assert len(started) == 1
    assert started[0].attributes["voice_survey.trigger"] == "coach_requested"
    # nothing should have been persisted under empty call_sid
    assert pop_handoff("") is None


async def test_happy_path_marker(business_span_exporter, handoff_store):
    handoff_store("CA2")
    ctx = _fake_ctx(call_sid="CA2")
    with patch(
        "voice_agent.api.websocket_handlers.handoff_initiation.send_end",
        new=AsyncMock(),
    ):
        await initiate_coach_handoff(
            ctx,
            path="happy",
            trigger=HandoffReason.COMPLETED_SURVEY,
            handoff_source=HandoffSource.SURVEY,
            whisper_text="done",
        )
    happy = [
        s
        for s in _started(business_span_exporter)
        if s.attributes.get("voice_survey.path") == "happy"
    ]
    assert happy[0].attributes["voice_survey.trigger"] == "completed_survey"
    assert happy[0].attributes["voice_survey.handoff_source"] == "survey"
    pop_handoff("CA2")
