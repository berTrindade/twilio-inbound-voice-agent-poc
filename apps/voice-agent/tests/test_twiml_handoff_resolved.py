"""Tests for voice_survey.handoff_resolved span emitted from /twiml/handoff_result."""

import pytest
from fastapi.testclient import TestClient

from voice_agent.main import app
from voice_agent.voice_ai.handoff_state import HandoffContext, set_handoff

client = TestClient(app)


@pytest.fixture(autouse=True)
def _bypass_twilio_signature():
    """These tests exercise handoff_result span emission, not Twilio auth; bypass
    signature validation via dependency override, same as test_twiml.py.
    Twilio auth itself is covered in tests/test_twilio_auth.py."""
    from voice_agent.api.twilio_auth import verify_twilio_signature

    app.dependency_overrides[verify_twilio_signature] = lambda: None
    yield
    app.dependency_overrides.clear()


def _seed(handoff_store, call_sid, path="escalation", trigger="coach_requested"):
    handoff_store(call_sid)
    set_handoff(
        HandoffContext(
            call_sid=call_sid,
            whisper_text="x",
            resume_snapshot={},
            participant_phone="",
            path=path,
            response_id="resp-1",
            trigger=trigger,
        )
    )


def _resolved(exp):
    return [
        s
        for s in exp.get_finished_spans()
        if s.attributes.get("voice_survey.event") == "handoff_resolved"
    ]


def test_resolved_succeeded(business_span_exporter, handoff_store):
    _seed(handoff_store, "CA-success")
    client.post(
        "/twiml/handoff_result",
        data={"CallSid": "CA-success", "DialCallStatus": "completed"},
    )
    a = _resolved(business_span_exporter)[0].attributes
    assert a["voice_survey.handoff_outcome"] == "succeeded"
    assert a["voice_survey.path"] == "escalation"
    assert a["voice_survey.trigger"] == "coach_requested"
    assert a["call_sid"] == "CA-success"
    assert a["response_id"] == "resp-1"


def test_resolved_no_answer_happy_path(business_span_exporter, handoff_store):
    _seed(handoff_store, "CA-noans", path="happy", trigger="completed_survey")
    client.post(
        "/twiml/handoff_result",
        data={"CallSid": "CA-noans", "DialCallStatus": "no-answer"},
    )
    a = _resolved(business_span_exporter)[0].attributes
    assert a["voice_survey.handoff_outcome"] == "no_answer"
    assert a["voice_survey.path"] == "happy"
    assert a["voice_survey.trigger"] == "completed_survey"


def test_resolved_with_no_stored_context(business_span_exporter, handoff_store):
    """If Twilio reports a result for a CallSid we never stored (e.g. the
    HandoffContext expired or was popped by something else), the span is still
    emitted — with the dial outcome and empty correlation fields."""
    client.post(
        "/twiml/handoff_result",
        data={"CallSid": "CA-orphan", "DialCallStatus": "busy"},
    )
    spans = [
        s
        for s in _resolved(business_span_exporter)
        if s.attributes.get("call_sid") == "CA-orphan"
    ]
    assert len(spans) == 1
    a = spans[0].attributes
    assert a["voice_survey.handoff_outcome"] == "busy"
    assert a["voice_survey.path"] == ""
    assert a["voice_survey.trigger"] == ""
    assert a["response_id"] == ""
