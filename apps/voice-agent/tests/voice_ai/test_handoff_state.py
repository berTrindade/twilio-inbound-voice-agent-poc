"""The handoff context store round-trips through the database.

It is persisted rather than held in a module dict because the TwiML webhooks
that read it (coach_whisper, handoff_result) are addressed to the service, not
to the process that held the websocket and wrote it.
"""

from voice_agent.voice_ai.handoff_state import (
    HandoffContext,
    get_handoff,
    pop_handoff,
    set_handoff,
)


def test_carries_path_and_response_id(handoff_store):
    handoff_store("CA1")
    set_handoff(
        HandoffContext(
            call_sid="CA1",
            whisper_text="...",
            resume_snapshot={},
            participant_phone="+1555",
            path="escalation",
            response_id="resp-1",
        )
    )
    ctx = pop_handoff("CA1")
    assert ctx.path == "escalation"
    assert ctx.response_id == "resp-1"
    assert ctx.attempts == 0  # preserved


def test_new_fields_default_empty(handoff_store):
    handoff_store("CA2")
    set_handoff(
        HandoffContext(
            call_sid="CA2", whisper_text="x", resume_snapshot={}, participant_phone=""
        )
    )
    ctx = pop_handoff("CA2")
    assert ctx.path == "" and ctx.response_id == ""


def test_resume_snapshot_survives_the_round_trip(handoff_store):
    """The snapshot is a nested dict, so it has to survive JSON encoding."""
    handoff_store("CA3")
    set_handoff(
        HandoffContext(
            call_sid="CA3",
            whisper_text="x",
            resume_snapshot={"current_id": "q2", "answers": {"q1": "yes"}},
        )
    )
    ctx = get_handoff("CA3")
    assert ctx.resume_snapshot == {"current_id": "q2", "answers": {"q1": "yes"}}


def test_pop_clears_so_a_retried_webhook_cannot_reuse_it(handoff_store):
    handoff_store("CA4")
    set_handoff(HandoffContext(call_sid="CA4", whisper_text="x"))
    assert pop_handoff("CA4") is not None
    assert pop_handoff("CA4") is None


def test_get_does_not_clear(handoff_store):
    handoff_store("CA5")
    set_handoff(HandoffContext(call_sid="CA5", whisper_text="x"))
    assert get_handoff("CA5") is not None
    assert get_handoff("CA5") is not None


def test_unknown_call_sid_is_none(handoff_store):
    assert get_handoff("CA_nope") is None
    assert pop_handoff("CA_nope") is None


def test_call_with_no_row_is_survivable(handoff_store):
    """A call that never got a survey_responses row has nowhere to store this.

    It must not raise into the handoff path: the TwiML side falls back to a
    generic whisper, the same as a context that was never set.
    """
    set_handoff(HandoffContext(call_sid="CA_norow", whisper_text="x"))
    assert get_handoff("CA_norow") is None


def test_stored_blob_from_an_older_shape_is_tolerated(handoff_store):
    """A row can outlive a deploy, so unknown keys must not raise in a webhook."""
    from voice_agent.voice_ai import handoff_state

    handoff_store("CA6")
    handoff_state._write("CA6", {"call_sid": "CA6", "whisper_text": "x", "gone": 1})
    ctx = get_handoff("CA6")
    assert ctx.whisper_text == "x"
