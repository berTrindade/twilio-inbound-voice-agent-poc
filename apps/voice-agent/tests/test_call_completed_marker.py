import types

from voice_agent.api.websocket_handlers.session_completion import (
    emit_call_completed_marker,
)


def _ctx(call_sid="CA1", csm=True):
    call_state_manager = (
        types.SimpleNamespace(
            response_id="r1",
            completed_questions=[{"turns": [1, 2]}, {"turns": [3]}],  # 3 turns total
            get_total_duration_ms=lambda: 180_000,
        )
        if csm
        else None
    )
    return types.SimpleNamespace(
        call_sid=call_sid,
        session_id="s1",
        correlation_id="c1",
        active_big_model_node="node_42",
        call_state_manager=call_state_manager,
    )


def _spans(exp):
    return [
        s
        for s in exp.get_finished_spans()
        if s.attributes.get("voice_survey.event") == "call_completed"
    ]


def test_call_completed_finished(business_span_exporter):
    emit_call_completed_marker(_ctx(), completion_type="finished")
    a = _spans(business_span_exporter)[0].attributes
    assert a["voice_survey.completion_type"] == "finished"
    assert a["voice_survey.final_node_id"] == "node_42"
    assert a["voice_survey.turn_count"] == 3  # sum of per-question turns
    assert a["voice_survey.duration_ms"] == 180_000
    assert a["response_id"] == "r1"


def test_call_completed_disconnected(business_span_exporter):
    emit_call_completed_marker(_ctx(), completion_type="disconnected")
    assert (
        _spans(business_span_exporter)[0].attributes["voice_survey.completion_type"]
        == "disconnected"
    )


def test_call_completed_error(business_span_exporter):
    emit_call_completed_marker(_ctx(), completion_type="error")
    assert (
        _spans(business_span_exporter)[0].attributes["voice_survey.completion_type"]
        == "error"
    )


def test_no_marker_without_call_state_manager(business_span_exporter):
    # Call ended before setup completed → no call_state_manager → no marker.
    emit_call_completed_marker(_ctx(csm=False), completion_type="disconnected")
    assert _spans(business_span_exporter) == []
